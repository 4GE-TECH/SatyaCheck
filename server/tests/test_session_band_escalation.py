"""A session's band never improves once it has raised a warning.

`SessionState.update` already kept the lowest trust score, but the band came from the
current 9 s window alone. Once the scam phrase scrolled out of the window the band fell
back to `unverified`, so the overlay went red -> grey mid-call and the end-of-call
notification could read grey for a call that had been red.
"""

from __future__ import annotations

from contracts import OperatingMode, TrustBand
from server.tests.test_overlay_update import _response
from server.ws_router import SessionState, _build_overlay_update


def _scored(band: TrustBand, trust: float):
    r = _response(band=band, mode=OperatingMode.AUTHORITY_CHECK)
    return r.model_copy(update={"fusion": r.fusion.model_copy(update={"trust_score": trust})})


def test_red_does_not_fall_back_to_grey_when_the_phrase_leaves_the_window():
    state = SessionState("s")
    state.update(_scored(TrustBand.UNVERIFIED, 90.0))
    state.update(_scored(TrustBand.HIGH_RISK, 20.0))
    later = state.update(_scored(TrustBand.UNVERIFIED, 88.0))
    assert later.fusion.band == TrustBand.HIGH_RISK
    assert later.fusion.trust_score == 20.0
    assert _build_overlay_update("s", later)["state"] == "red"


def test_amber_does_not_fall_back_but_can_still_escalate_to_red():
    state = SessionState("s")
    state.update(_scored(TrustBand.CAUTION, 70.0))
    assert state.update(_scored(TrustBand.UNVERIFIED, 90.0)).fusion.band == TrustBand.CAUTION
    assert state.update(_scored(TrustBand.SUSPICIOUS, 50.0)).fusion.band == TrustBand.SUSPICIOUS


def test_a_calm_call_is_untouched():
    state = SessionState("s")
    state.update(_scored(TrustBand.UNVERIFIED, 90.0))
    assert state.update(_scored(TrustBand.VERIFIED, 92.0)).fusion.band == TrustBand.VERIFIED
