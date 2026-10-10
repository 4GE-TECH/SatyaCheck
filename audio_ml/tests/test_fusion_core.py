"""Upgrade plan, Phase 0 step 6: one fusion implementation.

There were two. The live path (`server/orchestrator._compute_fusion`) renormalised over
available branches but had none of the safety floors; `audio_ml.fusion.fuse` had the
floors but was dead at runtime and — because its config import named constants that do
not exist — silently ran on its own fallback thresholds. The scenario matrix tested the
dead one.

`audio_ml/fusion_core.py` is now the only arithmetic. These pin it directly.
"""

from __future__ import annotations

import pytest

import config
from audio_ml.fusion_core import authenticity_base, fuse_risk, identity_risk


# --- shared input rules ----------------------------------------------------------------------

def test_identity_risk_is_neutral_for_unknown():
    assert identity_risk("unknown") == 0.5
    assert identity_risk("match") < 0.5 < identity_risk("mismatch")


def test_partial_synthetic_blends_the_peak_back_in():
    """Median alone hides a hybrid attack (human, then a cloned voice for the ask)."""
    assert authenticity_base(0.30, 0.93, partial=False) == pytest.approx(0.30)
    blended = authenticity_base(0.30, 0.93, partial=True)
    assert 0.30 < blended < 0.93
    assert blended == pytest.approx(0.30 + config.FUSION_PARTIAL_BLEND * 0.63)


# --- the gate and the weights -----------------------------------------------------------

def test_a_synthetic_voice_with_no_intent_is_damped():
    r = fuse_risk("unknown", 0.5, r_cm=0.95, r_text=0.0)
    assert r.r_cm_eff == pytest.approx(0.95 * config.CM_FLOOR)
    assert r.mode == "authority_check"


def test_mismatch_counts_as_intent_for_the_gate():
    stranger = fuse_risk("unknown", 0.5, r_cm=0.9, r_text=0.1)
    impostor = fuse_risk("mismatch", 0.85, r_cm=0.9, r_text=0.1)
    assert impostor.intent == pytest.approx(0.85)
    assert impostor.r_cm_eff > stranger.r_cm_eff


def test_weights_follow_the_mode_and_renormalise_over_live_branches():
    r = fuse_risk("match", 0.15, r_cm=0.1, r_text=0.1, cm_available=False)
    assert r.weights["cm"] == 0.0
    assert sum(r.weights.values()) == pytest.approx(1.0, abs=1e-3)
    assert r.weights["asv"] == pytest.approx(0.40 / 0.65, abs=1e-3)


def test_dead_text_reads_as_neutral_intent_not_zero():
    r = fuse_risk("unknown", 0.5, r_cm=0.9, r_text=0.0, text_available=False)
    assert r.intent == 0.5
    assert r.weights["text"] == 0.0


# --- the floors --------------------------------------------------------------------------

def test_intent_alone_reaches_high_risk_for_an_unverified_caller():
    """A human scammer is genuinely human. A clear scam script must stand on its own."""
    r = fuse_risk("unknown", 0.5, r_cm=0.05, r_text=0.88)
    assert r.risk >= 0.88 - 1e-9
    assert "intent" in r.floors
    assert config.risk_to_band(r.risk, is_authority_check=True).value == "high_risk"


def test_a_verified_caller_dampens_intent_but_does_not_erase_it():
    r = fuse_risk("match", 0.15, r_cm=0.05, r_text=0.62)
    assert r.risk == pytest.approx(0.62 * config.FUSION_MATCHED_TEXT_FLOOR, abs=1e-4)
    assert config.risk_to_band(r.risk).value in ("caution", "suspicious")


def test_dead_text_applies_no_intent_floor():
    r = fuse_risk("unknown", 0.5, r_cm=0.0, r_text=0.95, text_available=False)
    assert "intent" not in r.floors


def test_a_flagged_voice_is_near_decisive():
    r = fuse_risk("unknown", 0.5, r_cm=0.0, r_text=0.0, flagged_hits=1)
    assert r.risk == pytest.approx(config.FUSION_FLAGGED_RISK_FLOOR)
    assert "flagged_voice" in r.floors
    assert config.risk_to_band(r.risk, is_authority_check=True).value == "high_risk"


def test_a_replay_is_never_verified():
    r = fuse_risk("match", 0.15, r_cm=0.05, r_text=0.0, replay=True)
    assert r.risk >= config.FUSION_REPLAY_RISK_FLOOR
    assert "replay" in r.floors
    assert config.risk_to_band(r.risk).value == "caution", "never verified, but on its own not red either"


def test_floors_only_raise_risk():
    """The weighted sum here is ~0.90; the intent floor lifts it to 0.95, and the lower
    flagged (0.85) and replay (0.55) floors do not pull it down or register."""
    r = fuse_risk("mismatch", 0.85, r_cm=0.95, r_text=0.95, replay=True, flagged_hits=2)
    assert r.risk == pytest.approx(0.95)
    assert r.floors == ["intent"]


@pytest.mark.parametrize("verdict", ["match", "mismatch", "unknown"])
@pytest.mark.parametrize("cm", [0.0, 0.5, 1.0])
@pytest.mark.parametrize("text", [0.0, 0.5, 1.0])
def test_risk_stays_in_range(verdict, cm, text):
    r = fuse_risk(verdict, identity_risk(verdict), r_cm=cm, r_text=text, replay=True, flagged_hits=1)
    assert 0.0 <= r.risk <= 1.0


def test_audio_ml_fuse_uses_the_core_and_production_thresholds():
    """No more silent fallback constants: fuse() reads config through the core."""
    from types import SimpleNamespace as S

    from audio_ml import fusion

    r = fusion.fuse(S(verdict="unknown", norm_score=0.1, raw_cosine=0.1, flagged_voice_hits=0),
                    S(score=0.07, peak=0.12, verdict="bonafide"), S(risk=0.88))
    core = fuse_risk("unknown", 0.5, r_cm=0.07, r_text=0.88)
    assert r.trust_score == pytest.approx(config.risk_to_trust_score(core.risk), abs=1)
    assert r.band == "red"
