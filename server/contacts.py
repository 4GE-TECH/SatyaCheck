"""Usernames and connections: who can find whom, and who may call whom (webrtc/BACKEND_API.md).

    GET    /api/profile                        my username, or 404 before I have chosen one
    PUT    /api/profile                        choose or change my username and display name
    GET    /api/users/search?q=                usernames starting with q, with my relation to each
    GET    /api/connections                    connected, incoming requests, outgoing requests
    POST   /api/connections                    send a connect request {user_id}
    POST   /api/connections/{user_id}/accept   accept their request
    DELETE /api/connections/{user_id}          decline, cancel, or disconnect

The rules:
  * a call needs an accepted connection: finding someone's username never lets you ring
    their phone until they accept. In an anti-scam app, a stranger who can call you is the
    threat model, not a convenience;
  * if both people request each other, the second request accepts the first;
  * profiles carry a username and a display name, never an email address;
  * search and requests are rate-limited per account, so the directory cannot be scraped
    or used to spam requests;
  * every endpoint needs a verified sign-in, never the dev account.

On Postgres, profiles are readable by every account and writable by their owner, and a
connection is visible only to its two accounts (server/migrations/versions/0003_contacts.py).

C owns this file.
"""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

import config
from server import database
from server.auth import Principal, verified_principal

log = logging.getLogger("satyacheck.contacts")
router = APIRouter(prefix="/api", tags=["contacts"])

#: 3-20 characters: lower-case letters, digits, dot and underscore; starts with a letter or digit.
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._]{2,19}$")
#: A username that looks official is an impersonation tool in an anti-scam app.
RESERVED_PREFIXES = ("satyacheck", "admin", "support", "official")
SEARCH_LIMIT = 20


# --- rate limits ------------------------------------------------------------------------------

class _Limiter:
    """At most `limit` events per `window_s` per account. In memory, like the call registry."""

    def __init__(self, window_s: float) -> None:
        self.window_s = window_s
        self._events: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, who: str, limit: int, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            events = self._events.setdefault(who, deque())
            while events and now - events[0] > self.window_s:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            return True


search_limiter = _Limiter(60)
request_limiter = _Limiter(3600)


# --- repository -------------------------------------------------------------------------------

def normalise_username(raw: str) -> str:
    return (raw or "").strip().lstrip("@").lower()


def username_problem(username: str) -> Optional[str]:
    """Why this username cannot be used, or None."""
    if not USERNAME.match(username):
        return "Use 3 to 20 characters: letters, numbers, dots or underscores, starting with a letter or number."
    if username.startswith(RESERVED_PREFIXES):
        return "That username is reserved. Choose another."
    return None


def get_profile(owner_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    """A profile as the API shows it. `owner_id` is who is asking (the session scope)."""
    with database.owner_session(owner_id) as db:
        row = db.get(database.Profile, user_id or owner_id)
        return _public(row) if row else None


def _public(row) -> dict:
    return {"user_id": row.owner_id, "username": row.username, "display_name": row.display_name}


def _between(db, a: str, b: str):
    return db.query(database.Connection).filter(or_(
        and_(database.Connection.requester_id == a, database.Connection.addressee_id == b),
        and_(database.Connection.requester_id == b, database.Connection.addressee_id == a),
    )).first()


def relation(row, me: str) -> str:
    """none | outgoing | incoming | connected, from `me`'s side."""
    if row is None:
        return "none"
    if row.status == "accepted":
        return "connected"
    return "outgoing" if row.requester_id == me else "incoming"


def are_connected(a: str, b: str) -> bool:
    """May `a` call `b`? Only after one accepted the other's request."""
    if not a or not b or a == b:
        return False
    with database.owner_session(a) as db:
        return relation(_between(db, a, b), a) == "connected"


# --- endpoints --------------------------------------------------------------------------------

class ProfileIn(BaseModel):
    username: str = Field(..., max_length=40)
    display_name: Optional[str] = Field(None, max_length=60)


class Person(BaseModel):
    user_id: str
    username: str
    display_name: str
    relation: str = "none"   # none | outgoing | incoming | connected


class ConnectIn(BaseModel):
    user_id: str = Field(..., max_length=128)


class Connections(BaseModel):
    connected: list[Person]
    incoming: list[Person]
    outgoing: list[Person]


def _require_profile(owner_id: str) -> dict:
    profile = get_profile(owner_id)
    if profile is None:
        raise HTTPException(status_code=409, detail="Choose a username first.")
    return profile


@router.get("/profile")
async def read_profile(principal: Principal = Depends(verified_principal)) -> dict:
    profile = get_profile(principal.owner_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="No username yet.")
    return profile


@router.put("/profile")
async def write_profile(body: ProfileIn, principal: Principal = Depends(verified_principal)) -> dict:
    username = normalise_username(body.username)
    problem = username_problem(username)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    display = " ".join((body.display_name or "").split()) or username
    me = principal.owner_id
    try:
        with database.owner_session(me) as db:
            taken = db.query(database.Profile).filter(database.Profile.username == username,
                                                      database.Profile.owner_id != me).first()
            if taken is not None:
                raise HTTPException(status_code=409, detail="That username is taken. Choose another.")
            row = db.get(database.Profile, me)
            if row is None:
                row = database.Profile(owner_id=me, username=username, display_name=display)
                db.add(row)
            else:
                row.username, row.display_name = username, display
            db.commit()
            return _public(row)
    except IntegrityError:
        # Two accounts racing for the same name: the database's unique index decides.
        raise HTTPException(status_code=409, detail="That username is taken. Choose another.") from None


@router.get("/users/search", response_model=list[Person])
async def search(q: str = Query("", max_length=40), principal: Principal = Depends(verified_principal)) -> list[Person]:
    me = principal.owner_id
    prefix = normalise_username(q)
    if len(prefix) < 2:
        return []
    if not search_limiter.allow(me, config.WEBRTC_SEARCH_PER_MIN):
        raise HTTPException(status_code=429, detail="Too many searches. Wait a minute, then try again.")
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with database.owner_session(me) as db:
        rows = (db.query(database.Profile)
                .filter(database.Profile.username.like(f"{escaped}%", escape="\\"), database.Profile.owner_id != me)
                .order_by(database.Profile.username).limit(SEARCH_LIMIT).all())
        return [Person(**_public(r), relation=relation(_between(db, me, r.owner_id), me)) for r in rows]


@router.get("/connections", response_model=Connections)
async def list_connections(principal: Principal = Depends(verified_principal)) -> Connections:
    me = principal.owner_id
    out = Connections(connected=[], incoming=[], outgoing=[])
    with database.owner_session(me) as db:
        rows = db.query(database.Connection).filter(or_(database.Connection.requester_id == me,
                                                        database.Connection.addressee_id == me)).all()
        for row in rows:
            other = row.addressee_id if row.requester_id == me else row.requester_id
            profile = db.get(database.Profile, other)
            if profile is None:
                continue   # the account has no username any more: nothing to show or call
            rel = relation(row, me)
            getattr(out, rel).append(Person(**_public(profile), relation=rel))
    for group in (out.connected, out.incoming, out.outgoing):
        group.sort(key=lambda p: p.username)
    return out


@router.post("/connections", response_model=Person, status_code=201)
async def request_connection(body: ConnectIn, principal: Principal = Depends(verified_principal)) -> Person:
    me, them = principal.owner_id, body.user_id
    _require_profile(me)
    if them == me:
        raise HTTPException(status_code=400, detail="That is your own account.")
    with database.owner_session(me) as db:
        profile = db.get(database.Profile, them)
        if profile is None:
            raise HTTPException(status_code=404, detail="No one with that username.")
        row = _between(db, me, them)
        if row is not None and (row.status == "accepted" or row.requester_id == me):
            return Person(**_public(profile), relation=relation(row, me))   # already done: idempotent
        if row is not None:
            # They asked first: asking back is accepting.
            row.status, row.responded_at = "accepted", datetime.now(timezone.utc)
        else:
            if not request_limiter.allow(me, config.WEBRTC_CONNECT_REQUESTS_PER_HOUR):
                raise HTTPException(status_code=429, detail="Too many connect requests. Try again later.")
            row = database.Connection(connection_id=secrets.token_hex(8), requester_id=me, addressee_id=them,
                                      status="pending")
            db.add(row)
        db.commit()
        log.info(f"connection {row.connection_id}: {relation(row, me)}")
        return Person(**_public(profile), relation=relation(row, me))


@router.post("/connections/{user_id}/accept", response_model=Person)
async def accept_connection(user_id: str, principal: Principal = Depends(verified_principal)) -> Person:
    me = principal.owner_id
    _require_profile(me)
    with database.owner_session(me) as db:
        row = _between(db, me, user_id)
        profile = db.get(database.Profile, user_id)
        if row is None or profile is None or (row.status == "pending" and row.addressee_id != me):
            raise HTTPException(status_code=404, detail="No request from that person.")
        if row.status != "accepted":
            row.status, row.responded_at = "accepted", datetime.now(timezone.utc)
            db.commit()
        return Person(**_public(profile), relation="connected")


@router.delete("/connections/{user_id}", status_code=204, response_class=Response)
async def remove_connection(user_id: str, principal: Principal = Depends(verified_principal)) -> Response:
    """Decline their request, cancel mine, or disconnect. Either side may; the answer is the
    same whether or not there was anything to remove."""
    with database.owner_session(principal.owner_id) as db:
        row = _between(db, principal.owner_id, user_id)
        if row is not None:
            db.delete(row)
            db.commit()
    return Response(status_code=204)
