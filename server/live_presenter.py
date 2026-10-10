"""What a live listener is shown, independent of how it travels (v2 WebSocket, WebRTC).

The rules live here once, so every transport keeps them (CLAUDE.md "Live alerts never
quietly disappear"):
  * alerts are append-only (`AlertLog`); one is withdrawn only when the claim it rested
    on is superseded, and then it is marked, not deleted;
  * the display band only escalates within a call;
  * a catch-up window (older audio scored late) may raise an alert but never replaces
    the current assessment, and a stale transcript revision is not sent;
  * audio that could not be screened is reported as coverage, never passed off.

`compact()` renders the current state as a bounded packet for transports with a size
limit (LiveKit reliable data packets: 15 KiB). It truncates in a fixed order and never
drops an unresolved alert or the coverage summary.

C owns this file.

    python -m server.live_presenter     # smoke test: prints the size of a worst-case packet
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from contracts import SessionAuthenticity, StreamV2Alert, StreamV2Assessment
from server.live_session import AlertLog

log = logging.getLogger("satyacheck.live.presenter")

#: Largest compact packet, in bytes of UTF-8 JSON. LiveKit's reliable limit is 15 KiB.
MAX_PACKET_BYTES = 12 * 1024
TRANSCRIPT_TAIL_CHARS = 1000
MAX_REASONS = 3


class LivePresenter:
    """One listener's view of one screened voice."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.alerts = AlertLog(session_id)
        self.claim_rev = 0
        self._claims_seen: Optional[str] = None
        self._transcript_rev = -1
        self.rev = 0                                   # bumps on every state change sent
        self.latest: Optional[StreamV2Assessment] = None

    def _claims_revision(self, response) -> int:
        claims = (response.speaker.details.get("claim_check") or {}).get("claims") or []
        key = json.dumps(claims, sort_keys=True, default=str)
        if claims and key != self._claims_seen:
            self._claims_seen = key
            self.claim_rev += 1
        return self.claim_rev

    def consider(self, event) -> tuple[list[StreamV2Alert], Optional[StreamV2Assessment]]:
        """(alerts raised or resolved by this event, the new current assessment or None)."""
        response = event.response
        claim_rev = self._claims_revision(response)
        changed = self.alerts.consider(response, window_index=event.window_index, start_s=event.start_s,
                                       end_s=event.end_s, transcript_rev=event.transcript_rev,
                                       claim_rev=claim_rev)
        if changed:
            self.rev += 1
        if event.catchup:
            return changed, None   # older audio: may raise an alert, never replaces the current assessment
        if event.transcript_rev < self._transcript_rev and not event.is_final:
            log.debug(f"[{event.session_id}] stale window {event.window_index} (transcript rev "
                      f"{event.transcript_rev} < {self._transcript_rev}) not sent")
            return changed, None
        self._transcript_rev = max(self._transcript_rev, event.transcript_rev)
        self.latest = StreamV2Assessment(
            session_id=event.session_id, window_index=event.window_index,
            audio_start_s=event.start_s, audio_end_s=event.end_s, current=response,
            display_band=self.alerts.display_band(response.fusion.band), alerts=list(self.alerts.alerts),
            transcript_committed=response.transcript.text, transcript_tentative=event.transcript_tentative,
            coverage=list(event.coverage), coverage_degraded=event.coverage_degraded,
            authenticity=event.authenticity or SessionAuthenticity(),
            transcript_rev=event.transcript_rev, claim_rev=claim_rev, is_final=event.is_final)
        self.rev += 1
        return changed, self.latest

    def compact(self, *, available: bool = True, reason: Optional[str] = None,
                max_bytes: int = MAX_PACKET_BYTES) -> dict:
        """The current state as a bounded packet. Safe before any assessment exists."""
        a = self.latest
        unresolved = [x for x in self.alerts.alerts if not x.resolved]
        resolved = [x for x in self.alerts.alerts if x.resolved]

        def alert(x: StreamV2Alert, evidence_chars: int) -> dict:
            first = x.evidence[0] if x.evidence else None
            return {"alert_id": x.alert_id, "band": x.band.value if hasattr(x.band, "value") else x.band,
                    "at_s": round(x.audio_start_s, 1), "resolved": x.resolved,
                    "evidence": (first.explanation[:evidence_chars] if first else None)}

        def build(tail: int, explain: int, keep_resolved: bool) -> dict:
            packet = {
                "type": "satyacheck.verdict", "schema_version": 1, "rev": self.rev,
                "session_id": self.session_id, "screening_available": available, "reason": reason,
                "alerts": [alert(x, explain) for x in unresolved]
                          + ([alert(x, explain) for x in resolved] if keep_resolved else []),
            }
            if a is None:
                packet.update({"display_band": "insufficient", "trust_score": None, "mode": None,
                               "reasons": [], "coverage": None, "transcript_tail": "", "transcript_rev": -1,
                               "is_final": False})
                return packet
            fusion = a.current.fusion
            screened = sum(s.end_s - s.start_s for s in a.coverage if s.scored)
            unscreened = sum(s.end_s - s.start_s for s in a.coverage if not s.scored)
            text = a.transcript_committed or ""
            packet.update({
                "display_band": a.display_band.value if hasattr(a.display_band, "value") else a.display_band,
                "trust_score": None if a.display_band == "insufficient" else round(fusion.trust_score, 1),
                "mode": fusion.mode.value if hasattr(fusion.mode, "value") else fusion.mode,
                "reasons": [{"code": r.code, "explanation": r.explanation[:explain]}
                            for r in fusion.reason_codes[:MAX_REASONS]],
                "coverage": {"screened_s": round(screened, 1), "unscreened_s": round(unscreened, 1),
                             "degraded": a.coverage_degraded},
                "transcript_tail": text[-tail:] if tail else "", "transcript_rev": a.transcript_rev,
                "is_final": a.is_final,
            })
            return packet

        # Truncate in a fixed order: transcript first, then explanations, then resolved
        # alerts. Unresolved alerts and coverage are never dropped.
        for tail, explain, keep_resolved in ((TRANSCRIPT_TAIL_CHARS, 300, True), (300, 300, True),
                                             (0, 160, True), (0, 80, False), (0, 40, False)):
            packet = build(tail, explain, keep_resolved)
            if len(json.dumps(packet, ensure_ascii=False).encode()) <= max_bytes:
                return packet
        log.warning(f"[{self.session_id}] verdict packet still over {max_bytes} bytes after truncation "
                    f"({len(unresolved)} unresolved alerts); sending it anyway")
        return packet


if __name__ == "__main__":
    p = LivePresenter("smoke")
    packet = p.compact(available=False, reason="no assessment yet")
    print(packet["display_band"], len(json.dumps(packet).encode()), "bytes")
    print("[OK] live presenter smoke test")
