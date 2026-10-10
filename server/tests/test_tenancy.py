"""Upgrade plan, Phase 1: account A can never read, change or match account B's data.

Two signed-in accounts (real RS256 tokens, server/tests/auth_helpers.py) against the
SQLite dev database. Postgres row-level security is the second line of defence; its own
tests live in test_rls_postgres.py and run when a Postgres URL is configured.
"""

from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import config
from contracts import QualityGateResult, create_mock_fixture
from server.tests.auth_helpers import signed_in  # noqa: F401  (fixture)
from server.tests.isolated_db import isolated_db  # noqa: F401  (fixture)

A, B = "account-a", "account-b"


def _unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(192).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def client(isolated_db, signed_in):
    from server.main import app

    c = TestClient(app)
    c.db = isolated_db
    c.accounts = signed_in
    return c


@pytest.fixture
def stub_enroll(monkeypatch):
    import audio_ml.api
    from server import enroll_router

    class _Ingested:
        audio_sha256 = "sha"
        normalized_wav_path = "fake.wav"
        quality = QualityGateResult(passed=True, speech_duration_s=20.0, snr_db=20.0)

    monkeypatch.setattr(audio_ml.api, "compute_voiceprint",
                        lambda paths, nb8k_real_paths=None: {"wb": _unit(1), "nb8k_sim": _unit(2), "n_samples": 1},
                        raising=False)
    monkeypatch.setattr(enroll_router, "ingest_audio", lambda audio_bytes: _Ingested())
    monkeypatch.setattr(enroll_router, "discard", lambda ingested: None)


def _enroll(client, owner, headers_extra=None, **form):
    headers = {**client.accounts.headers(owner), **(headers_extra or {})}
    return client.post("/api/enroll", data={"name": "Papa", "relation": "Father", **form}, headers=headers,
                       files={"file": ("a.wav", b"RIFF", "audio/wav")})


# --- contacts ----------------------------------------------------------------------------------

def test_contacts_are_invisible_and_untouchable_across_accounts(client):
    h_a, h_b = client.accounts.headers(A), client.accounts.headers(B)
    pid = client.post("/api/persons", params={"name": "Ma", "relation": "Mother"}, headers=h_a).json()["person_id"]

    assert [p["person_id"] for p in client.get("/api/persons", headers=h_a).json()] == [pid]
    assert client.get("/api/persons", headers=h_b).json() == []
    assert client.get(f"/api/persons/{pid}", headers=h_b).status_code == 404
    assert client.delete(f"/api/persons/{pid}", headers=h_b).status_code == 404
    assert client.get(f"/api/persons/{pid}", headers=h_a).status_code == 200, "B's delete must not land"


def test_no_route_answers_without_a_token(client):
    for method, path in [("get", "/api/persons"), ("post", "/api/persons?name=x&relation=y"),
                         ("get", "/api/screen/s1"), ("get", "/api/report/s1"), ("get", "/api/metrics"),
                         ("get", "/api/demo/status"), ("get", "/api/evidence/root")]:
        assert getattr(client, method)(path).status_code == 401, f"{method.upper()} {path}"


def test_enrollment_cannot_target_another_accounts_person(client, stub_enroll):
    pid = _enroll(client, A).json()["person_id"]
    r = _enroll(client, B, person_id=pid)
    assert r.status_code == 404
    with client.db() as db:
        from server.database import Voiceprint
        assert db.query(Voiceprint).count() == 2, "B's upload added vectors to A's person"


def test_idempotency_keys_do_not_cross_accounts(client, stub_enroll):
    first = _enroll(client, A, headers_extra={"Idempotency-Key": "same-key"})
    second = _enroll(client, B, headers_extra={"Idempotency-Key": "same-key"})
    assert first.status_code == second.status_code == 201
    assert first.json()["person_id"] != second.json()["person_id"], "B was handed A's enrollment"


def test_consent_is_recorded_per_account(client, stub_enroll):
    from server.database import ConsentRecord

    pid = _enroll(client, A, consent="true").json()["person_id"]
    with client.db() as db:
        rows = [(r.owner_id, r.person_id, r.consent_text_version, r.recorded_by) for r in db.query(ConsentRecord)]
    assert rows == [(A, pid, config.CONSENT_TEXT_VERSION, A)]


# --- results and reports -------------------------------------------------------------------

def _store_result(db_factory, owner, session_id="sess-a"):
    from server.database import ScreeningResult, ScreeningSession

    response = create_mock_fixture("red").model_copy(update={"session_id": session_id})
    with db_factory() as db:
        db.add(ScreeningSession(session_id=session_id, owner_id=owner, status="complete"))
        db.add(ScreeningResult(owner_id=owner, session_id=session_id, response_json=response.model_dump_json(),
                               processing_ms=1.0, is_final=True))
        db.commit()


def test_results_reports_and_metrics_are_per_account(client):
    _store_result(client.db, A)
    h_a, h_b = client.accounts.headers(A), client.accounts.headers(B)
    assert client.get("/api/screen/sess-a", headers=h_a).status_code == 200
    assert client.get("/api/screen/sess-a", headers=h_b).status_code == 404
    assert client.get("/api/report/sess-a", headers=h_b).status_code == 404
    assert client.get("/api/metrics", headers=h_a).json()["total_sessions"] == 1
    assert client.get("/api/metrics", headers=h_b).json()["total_sessions"] == 0


def test_demo_reset_clears_only_the_callers_sessions(client):
    _store_result(client.db, A, "sess-a")
    _store_result(client.db, B, "sess-b")
    assert client.post("/api/demo/reset", headers=client.accounts.headers(B)).json()["sessions_cleared"] == 1
    assert client.get("/api/screen/sess-a", headers=client.accounts.headers(A)).status_code == 200


# --- identity ----------------------------------------------------------------------------------

def test_a_screening_only_compares_against_its_own_accounts_voices(isolated_db):
    from server import voiceprint_store
    from server.database import Person
    from server.orchestrator import _speaker_candidates

    with isolated_db() as db:
        db.add(Person(person_id="pa", owner_id=A, name="A's papa", relation="Father"))
        db.add(Person(person_id="pb", owner_id=B, name="B's papa", relation="Father"))
        db.flush()
        voiceprint_store.save_voiceprints(db, A, "pa", {"wb": _unit(1)}, duration_s=20, snr_db=20)
        voiceprint_store.save_voiceprints(db, B, "pb", {"wb": _unit(2)}, duration_s=20, snr_db=20)
        voiceprint_store.add_flagged_voice(db, B, _unit(3), "kyc")
        db.commit()
    candidates, flagged = _speaker_candidates(A)
    assert [c["person_id"] for c in candidates] == ["pa"]
    assert flagged == [], "B's flagged list leaked into A's screening"


# --- sockets -----------------------------------------------------------------------------------

def test_the_screen_socket_refuses_a_client_that_does_not_authenticate(client):
    with client.websocket_connect("/api/ws/screen/sock-1") as ws:
        ws.send_text(json.dumps({"type": "audio_chunk", "session_id": "sock-1", "chunk_index": 0,
                                 "audio_base64": "UklGRg==", "is_final": True}))
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_text()
    assert closed.value.code == 1008


def test_a_session_id_owned_by_another_account_is_refused(client):
    from server.database import ScreeningSession

    with client.db() as db:
        db.add(ScreeningSession(session_id="taken", owner_id=A, status="complete"))
        db.commit()
    with client.websocket_connect("/api/ws/screen/taken") as ws:
        ws.send_text(json.dumps({"type": "auth", "token": client.accounts.token(B)}))
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_text()
    assert closed.value.code == 1008


class _Listener:
    def __init__(self):
        self.received = []

    async def send_text(self, text):
        self.received.append(text)


def test_guardian_alerts_reach_only_their_account():
    from server import guardian

    a, b = _Listener(), _Listener()
    ids = [asyncio.run(guardian.subscribe(a, A)), asyncio.run(guardian.subscribe(b, B))]
    try:
        asyncio.run(guardian.publish_alert_from_response(create_mock_fixture("red"), A))
        assert len(a.received) == 1 and b.received == []
    finally:
        for conn_id in ids:
            guardian.unsubscribe(conn_id)


def test_the_live_feed_reaches_only_its_account():
    from server import live_feed

    a, b = _Listener(), _Listener()
    ids = [live_feed.subscribe(a, A), live_feed.subscribe(b, B)]
    try:
        asyncio.run(live_feed.publish({"type": "verdict", "session_id": "x"}, A))
        assert len(a.received) == 1 and b.received == []
    finally:
        for conn_id in ids:
            live_feed.unsubscribe(conn_id)


# --- the reports list (Phase 5) ------------------------------------------------------------------

def test_the_reports_list_is_per_account_newest_first_and_paged(client):
    from datetime import datetime, timedelta, timezone

    from server.database import ScreeningResult, ScreeningSession

    base = datetime(2026, 10, 10, tzinfo=timezone.utc)
    response = create_mock_fixture("red")
    with client.db() as db:
        for k in range(5):
            sid = f"list-a-{k}"
            db.add(ScreeningSession(session_id=sid, owner_id=A, status="complete", created_at=base + timedelta(minutes=k)))
            db.add(ScreeningResult(owner_id=A, session_id=sid, is_final=True, processing_ms=1.0,
                                   response_json=response.model_copy(update={"session_id": sid}).model_dump_json()))
        db.add(ScreeningSession(session_id="list-b", owner_id=B, status="complete", created_at=base))
        db.commit()
    h = client.accounts.headers(A)
    first = client.get("/api/screen", params={"limit": 2}, headers=h).json()
    assert [i["session_id"] for i in first["items"]] == ["list-a-4", "list-a-3"]
    assert first["items"][0]["band"] == "high_risk" and first["items"][0]["trust_score"] is not None
    second = client.get("/api/screen", params={"limit": 2, "cursor": first["next_cursor"]}, headers=h).json()
    assert [i["session_id"] for i in second["items"]] == ["list-a-2", "list-a-1"]
    third = client.get("/api/screen", params={"limit": 2, "cursor": second["next_cursor"]}, headers=h).json()
    assert [i["session_id"] for i in third["items"]] == ["list-a-0"] and third["next_cursor"] is None
    other = client.get("/api/screen", headers=client.accounts.headers(B)).json()
    assert [i["session_id"] for i in other["items"]] == ["list-b"] and other["items"][0]["band"] is None
