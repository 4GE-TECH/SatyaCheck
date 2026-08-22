"""SatyaCheck — WebSocket Streaming Router

Provides real-time audio screening over WebSocket.
Client sends 3s audio chunks; server rescores every ~2s.
Trust score is monotone-escalating within a session (can only decrease, never re-climb).

C owns this file.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
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
from server.audio_ingest import ingest_audio
from server.database import SessionLocal, ScreeningSession, ScreeningResult
from server.guardian import publish_alert_from_response
from server.orchestrator import screen_audio

log = logging.getLogger("satyacheck.ws")
router = APIRouter(prefix="/api/ws", tags=["websocket"])


class SessionState:
    """Rolling state maintained across chunks for a single screening session."""
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.chunk_index: int = 0
        self.min_trust_score: float = 100.0  # monotone: only decreases
        self.last_response: Optional[ScreeningResponse] = None

    def update(self, response: ScreeningResponse) -> ScreeningResponse:
        """Apply monotone escalation: trust score can only decrease within a session."""
        current_score = response.fusion.trust_score
        if current_score < self.min_trust_score:
            self.min_trust_score = current_score
        elif current_score > self.min_trust_score:
            # Re-score shows improvement, but we keep the session floor
            response = response.model_copy(
                update={
                    "fusion": response.fusion.model_copy(
                        update={"trust_score": self.min_trust_score}
                    )
                }
            )
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

            # ── Screen the chunk ───────────────────────────────────────
            # Load enrolled embeddings from DB
            from server.screen_router import _load_enrolled_embeddings
            enrolled = _load_enrolled_embeddings(db)

            response = await screen_audio(
                audio=ingested,
                enrolled_embeddings=enrolled,
            )
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
