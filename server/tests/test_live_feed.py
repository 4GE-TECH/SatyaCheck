"""The live feed: every runner verdict, pushed to dashboards and apps as it happens.

An Exotel call has no app socket of its own, so before this the only way to see it was a
guardian alert (on escalation only) or the report after the call. `/api/ws/live` streams
each verdict as one versioned JSON message; `docs/LIVE_FEED.md` is the contract the
frontends build against, so the message shape is pinned here field by field.

The tunnel URL is public and messages carry call transcripts, so when LIVE_FEED_TOKEN is
set the feed requires it (constant-time compare, 1008 on mismatch).
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

import config
from contracts import (
    AntiSpoofResult,
    CallerMetadata,
    ScriptAnalysisResult,
    SpeakerVerificationResult,
    TranscriptResult,
    create_mock_fixture,
)

VERDICT_KEYS = {
    "type", "schema_version", "session_id", "window_index", "is_final", "escalated", "timestamp",
    "band", "overlay_state", "trust_score", "risk_score", "mode", "signals", "reason_codes",
    "transcript", "language", "caller_context", "threat_label", "recommended_actions",
    "vernacular_warning",
}


def _event(band="red", **kw):
    from server.pipeline.dispatcher import VerdictEvent

    response = create_mock_fixture(band).model_copy(update={"session_id": "call-1"})
    return VerdictEvent(session_id="call-1", response=response, window_index=kw.get("i", 3),
                        escalated=kw.get("escalated", True), is_final=kw.get("final", False))


# --- the message ----------------------------------------------------------------------------

def test_a_verdict_message_has_exactly_the_documented_fields():
    from server.live_feed import verdict_message

    msg = verdict_message(_event())
    assert set(msg) == VERDICT_KEYS
    assert msg["type"] == "verdict" and msg["schema_version"] == 1
    assert (msg["session_id"], msg["window_index"], msg["is_final"], msg["escalated"]) == ("call-1", 3, False, True)
    assert msg["band"] == "high_risk" and msg["overlay_state"] == "red"
    assert msg["signals"] == {"identity": "match", "authenticity": "synthetic", "intent_risk": msg["signals"]["intent_risk"]}
    assert msg["transcript"].startswith("Papa emergency")
    assert msg["reason_codes"][0].keys() == {"code", "signal", "value", "threshold", "explanation", "severity"}
    assert msg["caller_context"] is None and msg["threat_label"] is None
    json.dumps(msg)  # must be plain JSON


def test_caller_context_and_threat_label_are_carried_when_present():
    from contracts import ThreatLabel
    from server.live_feed import verdict_message

    event = _event()
    fusion = event.response.fusion.model_copy(update={"threat_label": ThreatLabel(
        sector="banking", threat="KYC update fraud", family="kyc_update")})
    response = event.response.model_copy(update={
        "fusion": fusion, "caller_context": CallerMetadata(claimed_number="+911", channel_type="telephony")})
    msg = verdict_message(type(event)(**{**event.__dict__, "response": response}))
    assert msg["caller_context"]["channel_type"] == "telephony"
    assert msg["threat_label"] == {"sector": "banking", "threat": "KYC update fraud", "family": "kyc_update"}


def test_an_unavailable_spoof_branch_reads_unavailable_not_bonafide():
    from server.live_feed import verdict_message

    event = _event("green")
    spoof = AntiSpoofResult.neutral()
    spoof.details["available"] = False
    msg = verdict_message(type(event)(**{**event.__dict__,
                                         "response": event.response.model_copy(update={"spoof": spoof})}))
    assert msg["signals"]["authenticity"] == "unavailable"


# --- the endpoint and publishing ---------------------------------------------------------------

@pytest.fixture
def app_client(monkeypatch):
    from fastapi.testclient import TestClient

    import server.live_feed as lf
    from server.main import app

    monkeypatch.setattr(config, "LIVE_FEED_TOKEN", "")
    lf._subscribers.clear()
    with TestClient(app) as c:
        yield c
    lf._subscribers.clear()


def test_a_subscriber_gets_hello_then_every_published_verdict(app_client):
    from server.live_feed import verdict_message
    from server.pipeline.dispatcher import LiveFeedSink

    with app_client.websocket_connect("/api/ws/live") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["schema_version"] == 1
        for i, final in [(0, False), (1, True)]:
            event = _event(i=i, final=final)
            app_client.portal.call(LiveFeedSink().deliver, event)
            assert ws.receive_json() == verdict_message(event)


def test_publishing_with_no_subscribers_is_a_no_op():
    import server.live_feed as lf

    lf._subscribers.clear()
    asyncio.run(lf.publish({"type": "verdict"}))


def test_a_dead_subscriber_is_dropped_and_logged(caplog):
    import server.live_feed as lf

    class Dead:
        async def send_text(self, text):
            raise RuntimeError("socket gone")

    lf._subscribers.clear()
    lf._subscribers["dead"] = Dead()
    asyncio.run(lf.publish({"type": "verdict"}))
    assert "dead" not in lf._subscribers
    assert any("socket gone" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("query", ["", "?token=wrong", "?token="])
def test_a_set_token_is_required(app_client, monkeypatch, query):
    monkeypatch.setattr(config, "LIVE_FEED_TOKEN", "demo-secret")
    with pytest.raises(WebSocketDisconnect) as exc:
        with app_client.websocket_connect("/api/ws/live" + query) as ws:
            ws.receive_json()
    assert exc.value.code == 1008


def test_the_right_token_is_accepted(app_client, monkeypatch):
    monkeypatch.setattr(config, "LIVE_FEED_TOKEN", "demo-secret")
    with app_client.websocket_connect("/api/ws/live?token=demo-secret") as ws:
        assert ws.receive_json()["type"] == "hello"


# --- wiring: dispatcher defaults and an Exotel call end to end --------------------------------------

def test_the_live_feed_is_a_default_sink_and_rides_on_the_exotel_runner():
    import server.main

    assert "live_feed" in config.DISPATCH_SINKS
    names = [s.name for s in server.main._exotel_runner().dispatcher.sinks]
    assert "live_feed" in names and "app_overlay" not in names


def test_an_exotel_call_appears_on_the_live_feed(app_client, monkeypatch, tmp_path):
    import server.orchestrator as orch
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from acquisition.api import build_exotel_router
    from server.database import Base
    from server.pipeline.dispatcher import Dispatcher, LiveFeedSink
    from server.pipeline.runner import SessionRunner

    monkeypatch.setattr(config, "USE_REAL_SPEAKER", True)
    monkeypatch.setattr(config, "USE_REAL_SPOOF", True)
    monkeypatch.setattr(orch, "_real_speaker_branch", lambda p: SpeakerVerificationResult.neutral())
    monkeypatch.setattr(orch, "_real_spoof_branch", lambda p: AntiSpoofResult(risk=0.2, details={"available": True}))
    monkeypatch.setattr(config, "EXOTEL_BASIC_USER", "u")
    monkeypatch.setattr(config, "EXOTEL_BASIC_PASS", "p")
    monkeypatch.setattr(config, "EXOTEL_ALLOWED_IPS", [])
    engine = create_engine(f"sqlite:///{tmp_path / 'live.db'}")
    Base.metadata.create_all(engine)

    class Quiet:
        def push(self, chunk, sample_rate=16000):
            return TranscriptResult.empty()

        def flush(self):
            return TranscriptResult.empty()

    def factory():
        return SessionRunner(dispatcher=Dispatcher([LiveFeedSink()]), session_factory=sessionmaker(bind=engine),
                             transcriber_factory=Quiet, analyze=lambda t: ScriptAnalysisResult.neutral())

    exotel_app = FastAPI()
    exotel_app.include_router(build_exotel_router(factory))
    # The Exotel route shares this process's live-feed registry with the main app.
    t = np.arange(8000 * 5) / 8000
    pcm = (0.3 * np.sin(2 * np.pi * 220 * t) * ((t % 0.5) < 0.4) * 32767).astype("<i2").tobytes()
    msgs = [json.dumps({"event": "start", "stream_sid": "live-call",
                        "start": {"stream_sid": "live-call", "from": "+919876543210",
                                  "media_format": {"encoding": "raw", "sample_rate": "8000"}}})]
    for k, i in enumerate(range(0, len(pcm), 1600)):
        msgs.append(json.dumps({"event": "media", "sequence_number": k + 2, "stream_sid": "live-call",
                                "media": {"chunk": k + 1, "timestamp": k * 100,
                                          "payload": base64.b64encode(pcm[i:i + 1600]).decode()}}))
    msgs.append(json.dumps({"event": "stop", "stream_sid": "live-call", "stop": {"reason": "callended"}}))
    auth = {"authorization": "Basic " + base64.b64encode(b"u:p").decode()}

    with app_client.websocket_connect("/api/ws/live") as live:
        assert live.receive_json()["type"] == "hello"
        with TestClient(exotel_app) as exo, exo.websocket_connect(config.EXOTEL_WS_PATH, headers=auth) as call:
            for m in msgs:
                call.send_text(m)
            call.receive()
        received = []
        while not received or not received[-1]["is_final"]:
            received.append(live.receive_json())
    assert len(received) >= 3
    assert all(m["session_id"] == "live-call" for m in received)
    assert received[0]["caller_context"] == {"claimed_number": "+919876543210", "claimed_name": None,
                                             "claimed_identity": None, "channel_type": "telephony"}


# --- CORS for a dashboard that calls the tunnel directly --------------------------------------------

def test_extra_cors_origins_come_from_the_environment():
    out = subprocess.run(
        [sys.executable, "-c", "import config; print(config.CORS_ORIGINS)"],
        capture_output=True, text=True, cwd=str(config.REPO_ROOT), timeout=60,
        env={**os.environ, "SATYACHECK_CORS_ORIGINS": "https://dash.example.com, http://192.168.1.20:5173"},
    )
    assert "https://dash.example.com" in out.stdout and "http://192.168.1.20:5173" in out.stdout
    assert "http://localhost:5173" in out.stdout, out.stderr
