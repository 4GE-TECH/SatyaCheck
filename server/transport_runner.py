"""Runners for transports with no app socket of their own (Exotel, WebRTC).

`make_retaining_runner(owner_id, dispatcher)` binds every session of the runner to one
account: the listener's for a WebRTC voice, EXOTEL_OWNER_ID for a telephony call.

C owns this file.
"""

from __future__ import annotations

import logging
from typing import Optional

import config
from server.pipeline.runner import SessionRunner

log = logging.getLogger("satyacheck.server")


class _RetainingRunner(SessionRunner):
    """A SessionRunner that, when RETAIN_SESSION_AUDIO is on, also writes the whole call to
    data/sessions/<id>/chunk_0000.wav — the file enrol_from_call globs, and the only way
    to replay a live call that scored oddly. The app WebSocket path retains its own chunks
    in ws_router; this is for transports with no such path (Exotel)."""

    def _part(self, session_id: str):
        from server.ws_router import _session_audio_dir

        d = _session_audio_dir(session_id)
        return None if d is None else d / "call.pcm.part"

    async def push(self, frame, score: bool = True):
        if config.RETAIN_SESSION_AUDIO and frame.pcm_s16le:
            try:
                part = self._part(frame.session_id)
                if part is not None:
                    part.parent.mkdir(parents=True, exist_ok=True)
                    with open(part, "ab") as f:
                        f.write(frame.pcm_s16le)
            except Exception as e:  # noqa: BLE001 — never break a live call over a debug artefact
                log.warning(f"[{frame.session_id}] could not retain call audio: {e}")
        events = await super().push(frame, score)
        if frame.is_final:
            self._seal(frame.session_id)
        return events

    async def close(self, msg):
        events = await super().close(msg)
        self._seal(msg.session_id)
        return events

    def _seal(self, session_id: str) -> None:
        import wave

        try:
            part = self._part(session_id)
            if part is None or not part.is_file():
                return
            with wave.open(str(part.with_name("chunk_0000.wav")), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(config.TARGET_SAMPLE_RATE)
                w.writeframes(part.read_bytes())
            part.unlink()
            log.info(f"[{session_id}] call audio retained at {part.with_name('chunk_0000.wav')}")
        except Exception as e:  # noqa: BLE001
            log.warning(f"[{session_id}] could not write retained call audio: {e}")


def make_retaining_runner(owner_id: Optional[str], dispatcher=None) -> "_RetainingRunner":
    """A runner whose sessions all belong to `owner_id`. Without a dispatcher, the guardian
    and report sinks only (no client socket to talk to)."""
    if dispatcher is None:
        from server.pipeline.dispatcher import build_dispatcher

        dispatcher = build_dispatcher(ws=None)
    return _RetainingRunner(dispatcher=dispatcher, owner_id=owner_id)
