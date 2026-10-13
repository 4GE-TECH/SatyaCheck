"""App-to-app call endpoints: verified accounts only, calls only between connections, only
the callee answers, phones that cannot forge verdicts, and no existence leaks
(server/webrtc_router.py, server/webrtc_calls.py)."""

from __future__ import annotations

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from server.tests.auth_helpers import signed_in  # noqa: F401  (fixture)

SECRET = "test-livekit-secret-that-is-long-enough-for-hs256"


class _NoAgents:
    """Stands in for AgentManager: no LiveKit server in unit tests."""

    def __init__(self):
        self.started, self.bound, self.stopped = [], [], []

    def start(self, call):
        self.started.append(call.call_id)
        return True

    def bind_listener(self, call):
        self.bound.append((call.call_id, call.callee_id))

    async def stop(self, call_id, reason="call ended"):
        self.stopped.append(call_id)

    def running(self, call_id):
        return call_id in self.started and call_id not in self.stopped


@pytest.fixture
def api(signed_in, monkeypatch):   # noqa: F811
    from server import webrtc_calls, webrtc_screening
    from server.main import mount_webrtc

    monkeypatch.setattr(config, "ENABLE_WEBRTC", True)
    monkeypatch.setattr(config, "LIVEKIT_API_KEY", "devkey")
    monkeypatch.setattr(config, "LIVEKIT_API_SECRET", SECRET)
    monkeypatch.setattr(config, "LIVEKIT_URL", "wss://livekit.example")
    monkeypatch.setattr(webrtc_calls, "registry", webrtc_calls.CallRegistry())
    import server.webrtc_router as router_module

    monkeypatch.setattr(router_module, "registry", webrtc_calls.registry)
    agents = _NoAgents()
    monkeypatch.setattr(webrtc_screening, "manager", agents)
    app = FastAPI()
    assert mount_webrtc(app)
    client = TestClient(app)
    client.agents = agents
    client.headers_for = signed_in.headers
    return client


def _connect(*pairs) -> None:
    """Give each account a username and connect each pair, straight in the database."""
    from server import database

    names = sorted({who for pair in pairs for who in pair})
    with database.owner_session("setup") as db:
        for who in names:
            db.add(database.Profile(owner_id=who, username=who, display_name=who.title()))
        for i, (a, b) in enumerate(pairs):
            db.add(database.Connection(connection_id=f"c{i}", requester_id=a, addressee_id=b,
                                       pair_key=database.pair_key(a, b), status="accepted"))
        db.commit()


def _ring(api, caller="alice", callee="bob") -> dict:
    r = api.post("/api/webrtc/calls", json={"callee_id": callee}, headers=api.headers_for(caller))
    assert r.status_code == 201, r.text
    return r.json()


def _grants(token: str) -> dict:
    claims = jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_aud": False})
    return claims


def test_not_mounted_in_dev_auth_mode(monkeypatch):
    from server.main import mount_webrtc

    monkeypatch.setattr(config, "ENABLE_WEBRTC", True)
    monkeypatch.setattr(config, "AUTH_MODE", "dev")
    monkeypatch.setattr(config, "LIVEKIT_API_KEY", "k")
    monkeypatch.setattr(config, "LIVEKIT_API_SECRET", "s")
    app = FastAPI()
    assert mount_webrtc(app) is False
    client = TestClient(app)
    assert client.post("/api/webrtc/calls", json={"callee_id": "bob"}).status_code == 404
    assert client.get("/api/users/search?q=bo").status_code == 404


def test_an_unsigned_request_is_refused(api):
    assert api.post("/api/webrtc/calls", json={"callee_id": "bob"}).status_code == 401
    assert api.get("/api/webrtc/incoming").status_code == 401
    assert api.post("/api/webrtc/calls/abc/accept").status_code == 401


def test_you_can_ring_only_a_connection(api):
    _connect(("alice", "bob"))
    r = api.post("/api/webrtc/calls", json={"callee_id": "carol"}, headers=api.headers_for("alice"))
    assert r.status_code == 403
    assert api.agents.started == []


def test_the_callee_sees_it_ringing_and_answers_with_their_own_token(api):
    _connect(("alice", "bob"))
    placed = _ring(api)
    assert placed["other"] == {"user_id": "bob", "username": "bob", "display_name": "Bob"}
    assert api.get("/api/webrtc/incoming", headers=api.headers_for("alice")).json()["calls"] == []
    ringing = api.get("/api/webrtc/incoming", headers=api.headers_for("bob")).json()["calls"]
    assert [c["call_id"] for c in ringing] == [placed["call_id"]]
    assert ringing[0]["caller"]["username"] == "alice" and ringing[0]["rings_for_s"] > 0
    state = api.get(f"/api/webrtc/calls/{placed['call_id']}", headers=api.headers_for("alice")).json()
    assert (state["status"], state["other_joined"]) == ("ringing", False)

    answered = api.post(f"/api/webrtc/calls/{placed['call_id']}/accept", headers=api.headers_for("bob")).json()
    a, b = _grants(placed["token"]), _grants(answered["token"])
    assert (a["sub"], b["sub"]) == ("alice", "bob")
    for g in (a["video"], b["video"]):
        assert g["room"] == f"satyacheck-{placed['call_id']}" and g["roomJoin"] is True
        assert g["canPublishData"] is False and g["canPublishSources"] == ["microphone"]
    assert placed["agent_identity"] == answered["agent_identity"] == f"satyacheck-agent-{placed['call_id']}"
    assert answered["other"]["username"] == "alice"
    assert api.agents.bound == [(placed["call_id"], "bob")]
    state = api.get(f"/api/webrtc/calls/{placed['call_id']}", headers=api.headers_for("alice")).json()
    assert (state["status"], state["other_joined"]) == ("active", True)
    assert api.get("/api/webrtc/incoming", headers=api.headers_for("bob")).json()["calls"] == []


def test_the_agent_is_visible_publishes_data_and_never_media():
    """Visible on purpose: a hidden agent's packets arrive with no sender, so clients could
    not verify them (found by scripts/webrtc_smoke.py)."""
    from server.webrtc_calls import CallRegistry
    from server.webrtc_screening import agent_token

    call = CallRegistry().create("alice", "bob")
    old = (config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET)
    config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET = "devkey", SECRET
    try:
        g = _grants(agent_token(call))["video"]
    finally:
        config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET = old
    assert not g.get("hidden") and g["canPublishData"] is True and g["canPublish"] is False


def test_only_the_callee_can_answer_and_only_once(api):
    _connect(("alice", "bob"))
    call_id = _ring(api)["call_id"]
    for who in ("alice", "mallory"):
        assert api.post(f"/api/webrtc/calls/{call_id}/accept", headers=api.headers_for(who)).status_code == 404
    assert api.post(f"/api/webrtc/calls/{call_id}/accept", headers=api.headers_for("bob")).status_code == 200
    assert api.post(f"/api/webrtc/calls/{call_id}/accept", headers=api.headers_for("bob")).status_code == 404


def test_declining_ends_the_call_and_stops_its_agent(api):
    _connect(("alice", "bob"))
    call_id = _ring(api)["call_id"]
    assert api.post(f"/api/webrtc/calls/{call_id}/decline", headers=api.headers_for("bob")).status_code == 204
    state = api.get(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("alice")).json()
    assert (state["ended"], state["ended_reason"]) == (True, "declined")
    assert api.agents.stopped == [call_id]


def test_an_unanswered_call_is_missed_and_its_agent_stopped(api, monkeypatch):
    from server import webrtc_calls

    _connect(("alice", "bob"))
    now = [1000.0]
    monkeypatch.setattr(webrtc_calls.registry, "clock", lambda: now[0])
    call_id = _ring(api)["call_id"]
    now[0] += config.WEBRTC_RING_TIMEOUT_S + 1
    assert api.get("/api/webrtc/incoming", headers=api.headers_for("bob")).json()["calls"] == []
    state = api.get(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("alice")).json()
    assert state["ended_reason"] == "missed"
    assert api.agents.stopped == [call_id]
    assert api.post(f"/api/webrtc/calls/{call_id}/accept", headers=api.headers_for("bob")).status_code == 404


def test_someone_in_a_call_is_busy(api):
    _connect(("alice", "bob"), ("carol", "bob"), ("alice", "carol"))
    _ring(api)
    assert api.post("/api/webrtc/calls", json={"callee_id": "bob"}, headers=api.headers_for("carol")).status_code == 409
    assert api.post("/api/webrtc/calls", json={"callee_id": "carol"}, headers=api.headers_for("alice")).status_code == 409


def test_another_accounts_call_is_simply_not_found(api):
    _connect(("alice", "bob"))
    call_id = _ring(api)["call_id"]
    assert api.get(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("alice")).json()["role"] == "caller"
    assert api.get(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("bob")).json()["role"] == "callee"
    assert api.get(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("mallory")).status_code == 404
    assert api.delete(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("mallory")).status_code == 404


def test_calls_beyond_capacity_are_refused(api, monkeypatch):
    monkeypatch.setattr(config, "WEBRTC_MAX_CALLS", 1)
    _connect(("alice", "bob"), ("carol", "dave"))
    _ring(api)
    assert api.post("/api/webrtc/calls", json={"callee_id": "dave"}, headers=api.headers_for("carol")).status_code == 503


def test_cancelling_and_hanging_up_stop_the_agent(api):
    _connect(("alice", "bob"))
    call_id = _ring(api)["call_id"]
    assert api.delete(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("alice")).status_code == 204
    assert api.agents.stopped == [call_id]
    state = api.get(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("bob")).json()
    assert (state["ended"], state["ended_reason"]) == (True, "cancelled")

    call_id = _ring(api)["call_id"]
    api.post(f"/api/webrtc/calls/{call_id}/accept", headers=api.headers_for("bob"))
    assert api.delete(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("bob")).status_code == 204
    assert api.get(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("alice")).json()["ended_reason"] == "hung_up"


def test_an_answered_call_that_nobody_ends_times_out_and_frees_both_people(monkeypatch):
    """The backstop when the agent itself died: nothing else would end the call, and both
    people would stay busy for good."""
    from server.webrtc_calls import CallRegistry

    now = [0.0]
    r = CallRegistry(clock=lambda: now[0])
    call = r.create("alice", "bob")
    r.accept(call.call_id, "bob")
    now[0] += config.WEBRTC_MAX_CALL_S + 1
    assert r.get_for(call.call_id, "alice").ended_reason == "timed_out"
    assert r.drain_ended() == [call.call_id]               # its agent gets stopped
    assert r.create("alice", "carol").status == "ringing"  # alice is free again
    assert r.end_unattended(call.call_id, "dropped") is None   # already over: a no-op


def test_the_agent_can_end_an_answered_call_nobody_hung_up():
    from server.webrtc_calls import CallRegistry

    r = CallRegistry()
    call = r.create("alice", "bob")
    r.accept(call.call_id, "bob")
    assert r.end_unattended(call.call_id, "dropped").ended_reason == "dropped"
    assert r.end_unattended(call.call_id, "dropped") is None
    assert r.create("bob", "alice").status == "ringing"


def test_a_party_can_rejoin_a_live_call_with_a_fresh_token(api):
    """Room tokens are short-lived; a phone that dropped for good on a long call gets a new
    one for the same room, as itself, while the call is live, and only then."""
    _connect(("alice", "bob"))
    placed = _ring(api)
    call_id = placed["call_id"]
    rejoin = lambda who: api.post(f"/api/webrtc/calls/{call_id}/rejoin", headers=api.headers_for(who))   # noqa: E731

    assert rejoin("alice").status_code == 200                     # the caller, while it rings
    assert rejoin("bob").status_code == 404                       # the callee must answer, not rejoin
    api.post(f"/api/webrtc/calls/{call_id}/accept", headers=api.headers_for("bob"))
    for who, other in (("alice", "bob"), ("bob", "alice")):
        r = rejoin(who)
        assert r.status_code == 200, r.text
        ticket = r.json()
        grant = _grants(ticket["token"])
        assert grant["sub"] == who and grant["video"]["room"] == f"satyacheck-{call_id}"
        assert grant["video"]["canPublishData"] is False
        assert ticket["agent_identity"] == placed["agent_identity"] and ticket["other"]["user_id"] == other
    assert rejoin("mallory").status_code == 404                   # not a party: same as no call
    api.delete(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("alice"))
    assert rejoin("alice").status_code == 404                     # over: no way back in
