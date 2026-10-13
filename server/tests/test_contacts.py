"""Usernames and connections (server/contacts.py): who can find whom, and who may call whom."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from server.tests.auth_helpers import signed_in  # noqa: F401  (fixture)


@pytest.fixture
def api(signed_in, monkeypatch):   # noqa: F811
    from server import contacts

    monkeypatch.setattr(contacts, "search_limiter", contacts._Limiter(60))
    monkeypatch.setattr(contacts, "request_limiter", contacts._Limiter(3600))
    app = FastAPI()
    app.include_router(contacts.router)
    client = TestClient(app)
    client.as_ = lambda who: signed_in.headers(who)
    return client


def _name(api, who, username, display=None):
    r = api.put("/api/profile", json={"username": username, "display_name": display}, headers=api.as_(who))
    assert r.status_code == 200, r.text
    return r.json()


def test_everything_needs_a_verified_sign_in(api):
    assert api.get("/api/profile").status_code == 401
    assert api.get("/api/users/search?q=al").status_code == 401
    assert api.post("/api/connections", json={"user_id": "x"}).status_code == 401


def test_choosing_a_username(api):
    assert api.get("/api/profile", headers=api.as_("alice")).status_code == 404
    me = _name(api, "alice", "  @Alice.K ", "Alice  Kumar")
    assert me == {"user_id": "alice", "username": "alice.k", "display_name": "Alice Kumar"}
    assert api.get("/api/profile", headers=api.as_("alice")).json() == me
    # Changing it keeps the same account.
    assert _name(api, "alice", "alice_k")["username"] == "alice_k"


def test_usernames_are_unique_valid_and_not_official_looking(api):
    _name(api, "alice", "alice")
    assert api.put("/api/profile", json={"username": "ALICE"}, headers=api.as_("bob")).status_code == 409
    for bad in ("ab", "-bob", "bob smith", "x" * 21, "satyacheck_help", "support.desk"):
        assert api.put("/api/profile", json={"username": bad}, headers=api.as_("bob")).status_code == 422, bad


def test_search_finds_usernames_by_prefix_but_never_yourself_or_emails(api):
    _name(api, "alice", "alice")
    _name(api, "bob", "bobby", "Bob")
    _name(api, "bob2", "bob_k")
    found = api.get("/api/users/search?q=@BOB", headers=api.as_("alice")).json()
    assert [p["username"] for p in found] == ["bob_k", "bobby"]
    assert all(set(p) == {"user_id", "username", "display_name", "relation"} for p in found)
    assert api.get("/api/users/search?q=alice", headers=api.as_("alice")).json() == []
    assert api.get("/api/users/search?q=b", headers=api.as_("alice")).json() == []      # too short
    # LIKE wildcards are literal.
    assert api.get("/api/users/search?q=b%25", headers=api.as_("alice")).json() == []


def test_search_is_rate_limited(api, monkeypatch):
    monkeypatch.setattr(config, "WEBRTC_SEARCH_PER_MIN", 2)
    codes = [api.get("/api/users/search?q=bo", headers=api.as_("alice")).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_request_then_accept_connects_both_ways(api):
    _name(api, "alice", "alice")
    _name(api, "bob", "bob")
    sent = api.post("/api/connections", json={"user_id": "bob"}, headers=api.as_("alice"))
    assert sent.status_code == 201 and sent.json()["relation"] == "outgoing"
    assert api.get("/api/users/search?q=bo", headers=api.as_("alice")).json()[0]["relation"] == "outgoing"
    assert [p["username"] for p in api.get("/api/connections", headers=api.as_("bob")).json()["incoming"]] == ["alice"]

    # Only the addressee accepts.
    assert api.post("/api/connections/bob/accept", headers=api.as_("alice")).status_code == 404
    assert api.post("/api/connections/alice/accept", headers=api.as_("bob")).json()["relation"] == "connected"

    from server.contacts import are_connected

    assert are_connected("alice", "bob") and are_connected("bob", "alice")
    assert api.get("/api/connections", headers=api.as_("alice")).json()["connected"][0]["username"] == "bob"


def test_asking_back_accepts(api):
    _name(api, "alice", "alice")
    _name(api, "bob", "bob")
    api.post("/api/connections", json={"user_id": "bob"}, headers=api.as_("alice"))
    assert api.post("/api/connections", json={"user_id": "alice"}, headers=api.as_("bob")).json()["relation"] == "connected"


def test_a_pending_request_does_not_allow_calls_and_can_be_declined(api):
    from server.contacts import are_connected

    _name(api, "alice", "alice")
    _name(api, "mallory", "mallory")
    api.post("/api/connections", json={"user_id": "alice"}, headers=api.as_("mallory"))
    assert not are_connected("mallory", "alice")
    assert api.delete("/api/connections/mallory", headers=api.as_("alice")).status_code == 204
    assert api.get("/api/connections", headers=api.as_("mallory")).json()["outgoing"] == []


def test_requests_need_your_own_username_a_real_target_and_are_rate_limited(api, monkeypatch):
    assert api.post("/api/connections", json={"user_id": "bob"}, headers=api.as_("alice")).status_code == 409
    _name(api, "alice", "alice")
    assert api.post("/api/connections", json={"user_id": "nobody"}, headers=api.as_("alice")).status_code == 404
    assert api.post("/api/connections", json={"user_id": "alice"}, headers=api.as_("alice")).status_code == 400
    monkeypatch.setattr(config, "WEBRTC_CONNECT_REQUESTS_PER_HOUR", 1)
    for who in ("b1", "b2"):
        _name(api, who, f"user_{who}")
    assert api.post("/api/connections", json={"user_id": "b1"}, headers=api.as_("alice")).status_code == 201
    assert api.post("/api/connections", json={"user_id": "b2"}, headers=api.as_("alice")).status_code == 429


def test_the_database_keeps_one_row_per_pair_whoever_asked(api):
    """Both directions share one pair_key, so a second row for the same two people is refused
    by the database itself, not only by the request code."""
    from sqlalchemy.exc import IntegrityError

    from server import database

    with database.owner_session("alice") as db:
        db.add(database.Connection(connection_id="c1", requester_id="alice", addressee_id="bob",
                                   pair_key=database.pair_key("alice", "bob"), status="pending"))
        db.commit()
        db.add(database.Connection(connection_id="c2", requester_id="bob", addressee_id="alice",
                                   pair_key=database.pair_key("bob", "alice"), status="pending"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_two_people_asking_each_other_at_the_same_instant_end_up_connected(api, monkeypatch):
    """The race: bob's request is in flight while alice's lands. Bob's insert hits the
    one-row-per-pair index, and asking back accepts, as if alice's had arrived first."""
    from server import contacts

    _name(api, "alice", "alice")
    _name(api, "bob", "bobby")
    assert api.post("/api/connections", json={"user_id": "bob"}, headers=api.as_("alice")).json()["relation"] == "outgoing"
    real, calls = contacts._between, []

    def late(db, a, b):   # bob's first look happens before alice's row is visible
        calls.append(1)
        return None if len(calls) == 1 else real(db, a, b)

    monkeypatch.setattr(contacts, "_between", late)
    r = api.post("/api/connections", json={"user_id": "alice"}, headers=api.as_("bob"))
    assert r.status_code == 201 and r.json()["relation"] == "connected"
    assert api.get("/api/connections", headers=api.as_("alice")).json()["connected"][0]["user_id"] == "bob"


def test_an_older_database_with_duplicate_pairs_keeps_the_accepted_row(tmp_path):
    from sqlalchemy import create_engine, text

    from server import database

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:   # the 0003 shape: no pair_key, and a duplicated pair
        conn.execute(text("CREATE TABLE connections (connection_id VARCHAR PRIMARY KEY, requester_id VARCHAR NOT NULL, "
                          "addressee_id VARCHAR NOT NULL, status VARCHAR NOT NULL, created_at DATETIME, "
                          "responded_at DATETIME)"))
        conn.execute(text("INSERT INTO connections VALUES ('old', 'a', 'b', 'pending', '2026-10-01', NULL), "
                          "('acc', 'b', 'a', 'accepted', '2026-10-02', '2026-10-02'), "
                          "('other', 'a', 'c', 'pending', '2026-10-03', NULL)"))
    database.migrate(engine)
    with engine.connect() as conn:
        rows = dict(conn.execute(text("SELECT connection_id, pair_key FROM connections")).fetchall())
    assert rows == {"acc": "a|b", "other": "a|c"}
