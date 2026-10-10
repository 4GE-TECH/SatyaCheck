"""
audio_ml/fusion_core.py — the one fusion implementation.

Pure arithmetic on plain numbers: no server imports, no contracts, no I/O. Both the
live path (`server/orchestrator._compute_fusion`, through `audio_ml.api.fuse_risk`) and
`audio_ml.fusion.fuse` call it, so the scenario matrix tests what production runs.

    intent   = max(r_text, r_asv if verdict == "mismatch" else 0)     (0.5 if text is dead)
    r_cm_eff = r_cm * (CM_FLOOR + (1 - CM_FLOOR) * intent)            synthetic voice gates on intent
    risk     = sum(w_i * r_i) / sum(w_i) over the branches that ran   a dead branch drops its weight
    risk     = max(risk, floors)                                      intent, flagged voice, replay

Mode: `unknown` -> authority_check (speaker abstains at a neutral 0.5, weights shift);
otherwise identity_check. Every constant lives in config.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import config


@dataclass
class CoreFusion:
    risk: float                      # 0..1, clamped and rounded to 4 places
    mode: str                        # "identity_check" | "authority_check"
    weights: dict[str, float]        # renormalised weights that contributed ({"asv","cm","text"})
    r_cm_eff: float                  # intent-gated authenticity risk
    intent: float                    # the gate's intent value
    floors: list[str] = field(default_factory=list)  # floors that raised the risk, in order applied


def identity_risk(verdict: str) -> float:
    """Identity risk from the verifier's three-way verdict. `unknown` is neutral (0.5)."""
    return config.FUSION_IDENTITY_RISK.get(str(verdict), 0.5)


def authenticity_base(median: float, peak: float, partial: bool) -> float:
    """Synthetic-speech evidence before gating. For a hybrid call the median is exactly the
    statistic that hides the attack, so `partial_synthetic` blends the peak back in."""
    median = _clamp(float(median))
    if not partial:
        return median
    return _clamp(median + config.FUSION_PARTIAL_BLEND * (_clamp(float(peak)) - median))


def fuse_risk(
    verdict: str,
    r_asv: float,
    r_cm: float,
    r_text: float,
    *,
    text_available: bool = True,
    cm_available: bool = True,
    replay: bool = False,
    flagged_hits: int = 0,
) -> CoreFusion:
    """Fuse the three branch risks. Never raises on numeric input."""
    verdict = str(verdict)
    identity_check = verdict != "unknown"
    mode = "identity_check" if identity_check else "authority_check"
    table = config.WEIGHTS_IDENTITY_CHECK if identity_check else config.WEIGHTS_AUTHORITY_CHECK
    r_asv, r_cm, r_text = _clamp(r_asv), _clamp(r_cm), _clamp(r_text)

    # The gate. A dead text branch reads as neutral 0.5, never 0.0: zero would floor the
    # anti-spoof branch exactly when it is the only evidence left.
    identity_for_gate = r_asv if verdict == "mismatch" else 0.0
    intent = max(r_text, identity_for_gate) if text_available else max(0.5, identity_for_gate)
    r_cm_eff = r_cm * (config.CM_FLOOR + (1.0 - config.CM_FLOOR) * intent)

    # Weighted sum over the branches that ran. Identity always participates (in
    # authority_check as a neutral 0.5 at low weight); a dead branch left in at risk 0.0
    # would read as "nothing wrong" and cap the reachable risk.
    contributions = {"asv": (table["asv"], r_asv)}
    if cm_available:
        contributions["cm"] = (table["cm"], r_cm_eff)
    if text_available:
        contributions["text"] = (table["text"], r_text)
    total = sum(w for w, _ in contributions.values())
    risk = sum(w * r for w, r in contributions.values()) / total if total > 0 else 0.5
    weights = {k: (round(contributions[k][0] / total, 4) if k in contributions and total > 0 else 0.0)
               for k in ("asv", "cm", "text")}

    floors: list[str] = []

    def lift(value: float, name: str) -> None:
        nonlocal risk
        if value > risk:
            risk = value
            floors.append(name)

    if text_available:
        lift(r_text * config.FUSION_MATCHED_TEXT_FLOOR if verdict == "match" else r_text, "intent")
    if int(flagged_hits or 0) > 0:
        lift(config.FUSION_FLAGGED_RISK_FLOOR, "flagged_voice")
    if replay:
        lift(config.FUSION_REPLAY_RISK_FLOOR, "replay")

    return CoreFusion(risk=round(_clamp(risk), 4), mode=mode, weights=weights,
                      r_cm_eff=r_cm_eff, intent=intent, floors=floors)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return lo
    if x != x:  # NaN
        return lo
    return max(lo, min(hi, x))


if __name__ == "__main__":
    for name, args in [
        ("legit AI IVR", ("unknown", 0.5, 0.92, 0.05)),
        ("human scammer, KYC", ("unknown", 0.5, 0.07, 0.88)),
        ("cloned family emergency", ("mismatch", 0.85, 0.94, 0.88)),
        ("genuine family, odd request", ("match", 0.15, 0.07, 0.62)),
    ]:
        r = fuse_risk(*args)
        band = config.risk_to_band(r.risk, is_authority_check=r.mode == "authority_check")
        print(f"{name:<30} risk={r.risk:.3f} {band.value:<11} {r.mode:<16} floors={r.floors}")
