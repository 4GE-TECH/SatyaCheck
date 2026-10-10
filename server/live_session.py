"""SatyaCheck — live session state in absolute audio time (upgrade plan, Phase 3).

Three pieces the v2 protocol reports beside each window's own verdict:

  Coverage              which stretches of the call every check scored, and which it did
                        NOT — an unscored gap is shown, never silently stepped over, and
                        "not scored" is never presented as "human".
  AuthenticityTimeline  anti-spoof scores placed on one absolute timeline. Windows overlap,
                        so the same second is scored several times; each bin keeps its
                        maximum, and median / peak / longest synthetic run come from the
                        de-duplicated bins, not from summing windows.
  AlertLog              append-only warnings, each with the evidence it rested on. The
                        displayed band is the worse of the current window and every
                        unresolved alert, so a warning cannot scroll out of view; an alert
                        resolves only when its own evidence is invalidated (the claim it
                        rested on was superseded), never because later audio sounded fine.

C owns this file.
"""

from __future__ import annotations

import uuid
from typing import Iterable, Optional

import numpy as np

import config
from contracts import (CoverageSpan, ScreeningResponse, SessionAuthenticity, SpeakerVerdict, SpoofSegment,
                       StreamV2Alert, TrustBand)

_RANK = {TrustBand.INSUFFICIENT: 0, TrustBand.VERIFIED: 1, TrustBand.UNVERIFIED: 1,
         TrustBand.CAUTION: 2, TrustBand.SUSPICIOUS: 3, TrustBand.HIGH_RISK: 4}
_ALERT_BANDS = (TrustBand.SUSPICIOUS, TrustBand.HIGH_RISK)


def rank(band: TrustBand) -> int:
    return _RANK.get(TrustBand(band), 0)


def _merge(intervals: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for start, end in sorted((float(a), float(b)) for a, b in intervals if b > a):
        if out and start <= out[-1][1] + 1e-9:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


class Coverage:
    def __init__(self) -> None:
        self._scored: list[tuple[float, float]] = []
        self._unscored: list[tuple[float, float]] = []

    def scored(self, start_s: float, end_s: float) -> None:
        self._scored = _merge(self._scored + [(start_s, end_s)])

    def unscored(self, start_s: float, end_s: float) -> None:
        self._unscored = _merge(self._unscored + [(start_s, end_s)])

    def _gaps(self) -> list[tuple[float, float]]:
        gaps = []
        for start, end in self._unscored:
            cursor = start
            for s_start, s_end in self._scored:
                if s_end <= cursor or s_start >= end:
                    continue
                if s_start > cursor:
                    gaps.append((cursor, s_start))
                cursor = max(cursor, s_end)
            if cursor < end:
                gaps.append((cursor, end))
        return _merge(gaps)

    @property
    def degraded(self) -> bool:
        return bool(self._gaps())

    def spans(self) -> list[CoverageSpan]:
        spans = [CoverageSpan(start_s=round(a, 3), end_s=round(b, 3), scored=True) for a, b in self._scored]
        spans += [CoverageSpan(start_s=round(a, 3), end_s=round(b, 3), scored=False) for a, b in self._gaps()]
        return sorted(spans, key=lambda s: (s.start_s, not s.scored))


class AuthenticityTimeline:
    """Max-per-bin synthetic scores over absolute call time."""

    def __init__(self, bin_s: float = 0.5) -> None:
        self.bin_s = bin_s
        self._score: dict[int, float] = {}
        self._synthetic: dict[int, bool] = {}

    def add(self, window_start_s: float, segments: Iterable[SpoofSegment]) -> None:
        for seg in segments:
            a = float(window_start_s) + float(seg.start_s)
            b = float(window_start_s) + float(seg.end_s)
            for k in range(int(np.floor(a / self.bin_s + 1e-9)), int(np.ceil(b / self.bin_s - 1e-9))):
                self._score[k] = max(self._score.get(k, 0.0), float(seg.score))
                self._synthetic[k] = self._synthetic.get(k, False) or bool(seg.is_synthetic)

    def summary(self) -> SessionAuthenticity:
        if not self._score:
            return SessionAuthenticity()
        keys = sorted(self._score)
        scores = [self._score[k] for k in keys]
        run = best = 0
        previous = None
        for k in keys:
            if not self._synthetic[k]:
                run = 0
            elif run and k == previous + 1:   # contiguous with a synthetic bin
                run += 1
            else:
                run = 1
            best = max(best, run)
            previous = k
        return SessionAuthenticity(median=round(float(np.median(scores)), 4), peak=round(max(scores), 4),
                                   max_synth_run_s=round(best * self.bin_s, 3),
                                   scored_s=round(len(keys) * self.bin_s, 3))


def corroborated(response: ScreeningResponse) -> bool:
    """A warning rests on more than the synthetic-voice score alone while the transcript is
    still missing (AGENTS.md open item 1): there is text, or an identity mismatch, or a
    flagged or replayed voice."""
    text = response.script.details.get("available", True) is not False
    speaker = response.speaker
    return (text or speaker.verdict == SpeakerVerdict.MISMATCH or speaker.is_replay
            or int(speaker.details.get("flagged_voice_hits") or 0) > 0)


class AlertLog:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.alerts: list[StreamV2Alert] = []
        self._claims: dict[str, Optional[str]] = {}   # alert_id -> person whose mismatch it rested on

    def _unresolved(self) -> list[StreamV2Alert]:
        return [a for a in self.alerts if not a.resolved]

    def display_band(self, current: TrustBand) -> TrustBand:
        worst = max(self._unresolved(), key=lambda a: rank(a.band), default=None)
        return worst.band if worst is not None and rank(worst.band) > rank(current) else TrustBand(current)

    def consider(self, response: ScreeningResponse, *, window_index: int, start_s: float, end_s: float,
                 transcript_rev: int, claim_rev: int) -> list[StreamV2Alert]:
        """Resolve alerts whose claim was superseded, raise one if this window warrants it.
        Returns the alerts that changed (new or resolved), for sending."""
        changed: list[StreamV2Alert] = []
        check = response.speaker.details.get("claim_check") or {}
        for i, alert in enumerate(self.alerts):
            person = self._claims.get(alert.alert_id)
            if alert.resolved or person is None or claim_rev <= alert.claim_rev:
                continue
            if not (check.get("outcome") == "mismatch" and check.get("person") == person):
                resolved = alert.model_copy(update={
                    "resolved": True,
                    "resolved_reason": f"the claim it rested on (a voice mismatch with {person}) was superseded"})
                self.alerts[i] = resolved
                changed.append(resolved)

        band = TrustBand(response.fusion.band)
        top = max((rank(a.band) for a in self._unresolved()), default=0)
        if band in _ALERT_BANDS and rank(band) > top and corroborated(response):
            alert = StreamV2Alert(
                alert_id=f"alert_{uuid.uuid4().hex[:10]}", session_id=self.session_id, window_index=window_index,
                audio_start_s=float(start_s), audio_end_s=float(end_s), band=band,
                evidence=list(response.fusion.reason_codes), transcript_rev=transcript_rev, claim_rev=claim_rev)
            self.alerts.append(alert)
            rests_on_claim = (response.speaker.verdict == SpeakerVerdict.MISMATCH
                              and check.get("outcome") == "mismatch")
            self._claims[alert.alert_id] = check.get("person") if rests_on_claim else None
            changed.append(alert)
        return changed


if __name__ == "__main__":
    c = Coverage()
    c.scored(0, 9)
    c.unscored(9, 12)
    print("[OK] coverage:", [(s.start_s, s.end_s, s.scored) for s in c.spans()], "degraded", c.degraded,
          "| spoof bin", config.SPOOF_HOP_S)
