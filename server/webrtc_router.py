"""App-to-app call endpoints (webrtc/BACKEND_API.md). Mounted only when ENABLE_WEBRTC is on
and AUTH_MODE=jwt (server/main.py::mount_webrtc), together with server/contacts.py.

    POST   /api/webrtc/calls                    caller: ring a connection {callee_id}
    GET    /api/webrtc/incoming                 callee: calls ringing for me (polled while the app is open)
    POST   /api/webrtc/calls/{call_id}/accept   callee: answer; returns the room token
    POST   /api/webrtc/calls/{call_id}/decline  callee: decline
    GET    /api/webrtc/calls/{call_id}          either party: the call's state
    DELETE /api/webrtc/calls/{call_id}          either party: cancel or hang up

Every endpoint needs a verified sign-in (`verified_principal`): never the dev account. You
can ring only an accepted connection.

C owns this file.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

import config
from server import contacts
from server.auth import Principal, verified_principal
from server.webrtc_calls import CallError, registry

log = logging.getLogger("satyacheck.webrtc")
router = APIRouter(prefix="/api/webrtc", tags=["webrtc"])


class PlaceCall(BaseModel):
    callee_id: str = Field(..., max_length=128)


class Party(BaseModel):
    user_id: str
    username: str
    display_name: str


class CallTicket(BaseModel):
    """What a phone needs to enter the call's room."""
    call_id: str
    livekit_url: str
    token: str
    agent_identity: str
    other: Optional[Party] = None
    ring_timeout_s: Optional[int] = None


class IncomingCall(BaseModel):
    call_id: str
    caller: Party
    rings_for_s: int


class Incoming(BaseModel):
    calls: list[IncomingCall]


class CallState(BaseModel):
    call_id: str
    role: str                     # "caller" | "callee"
    status: str                   # "ringing" | "active" | "ended"
    ended_reason: Optional[str]   # "declined" | "missed" | "cancelled" | "hung_up"
    other_joined: bool            # the callee answered
    ended: bool
    screening: bool               # the agent is running


def _http(e: CallError) -> HTTPException:
    return HTTPException(status_code=e.status, detail=e.detail)


def _party(asker: str, user_id: str) -> Party:
    profile = contacts.get_profile(asker, user_id)
    return Party(**profile) if profile else Party(user_id=user_id, username="", display_name="Unknown")


async def _reap() -> None:
    """Stop the agents of calls that ended unanswered. Called on every request, and the
    phones poll often, so an unanswered call's slots are freed within seconds."""
    from server.webrtc_screening import get_manager

    for call_id in registry.drain_ended():
        log.info(f"[{call_id}] unanswered; stopping its screening agent")
        await get_manager().stop(call_id, "the call was not answered")


@router.post("/calls", response_model=CallTicket, status_code=201)
async def place_call(body: PlaceCall, principal: Principal = Depends(verified_principal)) -> CallTicket:
    from server.webrtc_screening import get_manager, phone_token

    await _reap()
    me = principal.owner_id
    if not contacts.are_connected(me, body.callee_id):
        raise HTTPException(status_code=403, detail="You can call only people you are connected with.")
    try:
        call = registry.create(me, body.callee_id)
    except CallError as e:
        raise _http(e) from None
    if not get_manager().start(call):
        registry.end(call.call_id, me)
        raise HTTPException(status_code=503, detail="The screening service is at capacity. Try again in a minute.")
    log.info(f"[{call.call_id}] ringing")
    return CallTicket(call_id=call.call_id, livekit_url=config.LIVEKIT_URL, token=phone_token(call, me),
                      agent_identity=call.agent_identity, other=_party(me, call.callee_id),
                      ring_timeout_s=config.WEBRTC_RING_TIMEOUT_S)


@router.get("/incoming", response_model=Incoming)
async def incoming(principal: Principal = Depends(verified_principal)) -> Incoming:
    await _reap()
    me = principal.owner_id
    now = registry.clock()
    return Incoming(calls=[IncomingCall(call_id=c.call_id, caller=_party(me, c.caller_id), rings_for_s=c.rings_for_s(now))
                           for c in registry.incoming_for(me)])


@router.post("/calls/{call_id}/accept", response_model=CallTicket)
async def accept_call(call_id: str, principal: Principal = Depends(verified_principal)) -> CallTicket:
    from server.webrtc_screening import get_manager, phone_token

    await _reap()
    me = principal.owner_id
    try:
        call = registry.accept(call_id, me)
    except CallError as e:
        raise _http(e) from None
    get_manager().bind_listener(call)
    log.info(f"[{call.call_id}] answered; both voices can now be screened")
    return CallTicket(call_id=call.call_id, livekit_url=config.LIVEKIT_URL, token=phone_token(call, me),
                      agent_identity=call.agent_identity, other=_party(me, call.caller_id))


@router.post("/calls/{call_id}/decline", status_code=204, response_class=Response)
async def decline_call(call_id: str, principal: Principal = Depends(verified_principal)) -> Response:
    from server.webrtc_screening import get_manager

    try:
        call = registry.decline(call_id, principal.owner_id)
    except CallError as e:
        raise _http(e) from None
    await get_manager().stop(call.call_id, "the call was declined")
    return Response(status_code=204)


@router.get("/calls/{call_id}", response_model=CallState)
async def call_state(call_id: str, principal: Principal = Depends(verified_principal)) -> CallState:
    from server.webrtc_screening import get_manager

    await _reap()
    try:
        call = registry.get_for(call_id, principal.owner_id)
    except CallError as e:
        raise _http(e) from None
    return CallState(call_id=call.call_id, role="caller" if principal.owner_id == call.caller_id else "callee",
                     status=call.status, ended_reason=call.ended_reason, other_joined=call.accepted_at is not None,
                     ended=call.status == "ended", screening=get_manager().running(call.call_id))


@router.delete("/calls/{call_id}", status_code=204, response_class=Response)
async def end_call(call_id: str, principal: Principal = Depends(verified_principal)) -> Response:
    from server.webrtc_screening import get_manager

    try:
        call = registry.end(call_id, principal.owner_id)
    except CallError as e:
        raise _http(e) from None
    await get_manager().stop(call.call_id, "a participant ended the call")
    return Response(status_code=204)
