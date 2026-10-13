"""The admin console's API (server/admin_router.py): only listed admins, every account,
read-only, every view logged."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import config
from contracts import create_mock_fixture
from server.tests.auth_helpers import signed_in  # noqa: F401  (fixture)
from server.tests.isolated_db import isolated_db  # noqa: F401  (fixture)

ADMIN, ALICE, BOB = "admin-1", "alice", "bob"


@pytest.fixture
def client(isolated_db, signed_in, monkeypatch):   # noqa: F811
    from server.main import app

    monkeypatch.setattr(config, "ADMIN_USER_IDS", frozenset({ADMIN}))
    c = TestClient(app)
    c.as_ = signed_in.headers
    c.token = signed_in.token
    c.db = isolated_db
    return c


def _call(db_factory, owner, session_id, fixture="red", text="beta paise bhejo jaldi", windows=2):
    from server.database import ScreeningResult, ScreeningSession

    created = datetime.now(timezone.utc) - timedelta(minutes=5)
    response = create_mock_fixture(fixture)
    response = response.model_copy(update={"session_id": session_id,
                                           "transcript": response.transcript.model_copy(update={"text": text})})
    with db_factory() as db:
        db.add(ScreeningSession(session_id=session_id, owner_id=owner, status="complete", channel_type="webrtc",
                                created_at=created))
        for i in range(windows):
            db.add(ScreeningResult(owner_id=owner, session_id=session_id, chunk_index=i, processing_ms=1.0,
                                   is_final=(i == windows - 1), response_json=response.model_dump_json(),
                                   created_at=created + timedelta(seconds=i)))
        db.commit()


def _profile(db_factory, owner, username):
    from server.database import Profile

    with db_factory() as db:
        db.add(Profile(owner_id=owner, username=username, display_name=username.title()))
        db.commit()


def test_signed_out_and_ordinary_accounts_are_refused(client, monkeypatch):
    assert client.get("/api/admin/me").status_code == 401
    assert client.get("/api/admin/me", headers=client.as_(ALICE)).status_code == 403
    assert client.get("/api/admin/screenings", headers=client.as_(ALICE)).status_code == 403
    assert client.get("/api/admin/me", headers=client.as_(ADMIN)).json() == {"user_id": ADMIN, "admin": True}


def test_the_dev_account_is_never_an_admin(isolated_db, monkeypatch):   # noqa: F811
    from server.main import app

    monkeypatch.setattr(config, "AUTH_MODE", "dev")
    monkeypatch.setattr(config, "ADMIN_USER_IDS", frozenset({config.DEV_OWNER_ID}))
    assert TestClient(app).get("/api/admin/me").status_code == 401


def test_an_admin_sees_every_accounts_calls_with_who_made_them(client):
    _profile(client.db, ALICE, "alice")
    _call(client.db, ALICE, "rtc_a_caller", text="main police station mein hoon")
    _call(client.db, BOB, "rtc_b_callee", fixture="green", text="hello beta")
    items = client.get("/api/admin/screenings", headers=client.as_(ADMIN)).json()["items"]
    by_id = {i["session_id"]: i for i in items}
    assert set(by_id) == {"rtc_a_caller", "rtc_b_callee"}
    assert by_id["rtc_a_caller"]["owner"]["username"] == "alice"
    assert by_id["rtc_b_callee"]["owner"]["username"] is None          # no username: shown by id
    assert by_id["rtc_a_caller"]["transcript_preview"].startswith("main police")
    only_alice = client.get("/api/admin/screenings", params={"owner": ALICE}, headers=client.as_(ADMIN)).json()
    assert [i["session_id"] for i in only_alice["items"]] == ["rtc_a_caller"]


def test_a_calls_detail_has_its_transcript_verdict_and_how_it_moved(client):
    _call(client.db, ALICE, "rtc_a_caller", windows=3)
    detail = client.get("/api/admin/screenings/rtc_a_caller", headers=client.as_(ADMIN)).json()
    assert detail["response"]["transcript"]["text"] == "beta paise bhejo jaldi"
    assert [t["chunk_index"] for t in detail["timeline"]] == [0, 1, 2] and detail["timeline"][-1]["is_final"]
    assert client.get("/api/admin/screenings/nope", headers=client.as_(ADMIN)).status_code == 404


def test_users_and_overview_count_across_accounts(client):
    _profile(client.db, ALICE, "alice")
    _call(client.db, ALICE, "a1")
    _call(client.db, BOB, "b1")
    users = {u["user_id"]: u for u in client.get("/api/admin/users", headers=client.as_(ADMIN)).json()["users"]}
    assert users[ALICE]["calls"] == 1 and users[ALICE]["username"] == "alice" and users[BOB]["calls"] == 1
    overview = client.get("/api/admin/overview", headers=client.as_(ADMIN)).json()
    assert overview["screenings_24h"] == 2 and overview["accounts_with_calls"] == 2
    assert sum(overview["bands_24h"].values()) == 2


def test_every_admin_view_is_logged_with_the_admins_id(client, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="satyacheck.admin")
    client.get("/api/admin/screenings", headers=client.as_(ADMIN))
    assert any(f"admin {ADMIN} viewed the call list" in r.getMessage() for r in caplog.records)


def test_live_calls_show_both_people_and_what_each_listener_sees(client, monkeypatch):
    from server import webrtc_calls, webrtc_screening

    reg = webrtc_calls.CallRegistry()
    monkeypatch.setattr(webrtc_calls, "registry", reg)
    _profile(client.db, ALICE, "alice")
    _profile(client.db, BOB, "bob")
    call = reg.create(ALICE, BOB)
    reg.accept(call.call_id, BOB)

    class _Manager:
        def running(self, call_id):
            return True

        def voice_states(self, call_id):
            return [{"session_id": f"rtc_{call_id}_caller", "speaker_id": ALICE, "listener_id": BOB,
                     "state": {"display_band": "suspicious", "transcript_tail": "paise bhejo"}}]

    monkeypatch.setattr(webrtc_screening, "manager", _Manager())
    calls = client.get("/api/admin/calls/live", headers=client.as_(ADMIN)).json()["calls"]
    assert len(calls) == 1 and calls[0]["status"] == "active"
    assert (calls[0]["caller"]["username"], calls[0]["callee"]["username"]) == ("alice", "bob")
    assert calls[0]["voices"][0]["state"]["transcript_tail"] == "paise bhejo"


def test_the_admin_live_feed_gets_every_accounts_verdicts_labelled(client):
    from server import live_feed
    from server.main import app

    with TestClient(app) as running, running.websocket_connect("/api/admin/ws/live") as ws:
        ws.send_json({"type": "auth", "token": client.token(ADMIN)})
        assert ws.receive_json()["type"] == "hello"
        for owner in (ALICE, BOB):
            running.portal.call(live_feed.publish, {"type": "verdict", "session_id": f"s-{owner}"}, owner)
            got = ws.receive_json()
            assert got["session_id"] == f"s-{owner}" and got["owner_id"] == owner


def test_an_ordinary_subscriber_still_sees_only_its_own_account():
    from server import live_feed

    sent = {}

    class Sock:
        def __init__(self, name):
            self.name = name

        async def send_text(self, text):
            sent.setdefault(self.name, []).append(text)

    live_feed._subscribers.clear()
    live_feed.subscribe(Sock("alice"), ALICE)
    live_feed.subscribe(Sock("admin"), live_feed.ADMIN)
    asyncio.run(live_feed.publish({"type": "verdict", "session_id": "s-bob"}, BOB))
    assert "alice" not in sent and len(sent["admin"]) == 1
    live_feed._subscribers.clear()
    live_feed._admins.clear()


def test_a_non_admin_is_refused_on_the_admin_live_feed(client):
    with client.websocket_connect("/api/admin/ws/live") as ws:
        ws.send_json({"type": "auth", "token": client.token(ALICE)})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 1008
