"""SatyaCheck — `/api/ws/live`: the live verdict feed (server/live_feed.py, docs/LIVE_FEED.md).

Receive-only for clients, and each client sees only its own account's calls. The client
authenticates with its first message, {"type": "auth", "token": <Supabase access token>}
(server/auth.py); in dev mode a silent client is the dev account. The older
`?token=<LIVE_FEED_TOKEN>` gate still applies when that token is set.

C owns this file.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import config
from server import live_feed

log = logging.getLogger("satyacheck.live")
router = APIRouter(prefix="/api/ws", tags=["live"])


@router.websocket("/live")
async def ws_live(ws: WebSocket) -> None:
    host = ws.client.host if ws.client else "?"
    expected = config.LIVE_FEED_TOKEN
    if expected:
        given = ws.query_params.get("token", "")
        if not hmac.compare_digest(given.encode(), expected.encode()):
            log.warning(f"live feed: refused {host}: missing or wrong token")
            await ws.close(code=1008)
            return
    await ws.accept()
    from server.auth import AuthError, authenticate_ws

    try:
        principal, _ = await authenticate_ws(ws, silent_dev_after=0.5)
    except AuthError as e:
        log.warning(f"live feed: refused {host}: {e}")
        await ws.close(code=1008)
        return
    conn_id = live_feed.subscribe(ws, principal.owner_id)
    try:
        await ws.send_json(live_feed.hello_message())
        while True:
            await ws.receive_text()  # clients only listen; anything they send is ignored
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        log.warning(f"live feed: subscriber {conn_id} error: {type(e).__name__}: {e}")
    finally:
        live_feed.unsubscribe(conn_id)
