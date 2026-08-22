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

from contracts import (
    GuardianAlert,
    ScreeningResponse,
    TrustBand,
)

log = logging.getLogger("satyacheck.guardian")

# In-memory subscriber registry: connection_id → WebSocket
_subscribers: dict[str, WebSocket] = {}


async def subscribe(ws: WebSocket) -> str:
    """Register a new guardian WebSocket connection. Returns connection_id."""
    conn_id = uuid.uuid4().hex[:8]
    _subscribers[conn_id] = ws
    log.info(f"Guardian subscribed: {conn_id} (total: {len(_subscribers)})")
    return conn_id


def unsubscribe(conn_id: str) -> None:
    """Remove a guardian subscriber."""
    _subscribers.pop(conn_id, None)
    log.info(f"Guardian unsubscribed: {conn_id} (total: {len(_subscribers)})")


async def publish_alert(alert: GuardianAlert) -> None:
    """Fan out a GuardianAlert to all subscribed connections."""
    if not _subscribers:
        return
    payload = alert.model_dump_json()
    dead: list[str] = []
    for conn_id, ws in _subscribers.items():
        try:
            await ws.send_text(payload)
        except Exception as e:
            log.warning(f"Guardian {conn_id} send failed ({e}), removing")
            dead.append(conn_id)
    for conn_id in dead:
        unsubscribe(conn_id)


async def publish_alert_from_response(response: ScreeningResponse) -> None:
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
    await publish_alert(alert)
    log.info(f"Guardian alert published: {alert.alert_id} (band={band})")
