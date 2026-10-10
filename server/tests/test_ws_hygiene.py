"""Upgrade plan, Phase 0 step 7: a client that leaves mid-send is a normal close.

A phone that hangs up or loses signal while a verdict is being sent raised out of the
send, and the handler logged it with `log.exception` — a full traceback at ERROR for the
most ordinary event a live call has. Real failures drowned in that noise.

Now a gone client is logged once at INFO, with no traceback, everywhere we send.
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from starlette.websockets import WebSocketDisconnect
from uvicorn.protocols.utils import ClientDisconnected

from contracts import create_mock_fixture
from server.tests.isolated_db import isolated_db  # noqa: F401  (fixture)


def _gone_errors():
    from websockets.exceptions import ConnectionClosedOK

    return [
        WebSocketDisconnect(code=1001),
        ClientDisconnected(),
        ConnectionClosedOK(None, None),
        RuntimeError('Cannot call "send" once a close message has been sent.'),
        RuntimeError("Unexpected ASGI message 'websocket.send', after sending 'websocket.close' "
                     "or response already completed."),
    ]


@pytest.mark.parametrize("exc", _gone_errors(), ids=lambda e: type(e).__name__)
def test_a_departed_client_is_recognised(exc):
    from server.ws_util import is_client_gone

    assert is_client_gone(exc)


@pytest.mark.parametrize("exc", [ValueError("bad"), RuntimeError("model crashed"), KeyError("x")])
def test_real_errors_are_not_mistaken_for_a_departed_client(exc):
    from server.ws_util import is_client_gone

    assert not is_client_gone(exc)


def _no_noise(caplog):
    loud = [r for r in caplog.records if r.levelno >= logging.WARNING or r.exc_info]
    assert loud == [], [f"{r.levelname}: {r.getMessage()}" for r in loud]


class _LeavingSocket:
    """Delivers one audio chunk, then the client is gone when we try to answer."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._sent_chunk = False
        self.closed = False

    async def accept(self):
        pass

    async def receive_text(self):
        if self._sent_chunk:
            raise WebSocketDisconnect(code=1001)
        self._sent_chunk = True
        return json.dumps({"type": "audio_chunk", "session_id": self.session_id, "chunk_index": 0,
                           "audio_base64": "UklGRg==", "is_final": False})

    async def send_text(self, text):
        raise ClientDisconnected()

    async def send_json(self, data):
        raise ClientDisconnected()

    async def close(self, code: int = 1000):
        self.closed = True


def test_the_screen_socket_treats_a_departure_mid_send_as_a_normal_close(isolated_db, monkeypatch, caplog):
    import server.ws_router as ws_router

    class _Ingested:
        waveform = [0.0] * 1600
        sample_rate = 16000
        normalized_wav_path = None

    async def stub_screen(audio, caller_metadata=None, owner_id=None):
        return create_mock_fixture("unverified")

    monkeypatch.setattr(ws_router, "ingest_audio", lambda audio_bytes: _Ingested())
    monkeypatch.setattr(ws_router, "discard", lambda ingested: None)
    monkeypatch.setattr(ws_router, "screen_audio", stub_screen)
    monkeypatch.setattr(ws_router.SessionState, "append_and_window", lambda self, wf, sr: b"")
    monkeypatch.setattr(ws_router.config, "USE_PIPELINE_RUNNER", False)

    ws = _LeavingSocket("hygiene-1")
    with caplog.at_level(logging.INFO):
        asyncio.run(ws_router.ws_screen(ws, "hygiene-1"))
    _no_noise(caplog)
    assert any("hygiene-1" in r.getMessage() and "left" in r.getMessage() for r in caplog.records)


def test_the_app_overlay_sink_logs_a_departure_at_info(caplog):
    from server.pipeline.dispatcher import AppOverlaySink, Dispatcher, VerdictEvent

    sink = AppOverlaySink(_LeavingSocket("s"))
    event = VerdictEvent(session_id="s", window_index=3, response=create_mock_fixture("unverified"),
                         is_final=False)
    with caplog.at_level(logging.INFO):
        result = asyncio.run(Dispatcher([sink], timeout_s=1.0).dispatch(event))
    assert result == {"app_overlay": False}
    _no_noise(caplog)


def test_the_live_feed_drops_a_departed_dashboard_quietly(caplog):
    from server import live_feed

    conn_id = live_feed.subscribe(_LeavingSocket("x"))
    try:
        with caplog.at_level(logging.INFO):
            asyncio.run(live_feed.publish({"type": "verdict"}))
        assert conn_id not in live_feed._subscribers
        _no_noise(caplog)
    finally:
        live_feed.unsubscribe(conn_id)


def test_the_guardian_feed_drops_a_departed_subscriber_quietly(caplog):
    from server import guardian

    conn_id = asyncio.run(guardian.subscribe(_LeavingSocket("g")))
    try:
        with caplog.at_level(logging.INFO):
            asyncio.run(guardian.publish_alert_from_response(create_mock_fixture("red")))
        assert conn_id not in guardian._subscribers
        _no_noise(caplog)
    finally:
        guardian.unsubscribe(conn_id)
