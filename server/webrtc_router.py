"""App-to-app call endpoints (webrtc/BACKEND_API.md). Mounted only when ENABLE_WEBRTC is on
and AUTH_MODE=jwt (server/main.py::mount_webrtc).

    POST   /api/webrtc/calls                 caller: create a call, get a code to share
    POST   /api/webrtc/calls/{code}/join     callee: join with the code
    GET    /api/webrtc/calls/{call_id}       either party: the call's state
    DELETE /api/webrtc/calls/{call_id}       either party: end it

Every endpoint needs a verified sign-in (`verified_principal`): never the dev account.

C owns this file.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

import config
from server.auth import Principal, verified_principal
from server.webrtc_calls import CallError, registry

log = logging.getLogger("satyacheck.webrtc")
router = APIRouter(prefix="/api/webrtc", tags=["webrtc"])


class CallCreated(BaseModel):
    call_id: str
    code: str
    livekit_url: str
    token: str
    agent_identity: str
    code_expires_in_s: int


class CallJoined(BaseModel):
    call_id: str
    livekit_url: str
    token: str
    agent_identity: str


class CallState(BaseModel):
    call_id: str
    role: str                    # "caller" | "callee"
    other_joined: bool
    ended: bool
    screening: bool              # the agent is running


def _http(e: CallError) -> HTTPException:
    return HTTPException(status_code=e.status, detail=e.detail)


@router.post("/calls", response_model=CallCreated, status_code=201)
async def create_call(principal: Principal = Depends(verified_principal)) -> CallCreated:
    from server.webrtc_screening import get_manager, phone_token

    try:
        call = registry.create(principal.owner_id)
    except CallError as e:
        raise _http(e) from None
    if not get_manager().start(call):
        registry.end(call.call_id, principal.owner_id)
        raise HTTPException(status_code=503, detail="The screening service is at capacity. Try again in a minute.")
    return CallCreated(call_id=call.call_id, code=call.code, livekit_url=config.LIVEKIT_URL,
                       token=phone_token(call, principal.owner_id), agent_identity=call.agent_identity,
                       code_expires_in_s=config.WEBRTC_CALL_TTL_S)


@router.post("/calls/{code}/join", response_model=CallJoined)
async def join_call(code: str, principal: Principal = Depends(verified_principal)) -> CallJoined:
    from server.webrtc_screening import get_manager, phone_token

    try:
        call = registry.join(code, principal.owner_id)
    except CallError as e:
        raise _http(e) from None
    get_manager().bind_listener(call)
    log.info(f"[{call.call_id}] callee joined; both voices can now be screened")
    return CallJoined(call_id=call.call_id, livekit_url=config.LIVEKIT_URL,
                      token=phone_token(call, principal.owner_id), agent_identity=call.agent_identity)


@router.get("/calls/{call_id}", response_model=CallState)
async def call_state(call_id: str, principal: Principal = Depends(verified_principal)) -> CallState:
    from server.webrtc_screening import get_manager

    try:
        call = registry.get_for(call_id, principal.owner_id)
    except CallError as e:
        raise _http(e) from None
    return CallState(call_id=call.call_id, role="caller" if principal.owner_id == call.caller_id else "callee",
                     other_joined=call.callee_id is not None, ended=call.ended_at is not None,
                     screening=get_manager().running(call.call_id))


@router.delete("/calls/{call_id}", status_code=204, response_class=Response)
async def end_call(call_id: str, principal: Principal = Depends(verified_principal)) -> Response:
    from server.webrtc_screening import get_manager

    try:
        call = registry.end(call_id, principal.owner_id)
    except CallError as e:
        raise _http(e) from None
    await get_manager().stop(call.call_id, "a participant ended the call")
    return Response(status_code=204)
