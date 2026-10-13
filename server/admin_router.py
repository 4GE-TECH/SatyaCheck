"""The admin console's API (web3): every account's calls, read-only.

    GET  /api/admin/me                       am I an admin? (the console's gate)
    GET  /api/admin/overview                 live counts, the last 24 h by band, capacity
    GET  /api/admin/calls/live               app-to-app calls ringing or in progress, with
                                             what each listener is being shown right now
    GET  /api/admin/screenings               every account's screened calls, newest first
    GET  /api/admin/screenings/{session_id}  one call: transcript, verdict, how it moved
    GET  /api/admin/users                    accounts with a username, and their activity
    WS   /api/admin/ws/live                  every verdict from every account, as it happens

Who: a verified sign-in listed in ADMIN_USER_IDS (`admin_principal`), nobody else, never
the dev account. Everything here READS: on Postgres through a read-only transaction on the
owner connection (`database.admin_session`), so the app role's per-account RLS stays as it
is. Every view is logged with the admin's account id: transcripts are personal data, and
"who looked at this call" must have an answer.

C owns this file.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import and_, func, or_

import config
from server import database
from server.auth import Principal, admin_principal

log = logging.getLogger("satyacheck.admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])


def _audit(principal: Principal, what: str) -> None:
    log.info(f"admin {principal.owner_id} viewed {what}")
    from server.observability import ADMIN_VIEWS

    ADMIN_VIEWS.inc()


def _db():
    try:
        return database.admin_session()
    except database.AdminUnavailable as e:
        log.error(f"admin console unavailable: {e}")
        raise HTTPException(status_code=503, detail="The admin console is not configured on this server.") from None


def _profiles(db, owner_ids) -> dict[str, dict]:
    ids = {o for o in owner_ids if o}
    if not ids:
        return {}
    rows = db.query(database.Profile).filter(database.Profile.owner_id.in_(ids)).all()
    return {r.owner_id: {"user_id": r.owner_id, "username": r.username, "display_name": r.display_name}
            for r in rows}


def _who(profiles: dict, owner_id: Optional[str]) -> dict:
    return profiles.get(owner_id or "") or {"user_id": owner_id, "username": None, "display_name": None}


def _summary(response_json: str) -> dict:
    data = json.loads(response_json)
    fusion = data.get("fusion") or {}
    transcript = (data.get("transcript") or {}).get("text") or ""
    return {"band": fusion.get("band"), "trust_score": fusion.get("trust_score"), "mode": fusion.get("mode"),
            "transcript_preview": transcript[:160]}


# --- endpoints --------------------------------------------------------------------------------

@router.get("/me")
async def me(principal: Principal = Depends(admin_principal)) -> dict:
    return {"user_id": principal.owner_id, "admin": True}


@router.get("/overview")
async def overview(principal: Principal = Depends(admin_principal)) -> dict:
    from server.capacity import readiness
    from server.webrtc_calls import registry

    _audit(principal, "the overview")
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    bands: dict[str, int] = {}
    with _db() as db:
        accounts = db.query(func.count(func.distinct(database.ScreeningSession.owner_id))).scalar() or 0
        usernames = db.query(func.count(database.Profile.owner_id)).scalar() or 0
        recent = db.query(database.ScreeningSession.session_id).filter(database.ScreeningSession.created_at >= since)
        recent_ids = [sid for (sid,) in recent]
        latest: dict[str, str] = {}
        if recent_ids:
            for r in (db.query(database.ScreeningResult.session_id, database.ScreeningResult.response_json)
                      .filter(database.ScreeningResult.session_id.in_(recent_ids))
                      .order_by(database.ScreeningResult.id)):
                latest[r.session_id] = r.response_json
        for blob in latest.values():
            band = _summary(blob)["band"] or "unknown"
            bands[band] = bands.get(band, 0) + 1
    calls = registry.active()
    ready = readiness()
    return {
        "calls": {"ringing": sum(c.status == "ringing" for c in calls),
                  "active": sum(c.status == "active" for c in calls)},
        "live_sessions": ready.get("live_sessions"), "max_live_sessions": ready.get("max_live_sessions"),
        "screenings_24h": len(recent_ids), "bands_24h": bands,
        "accounts_with_calls": accounts, "accounts_with_username": usernames,
        "device": ready.get("device"), "ready": ready.get("ready"), "problems": ready.get("problems", []),
        "webrtc_enabled": config.ENABLE_WEBRTC,
    }


@router.get("/calls/live")
async def live_calls(principal: Principal = Depends(admin_principal)) -> dict:
    from server.webrtc_calls import registry
    from server.webrtc_screening import get_manager

    _audit(principal, "live calls")
    calls = registry.active()
    now = registry.clock()
    with _db() as db:
        profiles = _profiles(db, [c.caller_id for c in calls] + [c.callee_id for c in calls])
    manager = get_manager()
    out = []
    for c in sorted(calls, key=lambda c: c.created_at):
        out.append({
            "call_id": c.call_id, "status": c.status, "age_s": round(now - c.created_at, 1),
            "in_call_s": round(now - c.accepted_at, 1) if c.accepted_at else None,
            "caller": _who(profiles, c.caller_id), "callee": _who(profiles, c.callee_id),
            "screening": manager.running(c.call_id), "voices": manager.voice_states(c.call_id),
        })
    return {"calls": out}


@router.get("/screenings")
async def screenings(
    limit: int = Query(30, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    owner: Optional[str] = Query(None, max_length=128),
    channel: Optional[str] = Query(None, max_length=32),
    principal: Principal = Depends(admin_principal),
) -> dict:
    from server.screen_router import _decode_cursor, _encode_cursor

    _audit(principal, f"the call list (owner={owner or 'all'}, channel={channel or 'all'})")
    S, R = database.ScreeningSession, database.ScreeningResult
    with _db() as db:
        query = db.query(S)
        if owner:
            query = query.filter(S.owner_id == owner)
        if channel:
            query = query.filter(S.channel_type == channel)
        if cursor:
            created, session_id = _decode_cursor(cursor)
            query = query.filter(or_(S.created_at < created, and_(S.created_at == created, S.session_id < session_id)))
        rows = query.order_by(S.created_at.desc(), S.session_id.desc()).limit(limit + 1).all()
        page, more = rows[:limit], len(rows) > limit
        latest: dict[str, tuple] = {}
        for r in (db.query(R.session_id, R.response_json, R.is_final)
                  .filter(R.session_id.in_([s.session_id for s in page])).order_by(R.id)):
            prev = latest.get(r.session_id)
            if prev is None or r.is_final or not prev[1]:   # a final verdict wins; else the newest
                latest[r.session_id] = (r.response_json, r.is_final)
        profiles = _profiles(db, [s.owner_id for s in page])
        items = []
        for s in page:
            summary = _summary(latest[s.session_id][0]) if s.session_id in latest else {}
            items.append({"session_id": s.session_id, "created_at": s.created_at.isoformat() if s.created_at else None,
                          "status": s.status, "channel_type": s.channel_type, "owner": _who(profiles, s.owner_id),
                          **summary})
        next_cursor = _encode_cursor(page[-1].created_at, page[-1].session_id) if more and page else None
    return {"items": items, "next_cursor": next_cursor}


@router.get("/screenings/{session_id}")
async def screening_detail(session_id: str, principal: Principal = Depends(admin_principal)) -> dict:
    _audit(principal, f"call {session_id}")
    S, R = database.ScreeningSession, database.ScreeningResult
    with _db() as db:
        session = db.get(S, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Call not found.")
        results = db.query(R).filter(R.session_id == session_id).order_by(R.id).all()
        profiles = _profiles(db, [session.owner_id])
        timeline = []
        for r in results:
            data = json.loads(r.response_json)
            fusion = data.get("fusion") or {}
            timeline.append({"chunk_index": r.chunk_index, "is_final": bool(r.is_final),
                             "at": r.created_at.isoformat() if r.created_at else None,
                             "band": fusion.get("band"), "trust_score": fusion.get("trust_score")})
        finals = [r for r in results if r.is_final]
        current = json.loads((finals or results)[-1].response_json) if results else None
        return {"session_id": session_id, "owner": _who(profiles, session.owner_id),
                "channel_type": session.channel_type, "status": session.status,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "response": current, "timeline": timeline}


@router.get("/users")
async def users(principal: Principal = Depends(admin_principal)) -> dict:
    _audit(principal, "the account list")
    S = database.ScreeningSession
    with _db() as db:
        counts = dict(db.query(S.owner_id, func.count(S.session_id)).group_by(S.owner_id).all())
        last = dict(db.query(S.owner_id, func.max(S.created_at)).group_by(S.owner_id).all())
        enrolled = dict(db.query(database.Person.owner_id, func.count(database.Person.person_id))
                        .group_by(database.Person.owner_id).all())
        conns: dict[str, int] = {}
        for row in db.query(database.Connection).filter(database.Connection.status == "accepted"):
            for party in (row.requester_id, row.addressee_id):
                conns[party] = conns.get(party, 0) + 1
        profiles = _profiles(db, set(counts) | set(enrolled) | set(conns)
                             | {p.owner_id for p in db.query(database.Profile.owner_id)})
        owners = set(counts) | set(enrolled) | set(profiles)
        out = [{**_who(profiles, o), "calls": counts.get(o, 0), "enrolled_voices": enrolled.get(o, 0),
                "connections": conns.get(o, 0),
                "last_call_at": last[o].isoformat() if last.get(o) else None,
                "admin": o in config.ADMIN_USER_IDS} for o in owners]
    out.sort(key=lambda u: (u["last_call_at"] or ""), reverse=True)
    return {"users": out}


@router.websocket("/ws/live")
async def admin_live(ws: WebSocket) -> None:
    """Every verdict from every account. Sign in with the first message (never the URL);
    only an admin is kept, anyone else is closed with 1008."""
    from server import live_feed
    from server.auth import AuthError, is_admin, verify_token

    await ws.accept()
    host = ws.client.host if ws.client else "?"
    principal = None
    try:
        msg = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=config.WS_AUTH_TIMEOUT_S))
        if isinstance(msg, dict) and msg.get("type") == "auth":
            principal = verify_token(str(msg.get("token") or ""))
    except (AuthError, asyncio.TimeoutError, ValueError, WebSocketDisconnect) as e:
        log.warning(f"admin live feed: refused {host}: {type(e).__name__}")
    if principal is None or not is_admin(principal):
        if principal is not None:
            log.warning(f"admin live feed: refused account {principal.owner_id}: not an admin")
        await ws.close(code=1008)
        return
    _audit(principal, "the live feed of every account")
    conn_id = live_feed.subscribe(ws, live_feed.ADMIN)
    try:
        await ws.send_json(live_feed.hello_message())
        while True:
            await ws.receive_text()   # the console only listens
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        log.warning(f"admin live feed {conn_id}: {type(e).__name__}: {e}")
    finally:
        live_feed.unsubscribe(conn_id)
