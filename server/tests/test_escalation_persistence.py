"""Item 9: a warning band must persist for N consecutive windows before it is shown.

One noisy 9 s window — a cough over the mic, a Whisper hallucination, a burst of
synthetic-looking codec noise — used to latch a call red for the rest of the session,
because `SessionState` escalated on any single window and never came back down.
`EscalationGate` requires `config.ESCALATION_PERSISTENCE_N` consecutive windows at or
above a band before confirming it; once confirmed, it latches exactly as before.

N=1 is today's behaviour, pinned by test_session_band_escalation.py, which must keep
passing unchanged.
"""

from __future__ import annotations

import pytest

import config
from contracts import OperatingMode, TrustBand
from server.escalation import EscalationGate
from server.tests.test_overlay_update import _response
from server.ws_router import SessionState

U, C, S, H = TrustBand.UNVERIFIED, TrustBand.CAUTION, TrustBand.SUSPICIOUS, TrustBand.HIGH_RISK


def _scored(band: TrustBand, trust: float):
    r = _response(band=band, mode=OperatingMode.AUTHORITY_CHECK)
    return r.model_copy(update={"fusion": r.fusion.model_copy(update={"trust_score": trust})})


def _run(n: int, windows):
    gate = EscalationGate(n)
    return [gate.apply(_scored(band, trust)).fusion for band, trust in windows]


def test_the_default_is_today_behaviour():
    assert config.ESCALATION_PERSISTENCE_N == 1


def test_n1_escalates_on_a_single_window_and_latches():
    shown = _run(1, [(U, 90.0), (H, 20.0), (U, 88.0)])
    assert [f.band for f in shown] == [U, H, H]
    assert [f.trust_score for f in shown] == [90.0, 20.0, 20.0]


def test_two_risky_windows_then_a_calm_one_never_escalate_at_n3():
    shown = _run(3, [(U, 90.0), (S, 45.0), (S, 44.0), (U, 89.0)])
    assert [f.band for f in shown] == [U, U, U, U]


def test_three_consecutive_risky_windows_escalate_and_latch_at_n3():
    shown = _run(3, [(U, 90.0), (S, 45.0), (S, 44.0), (S, 46.0), (U, 89.0)])
    assert [f.band for f in shown] == [U, U, U, S, S]


def test_the_score_floor_only_takes_confirmed_windows():
    """Score and band must never disagree: no 45 shown under a grey band."""
    shown = _run(3, [(U, 90.0), (S, 45.0), (S, 44.0), (S, 46.0), (U, 89.0)])
    assert [f.trust_score for f in shown] == [90.0, 90.0, 90.0, 44.0, 44.0]


def test_a_mixed_run_confirms_only_the_band_all_windows_reached():
    shown = _run(3, [(C, 70.0), (S, 50.0), (S, 48.0)])
    assert shown[-1].band == C


def test_a_higher_band_still_needs_its_own_run_after_a_latch():
    shown = _run(2, [(S, 50.0), (S, 49.0), (H, 20.0), (S, 48.0), (H, 21.0), (H, 19.0)])
    assert [f.band for f in shown] == [U, S, S, S, S, H]


def test_an_unconfirmed_first_window_shows_neutral_not_the_warning():
    shown = _run(3, [(H, 15.0)])
    assert shown[0].band == U
    assert shown[0].trust_score == 50.0


def test_insufficient_windows_break_a_run():
    """A window too short or noisy to score is not evidence the warning persisted."""
    shown = _run(2, [(S, 50.0), (TrustBand.INSUFFICIENT, 50.0), (S, 49.0)])
    assert [f.band for f in shown] == [U, TrustBand.INSUFFICIENT, U]


def test_calm_bands_pass_through_untouched_when_nothing_is_latched():
    shown = _run(3, [(TrustBand.VERIFIED, 92.0), (U, 88.0)])
    assert [f.band for f in shown] == [TrustBand.VERIFIED, U]


def test_session_state_uses_the_configured_n(monkeypatch):
    monkeypatch.setattr(config, "ESCALATION_PERSISTENCE_N", 2)
    state = SessionState("s")
    assert state.update(_scored(H, 20.0)).fusion.band == U
    assert state.update(_scored(H, 19.0)).fusion.band == H


def test_n_below_one_is_rejected():
    with pytest.raises(ValueError):
        EscalationGate(0)


def _old_session_update(windows):
    """The pre-item-9 `SessionState.update`, copied verbatim in logic, as the oracle."""
    rank = {C: 1, S: 2, H: 3}
    floor, worst, out = 100.0, None, []
    for band, trust in windows:
        shown_trust = trust
        if trust < floor:
            floor = trust
        elif trust > floor:
            shown_trust = floor
        shown_band = band
        if rank.get(band, 0) >= rank.get(worst, 0):
            if rank.get(band, 0) > 0:
                worst = band
        else:
            shown_band = worst
        out.append((shown_band, shown_trust))
    return out


def test_n1_matches_the_old_session_logic_on_random_calls():
    import random

    rng = random.Random(9)
    bands = [U, TrustBand.VERIFIED, TrustBand.INSUFFICIENT, C, S, H]
    for _ in range(500):
        windows = [(rng.choice(bands), round(rng.uniform(5, 99), 1)) for _ in range(rng.randint(1, 12))]
        got = [(f.band, f.trust_score) for f in _run(1, windows)]
        assert got == _old_session_update(windows), windows
