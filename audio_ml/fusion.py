"""
audio_ml/fusion.py — SatyaCheck signal fusion (REVISED: intent-gated)

KEY DESIGN PRINCIPLE
--------------------
Synthetic voice is a risk MULTIPLIER, not a risk SOURCE.

An AI voice is not a crime. Bank IVRs, hospital reminders and delivery
confirmations are all synthetic and all legitimate. Synthetic speech is only
alarming in the presence of scam intent or identity mismatch.

So instead of summing three independent signals, we let INTENT gate
AUTHENTICITY:

    intent  = max(script_risk, identity_risk if mismatch else 0)
    r_cm_eff = r_cm * (CM_FLOOR + (1 - CM_FLOOR) * intent)

This kills the legitimate-IVR false positive without weakening the
cloned-family-member true positive.

Owner: Member A.  Consumed by: server/session.py via audio_ml/api.py
"""

from __future__ import annotations
import math
from typing import Optional

# --------------------------------------------------------------------------
# Config (falls back to local defaults so this file runs standalone at H1:00,
# before C's config.py has landed)
# --------------------------------------------------------------------------
try:
    from config import (
        SPEAKER_MATCH_THRESHOLD, SPEAKER_UNKNOWN_FLOOR,
        BAND_GREEN, BAND_AMBER, W_IDENTITY, W_AUTHORITY,
    )
except Exception:  # pragma: no cover
    SPEAKER_MATCH_THRESHOLD = 0.62
    SPEAKER_UNKNOWN_FLOOR = 0.35
    BAND_GREEN = 70
    BAND_AMBER = 40
    W_IDENTITY = {"asv": 0.40, "cm": 0.35, "text": 0.25}
    W_AUTHORITY = {"asv": 0.10, "cm": 0.45, "text": 0.45}

# Tunables owned by A. Calibrate at H8:30 on the recorded eval set.
TAU = 0.12                 # sigmoid steepness around the speaker threshold
CM_FLOOR = 0.25            # residual weight of synthetic-voice evidence at zero intent
REPLAY_COSINE = 0.95       # above this, an "excellent match" is anomalous
REPLAY_RISK_FLOOR = 0.55   # replay caps us at amber, never green
FLAGGED_RISK_FLOOR = 0.85  # a hit on the reported-scammer list is near-decisive
PARTIAL_BLEND = 0.5        # how much of `peak` to blend in for partial_synthetic

# INTENT SUFFICIENCY.
# A low anti-spoof score is NOT evidence of safety — a human scammer is
# genuinely human. When the caller is not a verified enrolled person, a clear
# match to a known scam playbook is decisive on its own; voice authenticity
# only corroborates. Without this, a real human running a digital-arrest script
# is mathematically capped around 0.55 risk and can never turn red.
MATCHED_TEXT_FLOOR = 0.55  # verified identity dampens (but does not erase) intent


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _sigmoid(x: float) -> float:
    if x < -60:
        return 0.0
    if x > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


# --------------------------------------------------------------------------
# Component risks
# --------------------------------------------------------------------------
def identity_risk(speaker) -> tuple[float, bool]:
    """
    Returns (risk in 0..1, replay_suspected).

    THREE verdicts, and `unknown` is NEUTRAL (0.5), not guilty. If unknown were
    treated as guilty, every genuine stranger — a real bank, a delivery driver,
    a doctor — turns red and the product becomes noise people learn to ignore.
    """
    verdict = getattr(speaker, "verdict", "unknown")
    norm = float(getattr(speaker, "norm_score", 0.0) or 0.0)
    raw = float(getattr(speaker, "raw_cosine", 0.0) or 0.0)

    # An anomalously PERFECT match is not a better match — natural speech never
    # repeats that exactly. It is the signature of a replayed recording.
    replay = (verdict == "match") and (raw >= REPLAY_COSINE)

    if verdict == "unknown":
        return 0.5, replay

    # High norm_score -> low risk. Low norm_score -> high risk.
    r = 1.0 - _sigmoid((norm - SPEAKER_MATCH_THRESHOLD) / TAU)
    return _clamp(r), replay


def authenticity_base(spoof) -> float:
    """
    Base synthetic-speech evidence, BEFORE intent gating.

    For a hybrid call (human -> AI during the sensitive part -> human), the
    median is exactly the statistic that hides the attack. When the branch
    reports `partial_synthetic`, blend the peak back in.
    """
    score = float(getattr(spoof, "score", 0.5) or 0.5)
    peak = float(getattr(spoof, "peak", score) or score)
    verdict = getattr(spoof, "verdict", "uncertain")

    if verdict == "partial_synthetic":
        return _clamp(score + PARTIAL_BLEND * (peak - score))
    return _clamp(score)


def intent_risk(script, r_asv: float, speaker_verdict: str) -> float:
    """
    How much does this call LOOK like fraud, independent of voice authenticity?

    Identity mismatch counts as intent evidence (someone is pretending to be a
    specific person). Identity `unknown` does NOT — a stranger is not intent.
    """
    r_text = _clamp(float(getattr(script, "risk", 0.0) or 0.0))
    if speaker_verdict == "mismatch":
        return max(r_text, r_asv)
    return r_text


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------
def fuse(speaker, spoof, script, quality: Optional[object] = None):
    """
    Fuse the three branches into a FusionResult.

    Never raises. On any internal failure returns a neutral amber verdict.
    """
    try:
        return _fuse_inner(speaker, spoof, script, quality)
    except Exception as e:  # pragma: no cover
        import logging
        logging.exception("fusion failed: %s", e)
        return _result(50, "amber", "identity_check",
                       {"asv": 0.5, "cm": 0.5, "text": 0.5, "error": 1.0},
                       W_IDENTITY)


def _fuse_inner(speaker, spoof, script, quality):
    # ---- quality gate -----------------------------------------------------
    if quality is not None and getattr(quality, "insufficient", False):
        return _result(0, "insufficient", "identity_check",
                       {"asv": 0.0, "cm": 0.0, "text": 0.0},
                       {"asv": 0.0, "cm": 0.0, "text": 0.0})

    verdict = getattr(speaker, "verdict", "unknown")

    # ---- component risks --------------------------------------------------
    r_asv, replay = identity_risk(speaker)
    r_cm_raw = authenticity_base(spoof)
    r_text = _clamp(float(getattr(script, "risk", 0.0) or 0.0))

    # ---- THE GATE ---------------------------------------------------------
    intent = intent_risk(script, r_asv, verdict)
    r_cm = r_cm_raw * (CM_FLOOR + (1.0 - CM_FLOOR) * intent)

    # ---- mode-aware weights ----------------------------------------------
    # Speaker branch ABSTAINS when nobody enrolled is close. Weight shifts to
    # the two branches that actually carry information about this call.
    if verdict == "unknown":
        mode = "authority_check"
        w = dict(W_AUTHORITY)
    else:
        mode = "identity_check"
        w = dict(W_IDENTITY)

    risk = w["asv"] * r_asv + w["cm"] * r_cm + w["text"] * r_text

    # ---- intent sufficiency ----------------------------------------------
    # If we have NOT verified the caller as a known person, a strong scam-script
    # match stands on its own. If we HAVE verified them, identity vouches for
    # them and intent is dampened — a genuine family member making an odd
    # request should land amber ("verify before paying"), never red.
    if verdict == "match":
        risk = max(risk, r_text * MATCHED_TEXT_FLOOR)
    else:
        risk = max(risk, r_text)

    # ---- overrides --------------------------------------------------------
    flagged = int(getattr(speaker, "flagged_voice_hits", 0) or 0)
    if flagged > 0:
        risk = max(risk, FLAGGED_RISK_FLOOR)
    if replay:
        risk = max(risk, REPLAY_RISK_FLOOR)

    risk = _clamp(risk)
    trust = int(round(100 * (1.0 - risk)))

    # ---- band -------------------------------------------------------------
    # CRITICAL: in authority_check we never show green. We verified nobody.
    if mode == "authority_check" and trust >= BAND_GREEN:
        band = "unverified"
    elif trust >= BAND_GREEN:
        band = "green"
    elif trust >= BAND_AMBER:
        band = "amber"
    else:
        band = "red"

    breakdown = {
        "asv": round(r_asv, 4),
        "cm_raw": round(r_cm_raw, 4),
        "cm_gated": round(r_cm, 4),
        "text": round(r_text, 4),
        "intent": round(intent, 4),
        "replay_suspected": replay,
        "flagged_voice_hits": flagged,
    }
    return _result(trust, band, mode, breakdown, w)


def _result(trust, band, mode, breakdown, weights):
    try:
        from contracts import FusionResult
        return FusionResult(trust_score=trust, band=band, mode=mode,
                            risk_breakdown=breakdown, weights_used=weights)
    except Exception:
        return {"trust_score": trust, "band": band, "mode": mode,
                "risk_breakdown": breakdown, "weights_used": weights}


# --------------------------------------------------------------------------
# Smoke test:  python -m audio_ml.fusion
# --------------------------------------------------------------------------
if __name__ == "__main__":
    from types import SimpleNamespace as S

    def show(name, sp, cm, sc):
        r = fuse(sp, cm, sc)
        d = r if isinstance(r, dict) else r.model_dump()
        print(f"{name:<38} trust={d['trust_score']:>3}  {d['band']:<11} "
              f"{d['mode']:<16} intent={d['risk_breakdown']['intent']:.2f} "
              f"cm {d['risk_breakdown']['cm_raw']:.2f}->{d['risk_breakdown']['cm_gated']:.2f}")

    # legit bank IVR: synthetic, but zero intent -> must NOT be red
    show("legit AI IVR",
         S(verdict="unknown", norm_score=0.10, raw_cosine=0.10, flagged_voice_hits=0),
         S(score=0.92, peak=0.95, verdict="synthetic"),
         S(risk=0.05))

    # cloned family member demanding money -> must be red
    show("cloned family emergency",
         S(verdict="mismatch", norm_score=0.31, raw_cosine=0.31, flagged_voice_hits=0),
         S(score=0.94, peak=0.96, verdict="synthetic"),
         S(risk=0.88))

    # genuine call -> green
    show("genuine call",
         S(verdict="match", norm_score=0.78, raw_cosine=0.78, flagged_voice_hits=0),
         S(score=0.06, peak=0.11, verdict="bonafide"),
         S(risk=0.04))

    # hybrid: median says bonafide, peak says otherwise
    show("hybrid human/AI",
         S(verdict="unknown", norm_score=0.12, raw_cosine=0.12, flagged_voice_hits=0),
         S(score=0.30, peak=0.93, verdict="partial_synthetic"),
         S(risk=0.80))
