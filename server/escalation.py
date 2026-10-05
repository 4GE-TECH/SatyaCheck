"""SatyaCheck — session escalation: persistence, then latch (item 9, FR-13).

Per-window fusion (`orchestrator._compute_fusion`) is stateless and stays that way. This
module decides what a *session* shows, given the stream of per-window verdicts.

Two rules, in order:

1. **Persistence.** A warning band is confirmed only once the last
   `config.ESCALATION_PERSISTENCE_N` windows all reached it. The confirmed level is
   the lowest band among those N windows, so caution / suspicious / suspicious
   confirms caution, not suspicious. One noisy window — a cough, a Whisper
   hallucination, a burst of codec noise — no longer turns a call red.
2. **Latch.** Once confirmed, a warning band never improves within the session. The
   scam phrase scrolling out of the 9 s window must not take the overlay from red
   back to grey.

The trust score follows the same rule as the band: its floor only takes scores from
windows whose band is confirmed. A 45 shown under a grey band would contradict itself.
A window that is not confirmed yet holds whatever the session showed last.

N=1 reproduces the behaviour before this module existed — every window confirms itself.

C owns this file.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from contracts import ScreeningResponse, TrustBand

# Warning severity. Neutral bands rank 0: they never replace an earlier warning.
_WARNING_RANK = {
    TrustBand.CAUTION: 1,
    TrustBand.SUSPICIOUS: 2,
    TrustBand.HIGH_RISK: 3,
}
_BAND_FOR_RANK = {rank: band for band, rank in _WARNING_RANK.items()}

# Shown before any window has been confirmed. Grey and mid-scale: nothing has been
# measured that the session is prepared to stand behind yet.
_NOTHING_SHOWN = (TrustBand.UNVERIFIED, 50.0)


class EscalationGate:
    """Turns a stream of per-window responses into what one session displays."""

    def __init__(self, n: int) -> None:
        if n < 1:
            raise ValueError(f"persistence N must be >= 1, got {n}")
        self.n = n
        self._recent: deque[tuple[int, float]] = deque(maxlen=n)  # (rank, trust)
        self._latched_rank = 0
        self._floor: Optional[float] = None
        self._shown: Optional[tuple[TrustBand, float]] = None

    @property
    def latched_band(self) -> Optional[TrustBand]:
        return _BAND_FOR_RANK.get(self._latched_rank)

    def apply(self, response: ScreeningResponse) -> ScreeningResponse:
        band = response.fusion.band
        rank = _WARNING_RANK.get(band, 0)
        trust = response.fusion.trust_score
        self._recent.append((rank, trust))

        confirmed = min(r for r, _ in self._recent) if len(self._recent) == self.n else 0
        self._latched_rank = max(self._latched_rank, confirmed)
        effective = self._latched_rank

        # Windows in the persistence run whose band the session now stands behind.
        counted = [t for r, t in self._recent if r <= effective]
        if counted:
            low = min(counted)
            self._floor = low if self._floor is None else min(self._floor, low)

        if effective > 0:
            # A confirmed warning — possibly confirmed by this very window's run even
            # when this window itself reached higher (caution, suspicious, suspicious).
            shown_band, shown_trust = _BAND_FOR_RANK[effective], self._floor
        elif rank > 0:
            # This window's warning is not confirmed yet: hold what the session showed.
            shown_band, shown_trust = self._shown or _NOTHING_SHOWN
        else:
            shown_band, shown_trust = band, self._floor

        # `insufficient` is never held over a later window: that window *was* scored,
        # and "too short to evaluate" would misdescribe it.
        if shown_band != TrustBand.INSUFFICIENT:
            self._shown = (shown_band, shown_trust)
        if shown_band == band and shown_trust == trust:
            return response
        return response.model_copy(
            update={
                "fusion": response.fusion.model_copy(
                    update={"band": shown_band, "trust_score": shown_trust}
                )
            }
        )
