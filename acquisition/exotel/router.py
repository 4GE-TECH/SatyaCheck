"""WebSocket route for Exotel's Stream applet (unidirectional).

Exotel is the WebSocket *client*: it connects to `config.EXOTEL_WS_PATH`, sends
connected/start/media/stop as JSON text, and expects nothing back. Each connection is
one call, decoded by `ExotelStreamDecoder` and fed to a session runner that server/
injects (`runner_factory`) — acquisition/ never imports server/ (CLAUDE.md boundaries).

Auth (Exotel docs: Basic auth in the URL, wss://KEY:TOKEN@host/path, sent as an
Authorization header; documented for the Voicebot applet, *not confirmed* for Stream —
verify on a test call). Credentials come from the environment and are compared in
constant time. With no credentials configured every connection is refused, and the
reason is logged once, unless EXOTEL_ALLOW_UNAUTHENTICATED is explicitly true. An
optional allowlist (EXOTEL_ALLOWED_IPS: IPs, CIDRs, or exact host names) is checked
first; Exotel does not publish its egress IPs — ask Exotel support for your region.
Refusals close with 1008 (policy violation) and are logged; credentials never are.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import ipaddress
import logging
from typing import Callable

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

import config
from contracts import AudioFrame, SessionClose, SessionOpen

from acquisition.exotel.decoder import ExotelStreamDecoder

log = logging.getLogger("satyacheck.acquisition.exotel")

POLICY_VIOLATION = 1008


def _host_allowed(host: str, allowed) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    for entry in allowed:
        entry = str(entry).strip()
        if not entry:
            continue
        if entry == host:
            return True
        if addr is not None:
            try:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            except ValueError:
                continue
    return False


def _basic_credentials(header: str):
    if not header or not header.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    user, sep, password = decoded.partition(":")
    return (user, password) if sep else None


def build_exotel_router(runner_factory: Callable[[], object]) -> APIRouter:
    """An APIRouter with the Exotel WebSocket route. `runner_factory()` returns an object
    with async open(SessionOpen) / push(AudioFrame) / close(SessionClose)."""
    router = APIRouter(tags=["exotel"])
    state = {"explained_missing_credentials": False}

    def authorised(ws: WebSocket, host: str) -> bool:
        allowed = config.EXOTEL_ALLOWED_IPS or []
        if allowed and not _host_allowed(host, allowed):
            log.warning(f"exotel: refused connection from {host!r}: not in the EXOTEL_ALLOWED_IPS allowlist")
            return False
        user, password = config.EXOTEL_BASIC_USER, config.EXOTEL_BASIC_PASS
        if not user or not password:
            if config.EXOTEL_ALLOW_UNAUTHENTICATED:
                log.warning(f"exotel: accepting an unauthenticated connection from {host!r} "
                            f"(EXOTEL_ALLOW_UNAUTHENTICATED=true — closed test networks only)")
                return True
            if not state["explained_missing_credentials"]:
                state["explained_missing_credentials"] = True
                log.error("exotel: refusing every stream — EXOTEL_BASIC_USER / EXOTEL_BASIC_PASS are "
                          "not set. Set them and put the same pair in the Exotel applet URL "
                          "(wss://USER:PASS@host/path), or set EXOTEL_ALLOW_UNAUTHENTICATED=true "
                          "on a closed test network.")
            else:
                log.warning(f"exotel: refused connection from {host!r}: credentials not configured")
            return False
        given = _basic_credentials(ws.headers.get("authorization", ""))
        ok = given is not None and (
            hmac.compare_digest(given[0].encode(), str(user).encode())
            & hmac.compare_digest(given[1].encode(), str(password).encode())
        )
        if not ok:
            log.warning(f"exotel: refused connection from {host!r}: missing or wrong Basic credentials")
        return ok

    @router.websocket(config.EXOTEL_WS_PATH)
    async def exotel_stream(ws: WebSocket) -> None:
        host = ws.client.host if ws.client else ""
        if not authorised(ws, host):
            await ws.close(code=POLICY_VIOLATION)
            return
        await ws.accept()
        decoder = ExotelStreamDecoder(url_sample_rate=ws.query_params.get("sample-rate"))
        runner = runner_factory()
        disconnect_reason = "socket disconnected"
        try:
            while True:
                try:
                    message = await ws.receive()
                except WebSocketDisconnect as e:
                    disconnect_reason = f"socket disconnected (code {e.code})"
                    break
                if message.get("type") == "websocket.disconnect":
                    disconnect_reason = f"socket disconnected (code {message.get('code', 1000)})"
                    break
                text = message.get("text")
                if text is None:
                    log.warning("exotel: binary frame ignored (the Stream applet sends JSON text)")
                    continue
                for item in decoder.feed(text):
                    if isinstance(item, SessionOpen):
                        await runner.open(item)
                    elif isinstance(item, AudioFrame):
                        await runner.push(item)
                    elif isinstance(item, SessionClose):
                        await runner.close(item)
                        await ws.close(code=1000)
                        return
        except Exception as e:  # noqa: BLE001 — log why, then close the session below
            log.error(f"exotel: stream handler failed: {type(e).__name__}: {e}")
            disconnect_reason = f"handler error: {type(e).__name__}"
        close = decoder.end(disconnect_reason)
        if close is not None:
            try:
                await runner.close(close)
            except Exception as e:  # noqa: BLE001
                log.error(f"[{close.session_id}] exotel: closing the session failed: {e}")

    return router
