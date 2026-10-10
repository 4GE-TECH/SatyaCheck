"""Upgrade plan, Phase 3: coverage, a de-duplicated authenticity timeline, and alerts kept
separate from the current assessment (server/live_session.py)."""

from __future__ import annotations

import pytest

from contracts import (AntiSpoofResult, ReasonCode, ScriptAnalysisResult, SeverityLevel, SignalType,
                       SpeakerVerdict, SpeakerVerificationResult, SpoofSegment, TrustBand, create_mock_fixture)
from server.live_session import AlertLog, AuthenticityTimeline, Coverage


# --- coverage: never silent skipping ---------------------------------------------------------

def test_scored_windows_merge_into_one_span():
    c = Coverage()
    c.scored(0.0, 9.0)
    c.scored(2.0, 11.0)
    assert [(s.start_s, s.end_s, s.scored) for s in c.spans()] == [(0.0, 11.0, True)]
    assert not c.degraded


def test_an_unscored_stretch_is_explicit_and_degrades_the_session():
    c = Coverage()
    c.scored(0.0, 9.0)
    c.unscored(9.0, 15.0)
    c.scored(15.0, 17.0)
    assert [(s.start_s, s.end_s, s.scored) for s in c.spans()] == [
        (0.0, 9.0, True), (9.0, 15.0, False), (15.0, 17.0, True)]
    assert c.degraded


def test_catching_up_on_a_gap_heals_it():
    c = Coverage()
    c.scored(0.0, 9.0)
    c.unscored(7.0, 13.0)
    c.scored(4.0, 13.0)             # the catch-up window
    assert [(s.start_s, s.end_s, s.scored) for s in c.spans()] == [(0.0, 13.0, True)]
    assert not c.degraded


# --- authenticity: one absolute, de-duplicated timeline ----------------------------------------

def _segs(*spec):
    return [SpoofSegment(start_s=a, end_s=b, score=s, is_synthetic=s >= 0.5) for a, b, s in spec]


def test_overlapping_windows_do_not_count_the_same_audio_twice():
    t = AuthenticityTimeline()
    t.add(0.0, _segs((0.0, 4.0, 0.9), (2.0, 6.0, 0.9)))      # window 0-6
    t.add(2.0, _segs((0.0, 4.0, 0.9), (2.0, 6.0, 0.1)))      # window 2-8: re-scores 2-6
    summary = t.summary()
    assert summary.scored_s == pytest.approx(8.0)
    assert summary.peak == pytest.approx(0.9)
    assert summary.max_synth_run_s == pytest.approx(6.0), "max over overlaps, not a double count"


def test_a_short_cloned_burst_shows_in_peak_and_run_not_median():
    t = AuthenticityTimeline()
    t.add(0.0, _segs((0.0, 4.0, 0.05), (4.0, 8.0, 0.05), (8.0, 10.0, 0.97), (10.0, 14.0, 0.05), (14.0, 18.0, 0.05)))
    s = t.summary()
    assert s.median < 0.2 and s.peak == pytest.approx(0.97) and s.max_synth_run_s == pytest.approx(2.0)


def test_an_empty_timeline_is_zero_not_an_error():
    assert AuthenticityTimeline().summary().scored_s == 0.0


# --- alerts vs the current assessment ----------------------------------------------------------

def _response(band: TrustBand, *, text=True, verdict=SpeakerVerdict.UNKNOWN, claim=None):
    r = create_mock_fixture("red")
    fusion = r.fusion.model_copy(update={"band": band, "reason_codes": [ReasonCode(
        code="RC_TEST", signal=SignalType.INTENT, value=band.value, explanation="snapshot",
        severity=SeverityLevel.HIGH)]})
    details = {"claim_check": claim} if claim else {}
    speaker = SpeakerVerificationResult(verdict=verdict, risk=0.5, details=details)
    script = ScriptAnalysisResult(risk=0.8, details={"available": text})
    return r.model_copy(update={"fusion": fusion, "speaker": speaker, "script": script,
                                "spoof": AntiSpoofResult(risk=0.9, details={"available": True})})


def test_a_corroborated_warning_raises_one_alert_that_survives_benign_audio():
    log = AlertLog("s1")
    new = log.consider(_response(TrustBand.HIGH_RISK), window_index=3, start_s=4, end_s=13,
                       transcript_rev=2, claim_rev=0)
    assert [a.band for a in new] == [TrustBand.HIGH_RISK]
    assert new[0].evidence[0].code == "RC_TEST" and new[0].transcript_rev == 2
    later = log.consider(_response(TrustBand.UNVERIFIED), window_index=9, start_s=16, end_s=25,
                         transcript_rev=3, claim_rev=0)
    assert later == []
    assert log.display_band(TrustBand.UNVERIFIED) == TrustBand.HIGH_RISK, "a warning cannot scroll away"


def test_the_same_level_does_not_raise_a_second_alert_but_a_higher_one_does():
    log = AlertLog("s1")
    log.consider(_response(TrustBand.SUSPICIOUS), window_index=1, start_s=0, end_s=9, transcript_rev=1, claim_rev=0)
    assert log.consider(_response(TrustBand.SUSPICIOUS), window_index=2, start_s=2, end_s=11,
                        transcript_rev=1, claim_rev=0) == []
    assert len(log.consider(_response(TrustBand.HIGH_RISK), window_index=3, start_s=4, end_s=13,
                            transcript_rev=2, claim_rev=0)) == 1


def test_a_warning_resting_only_on_the_voice_check_before_any_transcript_is_not_an_alert():
    """AGENTS.md open item 1: a lone synthetic score with text abstaining shows on the window
    but must not become a sticky alert."""
    log = AlertLog("s1")
    assert log.consider(_response(TrustBand.SUSPICIOUS, text=False), window_index=1, start_s=0, end_s=9,
                        transcript_rev=0, claim_rev=0) == []
    assert log.display_band(TrustBand.SUSPICIOUS) == TrustBand.SUSPICIOUS


def test_an_identity_mismatch_is_corroboration_even_without_text():
    log = AlertLog("s1")
    claim = {"outcome": "mismatch", "person": "Papa"}
    raised = log.consider(_response(TrustBand.HIGH_RISK, text=False, verdict=SpeakerVerdict.MISMATCH, claim=claim),
                          window_index=1, start_s=0, end_s=9, transcript_rev=0, claim_rev=1)
    assert len(raised) == 1


def test_an_alert_resolves_only_when_the_claim_it_rested_on_is_superseded():
    log = AlertLog("s1")
    mismatch = {"outcome": "mismatch", "person": "Papa"}
    log.consider(_response(TrustBand.HIGH_RISK, text=False, verdict=SpeakerVerdict.MISMATCH, claim=mismatch),
                 window_index=1, start_s=0, end_s=9, transcript_rev=0, claim_rev=1)
    # Later benign audio, same claims: still raised.
    log.consider(_response(TrustBand.UNVERIFIED, claim=mismatch), window_index=2, start_s=2, end_s=11,
                 transcript_rev=1, claim_rev=1)
    assert log.display_band(TrustBand.UNVERIFIED) == TrustBand.HIGH_RISK
    # The claim changes ("it's Rahul, not Papa") and Papa is no longer the comparison.
    changed = log.consider(_response(TrustBand.CAUTION, claim={"outcome": "match", "person": "Rahul"}),
                           window_index=3, start_s=4, end_s=13, transcript_rev=2, claim_rev=2)
    assert [a.resolved for a in changed] == [True]
    assert "claim" in changed[0].resolved_reason
    assert log.display_band(TrustBand.CAUTION) == TrustBand.CAUTION


def test_alerts_not_resting_on_a_claim_never_resolve():
    log = AlertLog("s1")
    log.consider(_response(TrustBand.HIGH_RISK), window_index=1, start_s=0, end_s=9, transcript_rev=1, claim_rev=0)
    log.consider(_response(TrustBand.VERIFIED, claim={"outcome": "match", "person": "Papa"}),
                 window_index=2, start_s=2, end_s=11, transcript_rev=2, claim_rev=3)
    assert all(not a.resolved for a in log.alerts)
