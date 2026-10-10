"""SatyaCheck — live verdict feed for dashboards and apps.

Every verdict the session runner dispatches (Exotel calls; app WebSocket sessions when
USE_PIPELINE_RUNNER is on) is published here, as one versioned JSON message, to every
client connected to `/api/ws/live` (server/live_router.py). The message is the contract
in docs/LIVE_FEED.md — change both together and bump SCHEMA_VERSION.

In-memory, single process, like server/guardian.py: a client that connects mid-call sees
verdicts from then on; nothing is replayed or stored here.

C owns this file.
"""

from __future__ import annotations

import json
import logging
import uuid

from typing import Optional

from fastapi import WebSocket

log = logging.getLogger("satyacheck.live")

SCHEMA_VERSION = 1

_subscribers: dict[str, WebSocket] = {}
_owners: dict[str, Optional[str]] = {}   # each subscriber sees one account's calls only


def subscribe(ws: WebSocket, owner_id: Optional[str] = None) -> str:
    conn_id = uuid.uuid4().hex[:8]
    _subscribers[conn_id] = ws
    _owners[conn_id] = owner_id
    log.info(f"live feed: subscriber {conn_id} connected ({len(_subscribers)} total)")
    return conn_id


def unsubscribe(conn_id: str) -> None:
    _owners.pop(conn_id, None)
    if _subscribers.pop(conn_id, None) is not None:
        log.info(f"live feed: subscriber {conn_id} left ({len(_subscribers)} total)")


async def publish(message: dict, owner_id: Optional[str] = None) -> None:
    """Send `message` to the subscribers of its account. A failed send drops that
    subscriber, logged."""
    if not _subscribers:
        return
    text = json.dumps(message, ensure_ascii=False)
    for conn_id, ws in list(_subscribers.items()):
        if _owners.get(conn_id) != owner_id:
            continue
        try:
            await ws.send_text(text)
        except Exception as e:  # noqa: BLE001 — one dead dashboard must not stop the others
            from server.ws_util import is_client_gone

            if is_client_gone(e):
                log.info(f"live feed: subscriber {conn_id} left; dropped")
            else:
                log.warning(f"live feed: dropping subscriber {conn_id}: {type(e).__name__}: {e}")
            _subscribers.pop(conn_id, None)
            _owners.pop(conn_id, None)


def hello_message() -> dict:
    from datetime import datetime, timezone

    return {"type": "hello", "schema_version": SCHEMA_VERSION,
            "server_time": datetime.now(timezone.utc).isoformat()}


def verdict_message(event) -> dict:
    """One dispatched VerdictEvent as the documented live-feed message."""
    from server.ws_router import _OVERLAY_STATE

    response = event.response
    fusion = response.fusion
    spoof_available = response.spoof.details.get("available", True) is not False
    threat = getattr(fusion, "threat_label", None)
    caller = getattr(response, "caller_context", None)
    return {
        "type": "verdict",
        "schema_version": SCHEMA_VERSION,
        "session_id": event.session_id,
        "window_index": event.window_index,
        "is_final": event.is_final,
        "escalated": event.escalated,
        "timestamp": response.timestamp,
        "band": fusion.band.value,
        "overlay_state": _OVERLAY_STATE.get(fusion.band, "grey"),
        "trust_score": fusion.trust_score,
        "risk_score": fusion.risk_score,
        "mode": fusion.mode.value,
        "signals": {
            "identity": response.speaker.verdict.value,
            "authenticity": ("unavailable" if not spoof_available
                             else "synthetic" if response.spoof.is_synthetic else "bonafide"),
            "intent_risk": response.script.risk,
        },
        "reason_codes": [
            {"code": rc.code, "signal": rc.signal.value, "value": rc.value, "threshold": rc.threshold,
             "explanation": rc.explanation, "severity": rc.severity.value}
            for rc in fusion.reason_codes
        ],
        "transcript": response.transcript.text,
        "language": response.transcript.detected_language,
        "caller_context": caller.model_dump(mode="json") if caller is not None else None,
        "threat_label": threat.model_dump(mode="json") if threat is not None else None,
        "recommended_actions": list(fusion.recommended_actions),
        "vernacular_warning": fusion.vernacular_warning,
        # The session values above only fall; these follow the current window.
        "window_trust_score": event.window_trust_score if getattr(event, "window_trust_score", None) is not None
        else fusion.trust_score,
        "window_band": getattr(event, "window_band", None) or fusion.band.value,
    }
