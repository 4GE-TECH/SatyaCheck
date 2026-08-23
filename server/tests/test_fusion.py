"""Tests for `server/orchestrator._compute_fusion`.

The documented formula (CLAUDE.md, "Synthetic voice is a multiplier, not a source"):

    intent   = max(script_risk, identity_risk if verdict == "mismatch" else 0.0)
    r_cm_eff = r_cm * (CM_FLOOR + (1 - CM_FLOOR) * intent)
    combined = sum(w_i * r_i), renormalised over the *active* branches
    trust    = (1 - combined) * 100

The bug these were written for: fusion renormalised when the **text** branch
abstained but not when the **anti-spoof** branch did. `AntiSpoofResult.neutral()`
carries `risk = 0.0`, which in a weighted sum does not read as "no opinion" — it
reads as "definitely authentic" and actively raises trust. With the spoof branch cut
(no checkpoint exists, PLAN.md's H6:00 contingency), its 0.35 weight in
identity_check contributed a permanent 0.35 of "this is genuine" to every call.

Cutting a branch has to mean it abstains, not that it votes innocent.
"""

from __future__ import annotations

import pytest

import config
from contracts import (
    AntiSpoofResult,
    OperatingMode,
    ScriptAnalysisResult,
    SpeakerVerdict,
    SpeakerVerificationResult,
)
from server.orchestrator import _compute_fusion


def _speaker(verdict: str, risk: float) -> SpeakerVerificationResult:
    return SpeakerVerificationResult(verdict=verdict, risk=risk, raw_score=0.0, norm_score=0.0)


def _script(risk: float, available: bool = True) -> ScriptAnalysisResult:
    result = ScriptAnalysisResult.neutral()
    result.risk = risk
    result.details["available"] = available
    return result


def _spoof(risk: float, available: bool = True) -> AntiSpoofResult:
    result = AntiSpoofResult.neutral()
    result.risk = risk
    result.median_score = risk
    result.details["available"] = available
    return result


def _spoof_cut() -> AntiSpoofResult:
    """Exactly what `_mock_spoof_branch` produces when USE_REAL_SPOOF is off."""
    from server.orchestrator import _mock_spoof_branch

    return _mock_spoof_branch("ignored.wav")


# --- the abstention bug -------------------------------------------------------

def test_a_cut_spoof_branch_does_not_raise_trust():
    """The defect, stated as the thing a user would notice.

    Same speaker, same transcript. The only difference is whether the anti-spoof
    branch reported or abstained. An abstaining branch must not make the call look
    *safer* than one that measured nothing at all.
    """
    speaker = _speaker(SpeakerVerdict.MISMATCH, 0.85)
    script = _script(0.90)

    cut = _compute_fusion(speaker, _spoof_cut(), script)
    measured_synthetic = _compute_fusion(speaker, _spoof(0.9), script)

    assert cut.trust_score <= measured_synthetic.trust_score + 1e-6, (
        f"abstaining scored MORE trustworthy ({cut.trust_score}) than a branch that "
        f"found synthetic speech ({measured_synthetic.trust_score})"
    )
    # And the real point: a cut branch must not cap the achievable risk.
    assert cut.trust_score < 40.0, (
        f"a mismatched speaker reading a 0.90-risk scam script scored "
        f"trust={cut.trust_score} — the cut spoof branch is voting 'authentic'"
    )


def test_a_cut_spoof_branch_is_excluded_from_the_weights():
    """Transparency: `weights_used` has to show what actually contributed."""
    fusion = _compute_fusion(_speaker(SpeakerVerdict.MATCH, 0.15), _spoof_cut(), _script(0.5))

    assert fusion.weights_used.cm_weight == 0.0, (
        "the spoof branch abstained but still carries weight in the reported breakdown"
    )
    total = (
        fusion.weights_used.asv_weight
        + fusion.weights_used.cm_weight
        + fusion.weights_used.text_weight
    )
    assert total == pytest.approx(1.0, abs=1e-3), f"weights sum to {total}, not 1.0"


def test_a_scam_script_can_still_reach_high_risk_with_spoof_cut():
    """Two signals must still span the full range, or the top band is unreachable.

    If the cut branch keeps its weight, `combined_risk` caps at 0.65 in
    identity_check and nothing can ever be scored red — the product loses its
    strongest verdict silently.
    """
    fusion = _compute_fusion(
        _speaker(SpeakerVerdict.MISMATCH, 1.0), _spoof_cut(), _script(1.0)
    )

    assert fusion.risk_score == pytest.approx(1.0, abs=1e-3), (
        f"maximum evidence on both live branches produced risk={fusion.risk_score}"
    )


def test_both_branches_cut_leaves_identity_alone_spanning_the_range():
    fusion = _compute_fusion(
        _speaker(SpeakerVerdict.MISMATCH, 1.0), _spoof_cut(), _script(0.0, available=False)
    )

    assert fusion.weights_used.asv_weight == pytest.approx(1.0, abs=1e-3)
    assert fusion.risk_score == pytest.approx(1.0, abs=1e-3)


# --- the rules that must not regress -----------------------------------------

def test_a_legitimate_synthetic_ivr_does_not_go_red():
    """CLAUDE.md: "Bank IVRs are synthetic and legitimate."

    High authenticity risk, zero intent. Without the intent gate this is the case
    that makes every automated bank call amber and the product unusable.
    """
    fusion = _compute_fusion(
        _speaker(SpeakerVerdict.UNKNOWN, 0.5), _spoof(0.95), _script(0.05)
    )

    assert fusion.band.value != "high_risk"
    assert fusion.authenticity_risk_effective < fusion.authenticity_risk, (
        "the intent gate did not damp a synthetic-but-benign call"
    )


def test_unknown_speaker_never_shows_green():
    """CLAUDE.md: "Never show green in authority_check. We verified nobody."

    A perfectly clean stranger — no synthesis, no scam language. Trust is high, and
    the band still must not claim verification.
    """
    fusion = _compute_fusion(
        _speaker(SpeakerVerdict.UNKNOWN, 0.5), _spoof(0.0), _script(0.0)
    )

    assert fusion.mode == OperatingMode.AUTHORITY_CHECK
    assert fusion.band.value != "verified", (
        f"an unverified stranger was shown as verified (trust={fusion.trust_score})"
    )


def test_a_dead_text_branch_lowers_trust():
    """E1. A branch that produced nothing must not be read as 'nothing wrong'.

    `risk=0.0` with `available=False` is an abstention; `risk=0.0` with
    `available=True` is a measured benign call. They must not score the same.
    """
    speaker = _speaker(SpeakerVerdict.UNKNOWN, 0.5)

    dead = _compute_fusion(speaker, _spoof(0.3), _script(0.0, available=False))
    benign = _compute_fusion(speaker, _spoof(0.3), _script(0.0, available=True))

    assert dead.trust_score < benign.trust_score, (
        f"a dead ASR branch ({dead.trust_score}) scored as well as a measured "
        f"benign transcript ({benign.trust_score})"
    )


def test_mismatch_feeds_the_intent_gate():
    """A cloned voice is intent evidence even when the transcript is unremarkable."""
    stranger = _compute_fusion(_speaker(SpeakerVerdict.UNKNOWN, 0.5), _spoof(0.9), _script(0.0))
    impostor = _compute_fusion(_speaker(SpeakerVerdict.MISMATCH, 0.9), _spoof(0.9), _script(0.0))

    assert impostor.authenticity_risk_effective > stranger.authenticity_risk_effective


def test_trust_score_stays_in_range():
    for verdict, risk in ((SpeakerVerdict.MATCH, 0.0), (SpeakerVerdict.MISMATCH, 1.0)):
        for spoof_risk in (0.0, 0.5, 1.0):
            for text_risk in (0.0, 0.5, 1.0):
                fusion = _compute_fusion(
                    _speaker(verdict, risk), _spoof(spoof_risk), _script(text_risk)
                )
                assert 0.0 <= fusion.trust_score <= 100.0
                assert 0.0 <= fusion.risk_score <= 1.0


# --- what the evidence panel is allowed to claim ------------------------------

def test_a_cut_spoof_branch_does_not_claim_the_audio_is_authentic():
    """The evidence panel must not assert something the branch never measured.

    With no anti-spoof checkpoint the branch abstains, and the reason-code builder
    fell through to `RC_AUDIO_BONAFIDE` — "No significant synthetic speech artifacts
    detected. Audio appears to be organic human speech." Screening a cloned voice
    would show exactly that, as evidence, under a red score. A judge reading the
    panel would be right to call it.
    """
    fusion = _compute_fusion(
        _speaker(SpeakerVerdict.MISMATCH, 0.85), _spoof_cut(), _script(0.9)
    )
    codes = {code.code for code in fusion.reason_codes}

    assert "RC_AUDIO_BONAFIDE" not in codes, (
        "claimed the audio is organic human speech without running the model"
    )
    assert "RC_SPOOF_UNAVAILABLE" in codes, (
        f"no abstention code for the cut branch; got {sorted(codes)}"
    )

    abstention = next(c for c in fusion.reason_codes if c.code == "RC_SPOOF_UNAVAILABLE")
    assert "not" in abstention.explanation.lower() or "unavailable" in abstention.explanation.lower()


def test_a_measured_clean_result_still_reports_bonafide():
    """The honest case must not be lost to the abstention fix."""
    fusion = _compute_fusion(
        _speaker(SpeakerVerdict.MATCH, 0.15), _spoof(0.05, available=True), _script(0.0)
    )
    codes = {code.code for code in fusion.reason_codes}

    assert "RC_AUDIO_BONAFIDE" in codes
    assert "RC_SPOOF_UNAVAILABLE" not in codes


def test_identity_reason_codes_quote_the_threshold_actually_applied():
    """A displayed threshold has to be the one the decision used.

    The verdict is decided on raw cosine against `SPEAKER_MATCH_THRESHOLD` (0.85),
    but the codes quoted `ASV_MATCH_THRESHOLD` (1.20) — a different scale entirely,
    left over from when the verdict came off the s-norm score. Showing "> 1.2" beside
    a cosine of 0.95 is not evidence, it is noise.
    """
    for verdict, risk in ((SpeakerVerdict.MATCH, 0.15), (SpeakerVerdict.MISMATCH, 0.85)):
        fusion = _compute_fusion(_speaker(verdict, risk), _spoof_cut(), _script(0.5))
        identity = [c for c in fusion.reason_codes if c.code.startswith("RC_SPEAKER_")]
        assert identity, f"no identity reason code for verdict={verdict}"
        for code in identity:
            assert str(config.ASV_MATCH_THRESHOLD) not in code.threshold, (
                f"{code.code} quotes the fusion-scale threshold "
                f"{config.ASV_MATCH_THRESHOLD}, not the cosine cut actually applied"
            )
