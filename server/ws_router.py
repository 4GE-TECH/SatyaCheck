"""SatyaCheck — WebSocket Streaming Router

Provides real-time audio screening over WebSocket.
Client sends 3s audio chunks; server rescores every ~2s.
Trust score is monotone-escalating within a session (can only decrease, never re-climb).

C owns this file.
"""

from __future__ import annotations

import asyncio
import base64
import io
import shutil
import logging
import re
import uuid
import wave
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import config
from contracts import (
    ScreeningResponse,
    StreamClientMessageType,
    StreamServerMessageType,
    StreamAudioChunkMessage,
    StreamScreeningUpdateMessage,
    TrustBand,
)
from server.audio_ingest import discard, ingest_audio
from server.escalation import EscalationGate
from server.database import SessionLocal, ScreeningSession, ScreeningResult
from server.guardian import publish_alert_from_response
from server.orchestrator import screen_audio

log = logging.getLogger("satyacheck.ws")
router = APIRouter(prefix="/api/ws", tags=["websocket"])

# A session id names a folder under data/sessions. The route takes it from the URL
# path, where %5C decodes to a backslash that survives as one segment, so anything
# but a plain name could write retained audio outside DATA_DIR.
_SAFE_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


def _session_audio_dir(session_id: str) -> Optional[Path]:
    """data/sessions/<id>, or None (logged) when the id is not a plain folder name."""
    if not _SAFE_SESSION_ID.fullmatch(session_id or ""):
        log.warning(f"session id {session_id!r} is not a plain folder name; "
                    f"not retaining its audio")
        return None
    return config.DATA_DIR / "sessions" / session_id


# TrustBand -> the four colours the overlay renders, matching the app's own mapping
# in satyacheck_mobile/lib/models.dart (`TrustBand.signal`). Kept here rather than in
# contracts.py because it is a presentation choice for this one client, not a shared
# contract field — a second client could map the same bands differently.
_OVERLAY_STATE = {
    TrustBand.VERIFIED: "green",
    TrustBand.CAUTION: "amber",
    TrustBand.SUSPICIOUS: "red",
    TrustBand.HIGH_RISK: "red",
    TrustBand.UNVERIFIED: "grey",
    TrustBand.INSUFFICIENT: "grey",
}


def _overlay_evidence(response: ScreeningResponse) -> Optional[str]:
    """The one line worth quoting on the overlay: the strongest incriminating marker's
    matched text — words the caller actually said — or None.

    The top playbook's `matched_excerpt` is deliberately not a fallback here: it is
    corpus text (nlp_rag/corpus), not the caller's words, and the overlay renders this
    field in quotation marks. It goes in the separate `pattern` field instead.
    """
    markers = response.script.incriminating_markers
    return markers[0].matched_text if markers else None


def _overlay_pattern(response: ScreeningResponse) -> Optional[str]:
    """The scam pattern the call most resembles (playbook title), for a non-quoted line."""
    playbooks = response.script.playbooks
    return playbooks[0].title if playbooks else None


def _build_overlay_update(session_id: str, response: ScreeningResponse) -> dict:
    return {
        "type": "overlay_update",
        "session_id": session_id,
        "state": _OVERLAY_STATE.get(response.fusion.band, "grey"),
        "signals": {
            "identity": response.speaker.verdict.value,
            "intent": response.script.risk,
            # AntiSpoofResult has no verdict string of its own (only the frozen
            # contract's `is_synthetic` bool); "unavailable" when the branch abstained
            # (details["available"] is the flag orchestrator.py itself sets and reads —
            # see server/orchestrator.py:64,108,188) matches how the other two demo
            # signals are worded, and is honest about the branch being a stub today.
            "authenticity": (
                "unavailable"
                if response.spoof.details.get("available", True) is False
                else ("synthetic" if response.spoof.is_synthetic else "bonafide")
            ),
        },
        "evidence": _overlay_evidence(response),
        "pattern": _overlay_pattern(response),
        "latency_ms": response.processing_time_ms,
    }


def _pcm_to_wav_bytes(samples: list[float], sample_rate: int) -> bytes:
    """Wrap normalised float samples in a RIFF header — ffmpeg cannot infer sample
    rate or bit depth from bare PCM. Mirrors `scripts/live_screen.py`'s `to_wav`."""
    import struct

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        clipped = (max(-1.0, min(1.0, s)) for s in samples)
        w.writeframes(struct.pack(f"<{len(samples)}h", *(int(s * 32767) for s in clipped)))
    return buf.getvalue()


class SessionState:
    """Rolling state maintained across chunks for a single screening session."""
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.chunk_index: int = 0
        self.last_response: Optional[ScreeningResponse] = None
        # Persistence then latch — see server/escalation.py. Read per session so a
        # changed config takes effect on the next call, not the next restart.
        self.escalation = EscalationGate(config.ESCALATION_PERSISTENCE_N)
        # Accumulated 16kHz mono float samples, across chunks. Each chunk is scored
        # against the trailing config.STREAM_CONTEXT_S seconds of this buffer, not in
        # isolation — see config.py's comment on why the app's small chunks would
        # otherwise feed Whisper hallucination-prone slivers.
        self.buffer: list[float] = []
        self.sample_rate: int = config.TARGET_SAMPLE_RATE

    def append_and_window(self, waveform: list[float], sample_rate: int) -> bytes:
        """Append decoded samples, trim to the trailing context window, return a WAV."""
        self.sample_rate = sample_rate or self.sample_rate
        self.buffer.extend(waveform)
        max_samples = int(config.STREAM_CONTEXT_S * self.sample_rate)
        if len(self.buffer) > max_samples:
            self.buffer = self.buffer[-max_samples:]
        return _pcm_to_wav_bytes(self.buffer, self.sample_rate)

    def update(self, response: ScreeningResponse) -> ScreeningResponse:
        """Apply session escalation: a warning band must persist for
        `config.ESCALATION_PERSISTENCE_N` windows, then neither trust nor band can
        improve within the session.

        Carrying the trust floor alone was not enough: the band comes from the current
        9 s window, so once the scam phrase scrolled out of it the band fell back to
        `unverified` and the overlay went red -> grey mid-call. `EscalationGate`
        latches the band the same way it latches the floor.
        """
        response = self.escalation.apply(response)
        self.last_response = response
        self.chunk_index += 1
        return response


@router.websocket("/screen/{session_id}")
async def ws_screen(ws: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for real-time audio screening.

    Protocol:
      Client → {"type": "audio_chunk", "session_id": "...", "chunk_index": N, "audio_base64": "...", "is_final": false}
      Server → {"type": "screening_update", "session_id": "...", "chunk_index": N, "response": {...}}
      Client → {"type": "reset_session"} to restart
    """
    if config.USE_PIPELINE_RUNNER:
        await _ws_screen_runner(ws, session_id)
        return
    await ws.accept()
    log.info(f"WS /screen connected: session={session_id}")
    state = SessionState(session_id)

    db = SessionLocal()
    try:
        # Create session record
        db_session = ScreeningSession(
            session_id=session_id,
            status="streaming",
            channel_type="speakerphone",
        )
        db.add(db_session)
        db.commit()

        while True:
            try:
                raw = await ws.receive_text()
            except WebSocketDisconnect:
                log.info(f"WS disconnected: session={session_id}")
                break

            try:
                msg = StreamAudioChunkMessage.model_validate_json(raw)
            except Exception as e:
                await ws.send_json({"type": "error", "detail": f"Invalid message: {e}"})
                continue

            if msg.type == StreamClientMessageType.RESET_SESSION:
                state = SessionState(session_id)
                await ws.send_json({"type": "info", "detail": "Session reset"})
                continue

            if msg.type != StreamClientMessageType.AUDIO_CHUNK:
                await ws.send_json({"type": "error", "detail": f"Unknown message type: {msg.type}"})
                continue

            # ── Decode and ingest chunk ────────────────────────────────
            try:
                audio_bytes = base64.b64decode(msg.audio_base64)
            except Exception:
                await ws.send_json({"type": "error", "detail": "Invalid base64 audio"})
                continue

            ingested = ingest_audio(audio_bytes=audio_bytes)

            # Keep the normalised audio for this session.
            #
            # Enrolling a voice and screening it must happen over the same acoustic chain,
            # or the cosine measures the channel instead of the speaker. Measured on this
            # setup: the same person enrolled close-mic and probed off a speakerphone
            # scores ~0.31, where a clean-channel probe of the same voiceprint scores
            # 0.9464. Enrolling from audio that arrived through a real call is the only way
            # to make those two conditions match, and that requires keeping the audio.
            #
            # ffmpeg already wrote a 16 kHz mono WAV per chunk and left it on disk, so this
            # is a copy, not a re-encode. `enroll_person` takes a list of WAV paths, which
            # is exactly the shape a session produces.
            if config.RETAIN_SESSION_AUDIO and ingested.normalized_wav_path:
                try:
                    session_dir = _session_audio_dir(session_id)
                    if session_dir is None:
                        raise ValueError("unsafe session id")
                    session_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(
                        ingested.normalized_wav_path,
                        session_dir / f"chunk_{msg.chunk_index:04d}.wav",
                    )
                except Exception as e:  # never break a live call over a debug artefact
                    log.warning(f"could not retain session audio: {e}")

            # ── Build the trailing context window and screen that, not the raw
            # chunk alone ───────────────────────────────────────────────────
            # A small chunk in isolation is fine for identity (ECAPA does not need
            # 9s), but Whisper on an isolated tail mid-sentence hallucinates fluent,
            # wrong sentences — see config.STREAM_CONTEXT_S. Both branches run on the
            # same window: the alternative (a separate, shorter window for identity)
            # was considered and dropped — identity scored correctly on 9-10s windows
            # in testing (0.5 to 3s per clip), so splitting windows bought nothing but
            # a second ffmpeg/quality-gate pass per chunk.
            window_wav = state.append_and_window(ingested.waveform, ingested.sample_rate)
            discard(ingested)  # copied above if retained; the buffer holds the samples
            windowed = ingest_audio(audio_bytes=window_wav)

            # ── Screen the window ──────────────────────────────────────
            # Load enrolled embeddings from DB
            from server.screen_router import _load_enrolled_embeddings
            enrolled = _load_enrolled_embeddings(db)

            try:
                response = await screen_audio(
                    audio=windowed,
                    enrolled_embeddings=enrolled,
                )
            finally:
                discard(windowed)
            response = response.model_copy(update={"session_id": session_id})

            # Apply monotone escalation
            response = state.update(response)

            # ── Persist chunk result ───────────────────────────────────
            db_result = ScreeningResult(
                session_id=session_id,
                chunk_index=state.chunk_index - 1,
                response_json=response.model_dump_json(),
                processing_ms=response.processing_time_ms,
                is_final=msg.is_final,
            )
            db.add(db_result)
            db.commit()

            # ── Send update to client ──────────────────────────────────
            update = StreamScreeningUpdateMessage(
                session_id=session_id,
                chunk_index=state.chunk_index - 1,
                response=response,
            )
            await ws.send_text(update.model_dump_json())

            # ── overlay_update ─────────────────────────────────────────
            # A second message, not a replacement: `screening_update` carries the full
            # ScreeningResponse (contracts.py, frozen) for anything that needs it; this
            # is only what the phone overlay renders, pre-flattened so the app does not
            # need to know contracts.py's shape to show a state and a quoted line.
            await ws.send_json(_build_overlay_update(session_id, response))

            # ── Guardian alert if HIGH_RISK ────────────────────────────
            if response.fusion.band in (TrustBand.HIGH_RISK, TrustBand.SUSPICIOUS):
                await publish_alert_from_response(response)

            if msg.is_final:
                db_session.status = "complete"
                db.commit()
                log.info(f"WS session complete: {session_id} (chunks={state.chunk_index})")
                break

    except Exception as e:
        log.exception(f"WS error for session {session_id}: {e}")
        try:
            await ws.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        db.close()
        try:
            await ws.close()
        except Exception:
            pass


# ── Pipeline runner path (config.USE_PIPELINE_RUNNER, item 5) ──────────────────

def _retain_pcm(session_id: str, pcm_s16le: bytes, chunk_index: int) -> None:
    """Runner path: write one decoded chunk (16 kHz mono s16le) to
    data/sessions/<id>/chunk_NNNN.wav — the same file the per-chunk path copies from
    ffmpeg's output, so enrolment-from-a-call reads either path's sessions alike."""
    if not config.RETAIN_SESSION_AUDIO or not pcm_s16le:
        return
    try:
        session_dir = _session_audio_dir(session_id)
        if session_dir is None:
            return
        session_dir.mkdir(parents=True, exist_ok=True)
        with wave.open(str(session_dir / f"chunk_{chunk_index:04d}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(config.TARGET_SAMPLE_RATE)
            w.writeframes(pcm_s16le)
    except Exception as e:  # never break a live call over a debug artefact
        log.warning(f"[{session_id}] could not retain session audio: {e}")


async def _ws_screen_runner(ws: WebSocket, session_id: str) -> None:
    """The same protocol as `ws_screen`, through `SessionRunner`.

    Each base64 WAV chunk is decoded to 16 kHz mono by `acquisition.api.AppWsDecoder`
    (continuing seq / t_start_s) and pushed as an `AudioFrame`; the transport is named
    only on `SessionOpen.source`. Verdicts arrive per
    window (every `STREAM_HOP_S` of audio), not per chunk, and the dispatcher's
    AppOverlaySink sends the two messages the app reads. The session closes on
    `is_final` or disconnect; either way exactly one final verdict is dispatched.
    """
    from acquisition.api import AppWsDecoder
    from contracts import AudioSource, SessionClose, SessionOpen
    from server.pipeline.dispatcher import build_dispatcher
    from server.pipeline.runner import SessionRunner

    await ws.accept()
    log.info(f"WS /screen connected (pipeline runner): session={session_id}")
    runner = SessionRunner(dispatcher=build_dispatcher(ws=ws))
    opened = SessionOpen(session_id=session_id, source=AudioSource.APP_WS)
    await runner.open(opened)
    decoder = AppWsDecoder(session_id)
    reason = "client disconnected"
    try:
        while True:
            try:
                raw = await ws.receive_text()
            except WebSocketDisconnect:
                log.info(f"WS disconnected: session={session_id}")
                break

            try:
                msg = StreamAudioChunkMessage.model_validate_json(raw)
            except Exception as e:
                await ws.send_json({"type": "error", "detail": f"Invalid message: {e}"})
                continue

            if msg.type == StreamClientMessageType.RESET_SESSION:
                await runner.close(SessionClose(session_id=session_id, reason="reset_session"))
                await runner.open(opened)
                decoder = AppWsDecoder(session_id)
                await ws.send_json({"type": "info", "detail": "Session reset"})
                continue

            if msg.type != StreamClientMessageType.AUDIO_CHUNK:
                await ws.send_json({"type": "error", "detail": f"Unknown message type: {msg.type}"})
                continue

            try:
                audio_bytes = base64.b64decode(msg.audio_base64)
            except Exception:
                await ws.send_json({"type": "error", "detail": "Invalid base64 audio"})
                continue

            frames = decoder.decode(audio_bytes, is_final=msg.is_final)
            if not frames:
                # acquisition logged why. An is_final chunk still ends the session below:
                # close() scores the tail and emits the one final verdict.
                log.warning(f"[{session_id}] chunk {msg.chunk_index} decoded to no audio")
            for frame in frames:
                _retain_pcm(session_id, frame.pcm_s16le, msg.chunk_index)
                await runner.push(frame)
            if msg.is_final:
                reason = "final chunk"
                log.info(f"WS session complete: {session_id} (frames={decoder.next_seq})")
                break

    except Exception as e:
        log.exception(f"WS error for session {session_id}: {e}")
        try:
            await ws.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        await runner.close(SessionClose(session_id=session_id, reason=reason))
        try:
            await ws.close()
        except Exception:
            pass


@router.websocket("/guardian")
async def ws_guardian(ws: WebSocket) -> None:
    """Guardian alert WebSocket. Connect to receive real-time alerts for HIGH_RISK sessions."""
    from server.guardian import subscribe, unsubscribe
    await ws.accept()
    conn_id = await subscribe(ws)
    log.info(f"Guardian WS connected: {conn_id}")
    try:
        # Keep connection alive — guardian only receives, never sends
        while True:
            await ws.receive_text()  # blocks until disconnect
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning(f"Guardian WS error: {e}")
    finally:
        unsubscribe(conn_id)
        log.info(f"Guardian WS disconnected: {conn_id}")
