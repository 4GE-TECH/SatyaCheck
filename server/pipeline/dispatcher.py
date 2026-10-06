"""SatyaCheck — verdict dispatcher (item 6).

One place that sends each session verdict to every output: the app overlay, the
guardian alert, the stored result the PDF report reads, and (stubbed) a bank API.

Each sink is independent. They run concurrently, each under `config.DISPATCH_SINK_TIMEOUT_S`;
one raising or hanging is logged with its name and never stops the others or delays
the next verdict. Callers await `dispatch` once per window, in window order, so every
sink sees a session's verdicts in order.

C owns this file.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

import config
from contracts import ScreeningResponse, TrustBand

log = logging.getLogger("satyacheck.pipeline.dispatcher")

#: Bands that page a guardian. Caution is shown to the user but is not an alert.
_ALERT_BANDS = (TrustBand.SUSPICIOUS, TrustBand.HIGH_RISK)


@dataclass(frozen=True)
class VerdictEvent:
    """One window's verdict, after session escalation (server/escalation.py)."""
    session_id: str
    response: ScreeningResponse
    window_index: int
    escalated: bool = False   # the confirmed band rose with this window
    is_final: bool = False
    # This window's own verdict before the session floor and latch (server/escalation.py):
    # what a live gauge should follow. None when the producer did not record it.
    window_trust_score: Optional[float] = None
    window_band: Optional[str] = None


class Sink(Protocol):
    name: str

    async def deliver(self, event: VerdictEvent) -> None: ...


class Dispatcher:
    def __init__(self, sinks: list[Sink], timeout_s: Optional[float] = None) -> None:
        self.sinks = list(sinks)
        self.timeout_s = config.DISPATCH_SINK_TIMEOUT_S if timeout_s is None else timeout_s

    async def _one(self, sink: Sink, event: VerdictEvent) -> bool:
        try:
            await asyncio.wait_for(sink.deliver(event), timeout=self.timeout_s)
            return True
        except asyncio.TimeoutError:
            log.error(f"[{event.session_id}] sink {sink.name} timed out after {self.timeout_s}s "
                      f"(window {event.window_index})")
        except Exception as e:  # noqa: BLE001 — one output failing must not stop the rest
            log.error(f"[{event.session_id}] sink {sink.name} failed on window "
                      f"{event.window_index}: {type(e).__name__}: {e}")
        return False

    async def dispatch(self, event: VerdictEvent) -> dict[str, bool]:
        """Deliver to every sink. Returns {sink name: delivered}. Never raises."""
        results = await asyncio.gather(*(self._one(s, event) for s in self.sinks))
        return {s.name: ok for s, ok in zip(self.sinks, results)}


# --- sinks ----------------------------------------------------------------------------------

class AppOverlaySink:
    """The two messages the phone app reads: `screening_update` (full response, frozen
    contract) then `overlay_update` (pre-flattened for the overlay)."""
    name = "app_overlay"

    def __init__(self, ws) -> None:
        self.ws = ws

    async def deliver(self, event: VerdictEvent) -> None:
        from contracts import StreamScreeningUpdateMessage
        from server.ws_router import _build_overlay_update

        update = StreamScreeningUpdateMessage(session_id=event.session_id,
                                              chunk_index=event.window_index, response=event.response)
        await self.ws.send_text(update.model_dump_json())
        await self.ws.send_json(_build_overlay_update(event.session_id, event.response))


async def _publish_alert(response: ScreeningResponse) -> None:
    from server.guardian import publish_alert_from_response

    await publish_alert_from_response(response)


class GuardianSink:
    """Pages a guardian when the confirmed band *rises* to suspicious or high risk —
    not on every window while a call stays red."""
    name = "guardian"

    async def deliver(self, event: VerdictEvent) -> None:
        if event.escalated and event.response.fusion.band in _ALERT_BANDS:
            await _publish_alert(event.response)


class ReportSink:
    """Stores every verdict (`screenings` table) and marks the session complete on the
    final one — what `/api/report/{id}` and the PDF read."""
    name = "report"

    def __init__(self, session_factory: Optional[Callable] = None) -> None:
        if session_factory is None:
            from server.database import SessionLocal
            session_factory = SessionLocal
        self.session_factory = session_factory

    def _write(self, event: VerdictEvent) -> None:
        from server.database import ScreeningResult, ScreeningSession

        with self.session_factory() as db:
            db.add(ScreeningResult(
                session_id=event.session_id,
                chunk_index=event.window_index,
                response_json=event.response.model_dump_json(),
                processing_ms=event.response.processing_time_ms,
                is_final=event.is_final,
            ))
            if event.is_final:
                session = db.get(ScreeningSession, event.session_id)
                if session is not None:
                    session.status = "complete"
            db.commit()

    async def deliver(self, event: VerdictEvent) -> None:
        await asyncio.to_thread(self._write, event)


class LiveFeedSink:
    """Publishes every verdict to `/api/ws/live` subscribers (server/live_feed.py) —
    how a dashboard watches an Exotel call, which has no app socket of its own."""
    name = "live_feed"

    async def deliver(self, event: VerdictEvent) -> None:
        from server import live_feed

        await live_feed.publish(live_feed.verdict_message(event))


class BankApiSink:
    """Placeholder for a bank / telco integration. Logs at debug, delivers nowhere."""
    name = "bank_api"

    async def deliver(self, event: VerdictEvent) -> None:
        log.debug(f"[{event.session_id}] bank_api stub: band={event.response.fusion.band.value}")
        return None


def build_dispatcher(ws=None, session_factory: Optional[Callable] = None) -> Dispatcher:
    """Sinks named in `config.DISPATCH_SINKS`. The overlay needs a socket; without one it
    is left out. Unknown names are logged and skipped."""
    sinks: list[Sink] = []
    for name in config.DISPATCH_SINKS:
        if name == "app_overlay":
            if ws is not None:
                sinks.append(AppOverlaySink(ws))
        elif name == "guardian":
            sinks.append(GuardianSink())
        elif name == "report":
            sinks.append(ReportSink(session_factory))
        elif name == "live_feed":
            sinks.append(LiveFeedSink())
        elif name == "bank_api":
            sinks.append(BankApiSink())
        else:
            log.warning(f"unknown dispatch sink {name!r} in config.DISPATCH_SINKS; skipped")
    return Dispatcher(sinks)
