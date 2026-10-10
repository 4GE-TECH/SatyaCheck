"""The listener's view, shared by the v2 WebSocket and WebRTC (server/live_presenter.py):
alerts persist, catch-up never replaces the current state, and the WebRTC packet stays
under LiveKit's reliable-data limit without dropping an unresolved alert or coverage."""

from __future__ import annotations

import json

from contracts import CoverageSpan, TrustBand
from server.live_presenter import MAX_PACKET_BYTES, LivePresenter
from server.pipeline.dispatcher import VerdictEvent
from server.tests.test_live_session import _response


def _event(band, index, *, catchup=False, rev=None, text="", final=False, coverage=()):
    r = _response(band)
    if text:
        r = r.model_copy(update={"transcript": r.transcript.model_copy(update={"text": text})})
    return VerdictEvent(session_id="s", response=r, window_index=index, start_s=index * 2.0,
                        end_s=index * 2.0 + 9, catchup=catchup, transcript_rev=index if rev is None else rev,
                        is_final=final, coverage=tuple(coverage))


def _size(packet) -> int:
    return len(json.dumps(packet, ensure_ascii=False).encode())


def test_a_raised_alert_survives_later_calm_windows_and_the_band_never_drops():
    p = LivePresenter("s")
    raised, _ = p.consider(_event(TrustBand.HIGH_RISK, 3))
    assert raised
    _, calm = p.consider(_event(TrustBand.UNVERIFIED, 9))
    packet = p.compact()
    assert calm.display_band == TrustBand.HIGH_RISK
    assert [a["resolved"] for a in packet["alerts"]] == [False]
    assert packet["display_band"] == TrustBand.HIGH_RISK.value


def test_a_catch_up_window_can_raise_an_alert_but_never_replaces_the_current_state():
    p = LivePresenter("s")
    p.consider(_event(TrustBand.UNVERIFIED, 10))
    rev_before = p.latest.window_index
    raised, assessment = p.consider(_event(TrustBand.HIGH_RISK, 2, catchup=True))
    assert raised and assessment is None
    assert p.latest.window_index == rev_before
    assert p.compact()["alerts"][0]["resolved"] is False


def test_a_stale_transcript_revision_is_not_sent():
    p = LivePresenter("s")
    p.consider(_event(TrustBand.UNVERIFIED, 5, rev=7))
    _, stale = p.consider(_event(TrustBand.UNVERIFIED, 6, rev=4))
    assert stale is None


def test_rev_only_ever_increases():
    p = LivePresenter("s")
    revs = []
    for i, band in enumerate([TrustBand.UNVERIFIED, TrustBand.HIGH_RISK, TrustBand.UNVERIFIED]):
        p.consider(_event(band, i + 1))
        revs.append(p.compact()["rev"])
    assert revs == sorted(revs) and len(set(revs)) == len(revs)


def test_a_huge_transcript_and_many_alerts_stay_under_the_packet_limit():
    p = LivePresenter("s")
    long = "pura paisa abhi bhejo " * 4000                        # ~90 KB of transcript
    coverage = [CoverageSpan(start_s=0, end_s=60, scored=True), CoverageSpan(start_s=60, end_s=65, scored=False)]
    p.consider(_event(TrustBand.HIGH_RISK, 1, text=long, coverage=coverage))
    for i in range(2, 40):
        p.alerts.alerts.append(p.alerts.alerts[0].model_copy(update={"alert_id": f"a{i}", "resolved": True}))
    packet = p.compact()
    assert _size(packet) <= MAX_PACKET_BYTES
    assert any(not a["resolved"] for a in packet["alerts"])              # never drops an unresolved alert
    assert packet["coverage"] == {"screened_s": 60.0, "unscreened_s": 5.0, "degraded": False}


def test_before_any_verdict_the_packet_is_honest_about_having_nothing():
    packet = LivePresenter("s").compact(available=False, reason="listener not joined")
    assert packet["display_band"] == "insufficient" and packet["trust_score"] is None
    assert packet["screening_available"] is False and packet["reason"] == "listener not joined"
