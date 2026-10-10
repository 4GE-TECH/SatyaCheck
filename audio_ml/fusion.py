"""
audio_ml/fusion.py — signal-level fusion for the scenario matrix and the CLI.

KEY DESIGN PRINCIPLE
--------------------
Synthetic voice is a risk MULTIPLIER, not a risk SOURCE.

An AI voice is not a crime. Bank IVRs, hospital reminders and delivery
confirmations are all synthetic and all legitimate. Synthetic speech is only
alarming in the presence of scam intent or identity mismatch, so INTENT gates
AUTHENTICITY:

    intent   = max(script_risk, identity_risk if mismatch else 0)
    r_cm_eff = r_cm * (CM_FLOOR + (1 - CM_FLOOR) * intent)

The arithmetic lives in `audio_ml/fusion_core.py`, which the live path uses too. This
module only reads A's signal objects (SpeakerSignal / SpoofSignal / anything with the
same attributes) and reports the band as the overlay colour. It used to carry its own
copy of the formula and — because its config import named constants that do not exist
— its own fallback thresholds, so the scenario matrix tested a fusion production never
ran.

Owner: Member A.
"""

from __future__ import annotations

import logging
from typing import Optional

import config
from audio_ml.fusion_core import authenticity_base, fuse_risk, identity_risk

logger = logging.getLogger(__name__)

#: Production band -> overlay colour (the mapping server/ws_router.py shows the user).
BAND_COLOUR = {
    "verified": "green",
    "caution": "amber",
    "suspicious": "red",
    "high_risk": "red",
    "unverified": "unverified",
    "insufficient": "insufficient",
}


def fuse(speaker, spoof, script, quality: Optional[object] = None):
    """
    Fuse the three branches into a FusionResult.

    Never raises. On any internal failure returns a neutral amber verdict.
    """
    try:
        return _fuse_inner(speaker, spoof, script, quality)
    except Exception as e:  # pragma: no cover
        logger.exception("fusion failed: %s", e)
        return _result(50, "amber", "identity_check",
                       {"asv": 0.5, "cm": 0.5, "text": 0.5, "error": 1.0},
                       dict(config.WEIGHTS_IDENTITY_CHECK))


def _fuse_inner(speaker, spoof, script, quality):
    if quality is not None and getattr(quality, "insufficient", False):
        return _result(0, "insufficient", "identity_check",
                       {"asv": 0.0, "cm": 0.0, "text": 0.0},
                       {"asv": 0.0, "cm": 0.0, "text": 0.0})

    verdict = getattr(speaker, "verdict", "unknown")
    raw = float(getattr(speaker, "raw_cosine", 0.0) or 0.0)
    flagged = int(getattr(speaker, "flagged_voice_hits", 0) or 0)
    # An anomalously PERFECT match is not a better match — natural speech never repeats
    # that exactly. It is the signature of a replayed recording.
    replay = verdict == "match" and raw > config.REPLAY_COSINE_THRESHOLD

    score = getattr(spoof, "score", 0.5)
    score = 0.5 if score is None else float(score)
    peak = getattr(spoof, "peak", score)
    peak = score if peak is None else float(peak)
    r_cm = authenticity_base(score, peak, partial=getattr(spoof, "verdict", "") == "partial_synthetic")
    r_text = float(getattr(script, "risk", 0.0) or 0.0)
    r_asv = identity_risk(verdict)

    core = fuse_risk(verdict, r_asv, r_cm, r_text, replay=replay, flagged_hits=flagged)
    band = config.risk_to_band(core.risk, is_authority_check=core.mode == "authority_check")
    breakdown = {
        "asv": round(r_asv, 4),
        "cm_raw": round(r_cm, 4),
        "cm_gated": round(core.r_cm_eff, 4),
        "text": round(r_text, 4),
        "intent": round(core.intent, 4),
        "risk": core.risk,
        "replay_suspected": replay,
        "flagged_voice_hits": flagged,
        "floors": core.floors,
        "production_band": band.value,
    }
    return _result(int(round(config.risk_to_trust_score(core.risk))), BAND_COLOUR[band.value],
                   core.mode, breakdown, core.weights)


def _result(trust, band, mode, breakdown, weights):
    try:
        from audio_ml.signals import FusionResult
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
