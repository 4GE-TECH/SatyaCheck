"""Without the latch, a session follows its evidence back up.

Seen on a replayed Exotel call: a synthetic voice saying something harmless dropped the
session to suspicious 39.8 while the transcript was still pending, and the session
stayed there for the rest of the call — even after the harmless transcript arrived and
every window read ~82. The user's call: the session must not stay stuck once it drops,
and the final verdict is judged on the whole call.

`EscalationGate(n, latch=False)` keeps persistence (a warning still needs N windows in a
row) but shows the current run, not the worst one so far.
"""

from __future__ import annotations

from contracts import TrustBand
from server.escalation import EscalationGate
from server.tests.test_escalation_persistence import _scored

U, C, S, H = TrustBand.UNVERIFIED, TrustBand.CAUTION, TrustBand.SUSPICIOUS, TrustBand.HIGH_RISK


def _run(n, windows):
    gate = EscalationGate(n, latch=False)
    out = []
    for band, trust in windows:
        f = gate.apply(_scored(band, trust)).fusion
        out.append((f.band, f.trust_score, gate.latched_band))
    return out


def test_n1_follows_every_window_back_up():
    shown = _run(1, [(U, 90.0), (H, 20.0), (U, 88.0)])
    assert [(b, t) for b, t, _ in shown] == [(U, 90.0), (H, 20.0), (U, 88.0)]
    assert [l for _, _, l in shown] == [None, H, None]


def test_persistence_still_applies_and_a_confirmed_warning_clears_when_the_run_ends():
    shown = _run(3, [(U, 90.0), (S, 45.0), (S, 44.0), (S, 46.0), (U, 89.0)])
    assert [b for b, _, _ in shown] == [U, U, U, S, U]
    assert [t for _, t, _ in shown] == [90.0, 90.0, 90.0, 44.0, 89.0]


def test_one_noisy_window_still_does_not_escalate():
    shown = _run(3, [(U, 90.0), (H, 20.0), (U, 89.0)])
    assert [b for b, _, _ in shown] == [U, U, U]


def test_the_latching_gate_is_unchanged():
    gate = EscalationGate(1)
    bands = [gate.apply(_scored(b, t)).fusion.band for b, t in [(U, 90.0), (H, 20.0), (U, 88.0)]]
    assert bands == [U, H, H]
