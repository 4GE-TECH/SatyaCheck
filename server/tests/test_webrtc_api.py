"""App-to-app call endpoints: verified accounts only, phones that cannot forge verdicts,
single-use codes, and no existence leaks (server/webrtc_router.py, server/webrtc_calls.py)."""

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
    assert TestClient(app).post("/api/webrtc/calls").status_code == 404


def test_an_unsigned_request_is_refused(api):
    assert api.post("/api/webrtc/calls").status_code == 401
    assert api.post("/api/webrtc/calls/ABCDEFGH/join").status_code == 401


def test_two_accounts_get_distinct_identities_and_phones_cannot_publish_data(api):
    created = api.post("/api/webrtc/calls", headers=api.headers_for("alice")).json()
    joined = api.post(f"/api/webrtc/calls/{created['code']}/join", headers=api.headers_for("bob")).json()
    a, b = _grants(created["token"]), _grants(joined["token"])
    assert (a["sub"], b["sub"]) == ("alice", "bob")
    for g in (a["video"], b["video"]):
        assert g["room"] == f"satyacheck-{created['call_id']}" and g["roomJoin"] is True
        assert g["canPublishData"] is False and g["canPublishSources"] == ["microphone"]
    assert created["agent_identity"] == joined["agent_identity"] == f"satyacheck-agent-{created['call_id']}"
    assert api.agents.bound == [(created["call_id"], "bob")]


def test_the_agent_is_visible_publishes_data_and_never_media():
    """Visible on purpose: a hidden agent's packets arrive with no sender, so clients could
    not verify them (found by scripts/webrtc_smoke.py)."""
    from server.webrtc_calls import CallRegistry
    from server.webrtc_screening import agent_token

    call = CallRegistry().create("alice")
    old = (config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET)
    config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET = "devkey", SECRET
    try:
        g = _grants(agent_token(call))["video"]
    finally:
        config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET = old
    assert not g.get("hidden") and g["canPublishData"] is True and g["canPublish"] is False


def test_a_code_works_once_and_you_cannot_join_your_own_call(api):
    code = api.post("/api/webrtc/calls", headers=api.headers_for("alice")).json()["code"]
    assert api.post(f"/api/webrtc/calls/{code}/join", headers=api.headers_for("alice")).status_code == 400
    assert api.post(f"/api/webrtc/calls/{code.lower()}/join", headers=api.headers_for("bob")).status_code == 200
    assert api.post(f"/api/webrtc/calls/{code}/join", headers=api.headers_for("mallory")).status_code == 404


def test_another_accounts_call_is_simply_not_found(api):
    call_id = api.post("/api/webrtc/calls", headers=api.headers_for("alice")).json()["call_id"]
    assert api.get(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("alice")).json()["role"] == "caller"
    assert api.get(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("mallory")).status_code == 404
    assert api.delete(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("mallory")).status_code == 404


def test_guessing_codes_is_rate_limited(api, monkeypatch):
    monkeypatch.setattr(config, "WEBRTC_JOIN_ATTEMPTS_PER_MIN", 3)
    statuses = [api.post(f"/api/webrtc/calls/WRONG{i:03d}/join", headers=api.headers_for("mallory")).status_code
                for i in range(4)]
    assert statuses == [404, 404, 404, 429]


def test_an_expired_code_is_gone(api, monkeypatch):
    from server import webrtc_calls

    now = [1000.0]
    monkeypatch.setattr(webrtc_calls.registry, "clock", lambda: now[0])
    code = api.post("/api/webrtc/calls", headers=api.headers_for("alice")).json()["code"]
    now[0] += config.WEBRTC_CALL_TTL_S + 1
    assert api.post(f"/api/webrtc/calls/{code}/join", headers=api.headers_for("bob")).status_code == 404


def test_calls_beyond_capacity_are_refused(api, monkeypatch):
    monkeypatch.setattr(config, "WEBRTC_MAX_CALLS", 1)
    assert api.post("/api/webrtc/calls", headers=api.headers_for("alice")).status_code == 201
    assert api.post("/api/webrtc/calls", headers=api.headers_for("carol")).status_code == 503


def test_ending_a_call_stops_its_agent(api):
    call_id = api.post("/api/webrtc/calls", headers=api.headers_for("alice")).json()["call_id"]
    assert api.delete(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("alice")).status_code == 204
    assert api.agents.stopped == [call_id]
    assert api.get(f"/api/webrtc/calls/{call_id}", headers=api.headers_for("alice")).json()["ended"] is True
