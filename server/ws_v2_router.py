"""SatyaCheck — live screening protocol v2 (upgrade plan, Phase 3).

    /api/ws/v2/screen/{session_id}

Client -> server: `start` (JSON: token, caller context), BINARY 16 kHz mono s16le frames
(250-500 ms each), `end` (JSON). Server -> client: `ready`, an `assessment` per scored
window, an `alert` when one is raised or resolved, the final `assessment`, or an
`error` (then the socket closes: 1008 refused, 1013 busy). Message shapes are the
StreamV2* contracts.

Differences from v1 (server/ws_router.py, still served):
  * raw PCM, no base64 and no ffmpeg on the live path — the client resamples once;
  * sign-in rides the first message, never the URL;
  * a reader/consumer split keeps reading at real time while scoring runs; behind real
    time the newest window is scored first and older ones are caught up or reported as
    coverage gaps (server/pipeline/runner.py), never silently skipped;
  * the current assessment and append-only alerts are separate (server/live_session.py).

C owns this file.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

import config
from contracts import (AudioFrame, AudioSource, SessionClose, SessionOpen, StreamV2Error, StreamV2Ready,
                       StreamV2Start)
from server.ws_util import is_client_gone

log = logging.getLogger("satyacheck.ws.v2")
router = APIRouter(prefix="/api/ws/v2", tags=["stream-v2"])

#: Largest binary frame accepted: 2 s of 16 kHz s16le. Clients send 250-500 ms.
MAX_FRAME_BYTES = 16000 * 2 * 2
POLICY_VIOLATION, TRY_AGAIN_LATER = 1008, 1013


class V2ClientSink:
    """Sends a session's verdicts to its v2 client as assessments and alerts. The rules for
    what is sent live in server/live_presenter.py, shared with the WebRTC transport."""
    name = "v2_client"

    def __init__(self, ws: WebSocket, session_id: str) -> None:
        from server.live_presenter import LivePresenter

        self.ws = ws
        self.presenter = LivePresenter(session_id)

    @property
    def alerts(self):
        return self.presenter.alerts

    @property
    def claim_rev(self) -> int:
        return self.presenter.claim_rev

    async def deliver(self, event) -> None:
        changed, assessment = self.presenter.consider(event)
        for alert in changed:
            await self.ws.send_text(alert.model_dump_json())
        if assessment is None:
            return
        await self.ws.send_text(assessment.model_dump_json())
        from server.observability import ASSESSMENTS, COVERAGE_GAP_SECONDS

        ASSESSMENTS.labels(assessment.display_band, "false").inc()
        if event.is_final:
            COVERAGE_GAP_SECONDS.inc(sum(s.end_s - s.start_s for s in assessment.coverage if not s.scored))


def make_runner(dispatcher, owner_id: str, transcriber_factory=None, analyze=None):
    """The session runner for one v2 socket (a seam tests replace to stub ASR)."""
    from server.pipeline.runner import SessionRunner

    return SessionRunner(dispatcher=dispatcher, owner_id=owner_id, transcriber_factory=transcriber_factory,
                         analyze=analyze)


def _reserve_session(owner_id: str, session_id: str) -> bool:
    """Create this account's session row, or confirm it already is theirs. False when the id
    belongs to another account (detected by the primary key, so RLS cannot hide it)."""
    from sqlalchemy.exc import IntegrityError

    from server.database import ScreeningSession, owner_session

    with owner_session(owner_id) as db:
        row = db.get(ScreeningSession, session_id)
        if row is not None:
            return row.owner_id == owner_id
        db.add(ScreeningSession(session_id=session_id, owner_id=owner_id, status="streaming", channel_type="app_ws"))
        try:
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False


async def _refuse(ws: WebSocket, code: str, detail: str, close_code: int) -> None:
    try:
        await ws.send_text(StreamV2Error(code=code, detail=detail).model_dump_json())
        await ws.close(code=close_code)
    except Exception:  # noqa: BLE001 — the client may already be gone
        pass


async def _start(ws: WebSocket, session_id: str):
    """Parse `start` and sign in. Returns (principal, start) or (None, None) after refusing."""
    from server.auth import AuthError, Principal, verify_token
    from server.ws_router import _SAFE_SESSION_ID

    if not _SAFE_SESSION_ID.fullmatch(session_id or ""):
        await _refuse(ws, "bad_request", "session id must be a plain name", POLICY_VIOLATION)
        return None, None
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=config.WS_AUTH_TIMEOUT_S)
        start = StreamV2Start.model_validate_json(raw)
    except Exception as e:  # noqa: BLE001
        await _refuse(ws, "bad_request", f"first message must be a v2 'start': {type(e).__name__}",
                      POLICY_VIOLATION)
        return None, None
    try:
        if start.token:
            principal = verify_token(start.token)
        elif config.AUTH_MODE == "dev":
            principal = Principal(owner_id=config.DEV_OWNER_ID, via="dev")
        else:
            raise AuthError("missing token")
    except AuthError as e:
        log.info(f"[{session_id}] v2 refused: {e}")
        await _refuse(ws, "unauthorized", "Sign in required.", POLICY_VIOLATION)
        return None, None
    return principal, start


@router.websocket("/screen/{session_id}")
async def ws_v2_screen(ws: WebSocket, session_id: str) -> None:
    from server.capacity import admission
    from server.pipeline.dispatcher import Dispatcher, build_dispatcher

    await ws.accept()
    principal, start = await _start(ws, session_id)
    if principal is None:
        return
    if not admission.try_acquire():
        await _refuse(ws, "busy", "The server is at capacity. Try again shortly.", TRY_AGAIN_LATER)
        return
    try:
        if not await asyncio.to_thread(_reserve_session, principal.owner_id, session_id):
            await _refuse(ws, "bad_request", "That session id is already in use.", POLICY_VIOLATION)
            return
        sink = V2ClientSink(ws, session_id)
        dispatcher = Dispatcher([sink] + build_dispatcher(ws=None).sinks)
        runner = make_runner(dispatcher, principal.owner_id)
        await runner.open(SessionOpen(session_id=session_id, source=AudioSource.APP_WS,
                                      caller_context=start.caller_context))
        await ws.send_text(StreamV2Ready(session_id=session_id, max_frame_bytes=MAX_FRAME_BYTES).model_dump_json())
        log.info(f"[{session_id}] v2 session started (client={start.client or '?'}, via={principal.via})")
        await _stream(ws, runner, session_id)
    finally:
        admission.release()


async def _stream(ws: WebSocket, runner, session_id: str) -> None:
    """Read at real time into a queue; score from the queue. Behind real time the newest
    frame is scored and the backlog is handed to the runner's catch-up (never dropped)."""
    queue: asyncio.Queue = asyncio.Queue()
    done = object()
    reason = "client disconnected"

    async def consume() -> None:
        while True:
            batch = [await queue.get()]
            while not queue.empty():
                batch.append(queue.get_nowait())
            last = max((i for i, item in enumerate(batch) if isinstance(item, AudioFrame)), default=-1)
            for i, item in enumerate(batch):
                if item is done:
                    return
                try:
                    await runner.push(item, score=(i == last))
                except Exception as e:  # noqa: BLE001 — keep consuming; log why
                    log.error(f"[{session_id}] v2 scoring step failed: {type(e).__name__}: {e}")

    consumer = asyncio.create_task(consume())
    seq, samples = 0, 0
    try:
        while True:
            message = await ws.receive()
            if message.get("type") == "websocket.disconnect":
                break
            data = message.get("bytes")
            if data is not None:
                if len(data) % 2 or not data or len(data) > MAX_FRAME_BYTES:
                    await ws.send_text(StreamV2Error(
                        code="bad_request",
                        detail=f"frame of {len(data)} bytes ignored: need 16 kHz s16le, even length, "
                               f"at most {MAX_FRAME_BYTES} bytes").model_dump_json())
                    continue
                queue.put_nowait(AudioFrame(session_id=session_id, seq=seq, t_start_s=samples / 16000,
                                            pcm_s16le=data))
                seq += 1
                samples += len(data) // 2
                continue
            try:
                kind = json.loads(message.get("text") or "{}").get("type")
            except ValueError:
                kind = None
            if kind == "end":
                reason = "client ended the call"
                break
            log.info(f"[{session_id}] v2: ignored a {kind!r} text message mid-call")
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        if not is_client_gone(e):
            log.error(f"[{session_id}] v2 read failed: {type(e).__name__}: {e}")
    queue.put_nowait(done)
    await consumer
    await runner.close(SessionClose(session_id=session_id, reason=reason))
    try:
        await ws.close(code=1000)
    except Exception:  # noqa: BLE001
        pass
    log.info(f"[{session_id}] v2 session closed ({reason}; {samples / 16000:.1f}s of audio)")
