"""Upgrade plan, Phase 3: the v2 live-screening protocol (/api/ws/v2/screen/{id}).

JSON `start` (sign-in + claims), BINARY 16 kHz s16le frames, JSON `end`. The server
answers `ready`, an `assessment` per window (current verdict kept apart from alerts, with
coverage and committed/tentative text), `alert`s, and the final assessment. No base64,
no ffmpeg on the live path. Models are stubbed.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import config
from contracts import (AntiSpoofResult, CallerMetadata, ScriptAnalysisResult, SpeakerVerificationResult,
                       StreamV2Start, TranscriptResult)
from server.tests.auth_helpers import signed_in  # noqa: F401  (fixture)
from server.tests.isolated_db import isolated_db  # noqa: F401  (fixture)

URL = "/api/ws/v2/screen/{}"


def _pcm(seconds: float) -> bytes:
    t = np.arange(int(16000 * seconds)) / 16000
    return (0.3 * np.sin(2 * np.pi * 220 * t) * ((t % 0.5) < 0.4) * 32767).astype("<i2").tobytes()


@pytest.fixture
def stubbed(monkeypatch, isolated_db):
    """Speaker unknown, anti-spoof clean, and a transcriber/analyzer the test controls."""
    import server.orchestrator as orch
    from server import ws_v2_router

    monkeypatch.setattr(config, "USE_REAL_SPEAKER", True)
    monkeypatch.setattr(config, "USE_REAL_SPOOF", True)
    monkeypatch.setattr(orch, "_real_speaker_branch", lambda p, owner_id=None: SpeakerVerificationResult.neutral())
    monkeypatch.setattr(orch, "_real_spoof_branch", lambda p: AntiSpoofResult(risk=0.05, details={"available": True}))
    state = {"script_risk": 0.0}

    class Words:
        tentative_text = "turant"

        def push(self, chunk, sample_rate=16000):
            return TranscriptResult(text="paise bhejo", detected_language="hi", confidence=0.9)

        def flush(self):
            return TranscriptResult(text="paise bhejo turant", detected_language="hi", confidence=0.9)

    def analyze(transcript):
        return ScriptAnalysisResult(risk=state["script_risk"], details={"available": True})

    real = ws_v2_router.make_runner
    monkeypatch.setattr(ws_v2_router, "make_runner",
                        lambda dispatcher, owner_id: real(dispatcher, owner_id, transcriber_factory=Words,
                                                          analyze=analyze))
    return state


def _start(**kw) -> str:
    return StreamV2Start(**kw).model_dump_json()


def _run_call(client, session_id, seconds=7.0, start=None, frame_s=0.5):
    """Send a whole call; return every server message until the final assessment."""
    messages = []
    with client.websocket_connect(URL.format(session_id)) as ws:
        ws.send_text(start or _start())
        messages.append(json.loads(ws.receive_text()))
        if messages[0]["type"] != "ready":
            return messages
        pcm = _pcm(seconds)
        step = int(16000 * 2 * frame_s)
        for i in range(0, len(pcm), step):
            ws.send_bytes(pcm[i:i + step])
        ws.send_text(json.dumps({"type": "end"}))
        while True:
            msg = json.loads(ws.receive_text())
            messages.append(msg)
            if msg["type"] == "assessment" and msg["is_final"]:
                return messages


def test_a_call_gets_ready_assessments_and_one_final(stubbed):
    from server.main import app

    messages = _run_call(TestClient(app), "v2-basic")
    assert messages[0]["type"] == "ready" and messages[0]["schema_version"] == 2
    assessments = [m for m in messages if m["type"] == "assessment"]
    assert assessments and sum(m["is_final"] for m in assessments) == 1
    final = assessments[-1]
    assert final["transcript_committed"] == "paise bhejo turant"
    assert final["coverage"] and all(span["scored"] for span in final["coverage"])
    assert final["coverage"][-1]["end_s"] == pytest.approx(7.0, abs=0.01)
    assert final["display_band"] == final["current"]["fusion"]["band"]
    assert assessments[0]["transcript_tentative"] == "turant"


def test_a_corroborated_warning_becomes_an_alert_that_outlives_its_window(stubbed):
    from server.main import app

    stubbed["script_risk"] = 0.95
    messages = _run_call(TestClient(app), "v2-alert")
    alerts = [m for m in messages if m["type"] == "alert"]
    assert alerts and alerts[0]["band"] == "high_risk" and alerts[0]["evidence"]
    final = [m for m in messages if m["type"] == "assessment"][-1]
    assert final["display_band"] == "high_risk"
    assert [a["alert_id"] for a in final["alerts"]] == [alerts[0]["alert_id"]]


def test_jwt_mode_refuses_a_start_without_a_token(stubbed, signed_in):
    from server.main import app

    with TestClient(app).websocket_connect(URL.format("v2-anon")) as ws:
        ws.send_text(_start())
        error = json.loads(ws.receive_text())
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_text()
    assert error == {"type": "error", "code": "unauthorized", "detail": error["detail"]}
    assert closed.value.code == 1008


def test_jwt_mode_accepts_a_token_in_the_start_message(stubbed, signed_in):
    from server.main import app

    messages = _run_call(TestClient(app), "v2-signed", seconds=3.0, start=_start(token=signed_in.token("acct-1")))
    assert messages[0]["type"] == "ready"
    assert any(m["type"] == "assessment" and m["is_final"] for m in messages)


def test_a_full_server_answers_busy(stubbed, monkeypatch):
    from server.main import app

    monkeypatch.setattr(config, "MAX_LIVE_SESSIONS", 0)
    with TestClient(app).websocket_connect(URL.format("v2-busy")) as ws:
        ws.send_text(_start())
        error = json.loads(ws.receive_text())
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_text()
    assert error["code"] == "busy" and closed.value.code == 1013


def test_a_malformed_frame_is_reported_and_the_call_goes_on(stubbed):
    from server.main import app

    with TestClient(app).websocket_connect(URL.format("v2-odd")) as ws:
        ws.send_text(_start())
        assert json.loads(ws.receive_text())["type"] == "ready"
        ws.send_bytes(b"\x01\x02\x03")                       # odd length: not s16le
        assert json.loads(ws.receive_text())["code"] == "bad_request"
        pcm = _pcm(3.0)
        for i in range(0, len(pcm), 16000):                 # 0.5 s frames
            ws.send_bytes(pcm[i:i + 16000])
        ws.send_text(json.dumps({"type": "end"}))
        final = None
        while final is None:
            msg = json.loads(ws.receive_text())
            if msg["type"] == "assessment" and msg["is_final"]:
                final = msg
    assert final["coverage"][-1]["end_s"] == pytest.approx(3.0, abs=0.01)


def test_a_session_id_owned_by_another_account_is_refused(stubbed, signed_in, isolated_db):
    from server.database import ScreeningSession
    from server.main import app

    with isolated_db() as db:
        db.add(ScreeningSession(session_id="v2-taken", owner_id="someone-else", status="complete"))
        db.commit()
    with TestClient(app).websocket_connect(URL.format("v2-taken")) as ws:
        ws.send_text(_start(token=signed_in.token("acct-1")))
        error = json.loads(ws.receive_text())
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_text()
    assert error["code"] == "bad_request" and closed.value.code == 1008


def test_claims_in_the_start_message_reach_identity(stubbed, isolated_db):
    """The caller context rides the session; a claim with no voiceprint is reported, not scored."""
    from server.database import Person
    from server.main import app

    with isolated_db() as db:
        db.add(Person(person_id="p_papa", owner_id=config.DEV_OWNER_ID, name="Ramesh", relation="Father"))
        db.commit()
    start = _start(caller_context=CallerMetadata(claimed_identity="p_papa", channel_type="speakerphone"))
    messages = _run_call(TestClient(app), "v2-claim", seconds=3.0, start=start)
    final = [m for m in messages if m["type"] == "assessment"][-1]
    assert final["current"]["speaker"]["details"]["claim_check"]["outcome"] == "no_voiceprint"
    assert final["claim_rev"] >= 1


def test_an_oversized_frame_is_refused_not_truncated(stubbed):
    from server.main import app

    with TestClient(app).websocket_connect(URL.format("v2-big")) as ws:
        ws.send_text(_start())
        assert json.loads(ws.receive_text())["type"] == "ready"
        ws.send_bytes(_pcm(3.0))                               # one 3 s frame: over the limit
        error = json.loads(ws.receive_text())
        ws.send_text(json.dumps({"type": "end"}))
    assert error["code"] == "bad_request" and "at most" in error["detail"]
