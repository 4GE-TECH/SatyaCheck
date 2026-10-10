"""SatyaCheck — WebSocket helpers.

A client that hangs up, loses signal or closes the tab while we are sending is the most
ordinary event a live call has. It must read as a normal close (INFO, no traceback), not
as a server error, or real failures drown in it.

C owns this file.
"""

from __future__ import annotations

from starlette.websockets import WebSocketDisconnect

_CLOSED_SEND_MESSAGES = (
    'Cannot call "send" once a close message has been sent',
    "after sending 'websocket.close'",
    "WebSocket is not connected",
)


def _gone_types() -> tuple[type, ...]:
    types: list[type] = [WebSocketDisconnect]
    try:  # what uvicorn raises when the peer is gone (an OSError subclass)
        from uvicorn.protocols.utils import ClientDisconnected
        types.append(ClientDisconnected)
    except ImportError:  # pragma: no cover - uvicorn is a hard dependency here
        pass
    try:
        from websockets.exceptions import ConnectionClosed
        types.append(ConnectionClosed)
    except ImportError:  # pragma: no cover
        pass
    return tuple(types)


_GONE_TYPES = _gone_types()


def is_client_gone(exc: BaseException) -> bool:
    """True when `exc` only means the other end of the socket has left."""
    if isinstance(exc, _GONE_TYPES):
        return True
    return isinstance(exc, RuntimeError) and any(m in str(exc) for m in _CLOSED_SEND_MESSAGES)


if __name__ == "__main__":
    assert is_client_gone(WebSocketDisconnect(code=1001))
    assert is_client_gone(RuntimeError('Cannot call "send" once a close message has been sent.'))
    assert not is_client_gone(RuntimeError("model crashed"))
    print(f"[OK] ws_util: {len(_GONE_TYPES)} departure exception type(s) recognised")
