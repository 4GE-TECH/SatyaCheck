"""SatyaCheck — Guardian Alert Pub/Sub

In-memory WebSocket subscriber registry.
Triggered automatically when trust score crosses HIGH_RISK or SUSPICIOUS threshold.

C owns this file.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import WebSocket

import config

from contracts import (
    GuardianAlert,
    ScreeningResponse,
    TrustBand,
)

log = logging.getLogger("satyacheck.guardian")

# In-memory subscriber registry: connection_id → WebSocket, and the account it listens for.
_subscribers: dict[str, WebSocket] = {}
_owners: dict[str, Optional[str]] = {}


async def subscribe(ws: WebSocket, owner_id: Optional[str] = None) -> str:
    """Register a guardian WebSocket for one account's alerts. Returns connection_id."""
    conn_id = uuid.uuid4().hex[:8]
    _subscribers[conn_id] = ws
    _owners[conn_id] = owner_id
    log.info(f"Guardian subscribed: {conn_id} (total: {len(_subscribers)})")
    return conn_id


def unsubscribe(conn_id: str) -> None:
    """Remove a guardian subscriber."""
    _subscribers.pop(conn_id, None)
    _owners.pop(conn_id, None)
    log.info(f"Guardian unsubscribed: {conn_id} (total: {len(_subscribers)})")


async def publish_alert(alert: GuardianAlert, owner_id: Optional[str] = None) -> None:
    """Send a GuardianAlert to the connections listening for its account only."""
    if not _subscribers:
        return
    payload = alert.model_dump_json()
    dead: list[str] = []
    for conn_id, ws in list(_subscribers.items()):
        if _owners.get(conn_id) != owner_id:
            continue
        try:
            await ws.send_text(payload)
        except Exception as e:
            from server.ws_util import is_client_gone

            if is_client_gone(e):
                log.info(f"Guardian {conn_id} left; removing")
            else:
                log.warning(f"Guardian {conn_id} send failed ({e}), removing")
            dead.append(conn_id)
    for conn_id in dead:
        unsubscribe(conn_id)


async def publish_alert_from_response(response: ScreeningResponse, owner_id: Optional[str] = None) -> None:
    """Build and publish a GuardianAlert from a ScreeningResponse."""
    band = response.fusion.band
    if band not in (TrustBand.HIGH_RISK, TrustBand.SUSPICIOUS):
        return

    caller_label = (
        response.speaker.matched_person_name
        or response.spoof.__class__.__name__  # fallback
        or "Unknown Caller"
    )
    # Use metadata from response if available (no direct metadata field on ScreeningResponse — use reason codes)
    key_reasons = [rc.explanation for rc in response.fusion.reason_codes[:3]]
    summary = f"{band.value.replace('_', ' ').title()} — {key_reasons[0] if key_reasons else 'Suspicious call detected'}"

    alert = GuardianAlert(
        alert_id=f"alert_{uuid.uuid4().hex[:8]}",
        session_id=response.session_id,
        trust_score=response.fusion.trust_score,
        band=band,
        caller_name_or_number=caller_label,
        summary=summary,
        key_reasons=key_reasons,
        audio_sha256=response.audio_sha256,
    )
    if config.ENABLE_EVIDENCE_LOG:
        try:
            from server.evidence import get_log
            get_log().append(alert)
        except Exception as e:  # the alert still goes out; the gap is logged loudly
            log.error(f"evidence log append failed for {alert.alert_id}: {e}")
    await publish_alert(alert, owner_id)
    log.info(f"Guardian alert published: {alert.alert_id} (band={band})")
