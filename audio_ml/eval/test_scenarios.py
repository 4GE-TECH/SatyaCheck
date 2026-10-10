"""
audio_ml/eval/test_scenarios.py — the 12-scenario regression matrix

Runs all twelve demo scenarios as SIGNAL-LEVEL inputs (no audio required), so
it can be run from minute one and re-run after every threshold change. This is
the file that tells you instantly whether a calibration tweak has broken the
legitimate-IVR case.

Every scenario runs twice: through `audio_ml.fusion.fuse` (signal level) and through
the PRODUCTION path — server/audio_adapter into server/orchestrator._compute_fusion —
whose band is compared by overlay colour. Both share audio_ml/fusion_core.py, but only
the second proves what a user is shown. (Importing server/ from audio_ml/ is otherwise
off limits; this gate is the deliberate exception, it is an entry point no product code
imports, and the import is lazy.) Extra production checks follow the matrix: intent-only
scams reach high_risk, a replay is capped at caution, a flagged voice is high_risk, and a
clone stays red with any one branch degraded.

It also writes data/scenario_matrix.json, which feeds the
"12 scenarios tested" slide. That slide buys breadth credit without spending
demo clock.

Run:  python -m audio_ml.eval.test_scenarios
Exit code is non-zero if any scenario fails — wire it into your pre-freeze check.
"""

from __future__ import annotations
import json, os, sys
from types import SimpleNamespace as S

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from audio_ml.fusion import BAND_COLOUR, fuse  # noqa: E402


def sp(verdict, norm, raw=None, flagged=0):
    return S(verdict=verdict, norm_score=norm,
             raw_cosine=raw if raw is not None else norm,
             flagged_voice_hits=flagged, best_match_id=None,
             best_match_name=None, relationship=None)


def cm(score, peak=None, verdict="uncertain"):
    return S(score=score, peak=peak if peak is not None else score,
             verdict=verdict, max_synth_run_s=0.0, timeline=[], n_chunks=8)


def sc(risk):
    return S(risk=risk, top_matches=[], markers=[])


# --------------------------------------------------------------------------
# name, speaker, spoof, script, acceptable bands
# --------------------------------------------------------------------------
SCENARIOS = [
    ("1  genuine human, normal call",
     sp("match", 0.78), cm(0.06, 0.11, "bonafide"), sc(0.04),
     {"green"}),

    ("2  AI voice, legitimate IVR",
     sp("unknown", 0.10), cm(0.92, 0.95, "synthetic"), sc(0.05),
     {"unverified"}),

    ("3  human scammer, bank/KYC",
     sp("unknown", 0.09), cm(0.07, 0.12, "bonafide"), sc(0.88),
     {"red"}),

    ("4  AI clone, family emergency",
     sp("mismatch", 0.31), cm(0.94, 0.96, "synthetic"), sc(0.88),
     {"red"}),

    ("5  spoofed number, human voice",
     sp("unknown", 0.11), cm(0.08, 0.14, "bonafide"), sc(0.80),
     {"red"}),

    ("6  trusted number, cloned voice",
     sp("mismatch", 0.28), cm(0.90, 0.94, "synthetic"), sc(0.55),
     {"red"}),

    ("7  replay of family member",
     sp("match", 0.97, raw=0.985), cm(0.10, 0.18, "bonafide"), sc(0.30),
     {"amber", "red"}),

    ("8  human, digital arrest",
     sp("unknown", 0.08), cm(0.06, 0.10, "bonafide"), sc(0.95),
     {"red"}),

    ("9  Hinglish KYC/OTP scam",
     sp("unknown", 0.10), cm(0.09, 0.15, "bonafide"), sc(0.85),
     {"red"}),

    ("10 genuine family, odd money request",
     sp("match", 0.74), cm(0.07, 0.12, "bonafide"), sc(0.62),
     {"amber"}),

    ("11 escalation, final state",
     sp("unknown", 0.12), cm(0.10, 0.16, "bonafide"), sc(0.90),
     {"red"}),

    ("12 hybrid human + AI",
     sp("unknown", 0.12), cm(0.30, 0.93, "partial_synthetic"), sc(0.80),
     {"red"}),
]

# Scenario 11 as a time series — the meter must climb monotonically.
ESCALATION = [
    (" t=0:15 pleasantries", sc(0.05)),
    (" t=0:45 vague problem", sc(0.30)),
    (" t=1:10 threat appears", sc(0.62)),
    (" t=1:40 OTP demanded", sc(0.90)),
]


def production_band(speaker, spoof, script, degrade: str | None = None) -> str:
    """The band the live path returns for these signals, optionally with one branch
    degraded exactly as it degrades in production ("speaker", "spoof" or "text")."""
    from audio_ml.signals import SpeakerSignal, SpoofSignal
    from contracts import ScriptAnalysisResult, SpeakerVerificationResult
    from server.audio_adapter import to_speaker_result, to_spoof_result
    from server.orchestrator import _compute_fusion

    if degrade == "speaker":
        speaker_result = SpeakerVerificationResult.neutral()
    else:
        speaker_result = to_speaker_result(SpeakerSignal(
            verdict=speaker.verdict, raw_cosine=speaker.raw_cosine, norm_score=speaker.norm_score,
            flagged_voice_hits=speaker.flagged_voice_hits))
    spoof_result = to_spoof_result(SpoofSignal(
        score=spoof.score, peak=spoof.peak, verdict=spoof.verdict, n_chunks=0 if degrade == "spoof" else 8))
    script_result = ScriptAnalysisResult(risk=script.risk)
    if degrade == "text":
        script_result = ScriptAnalysisResult.neutral()
        script_result.details["available"] = False
    return _compute_fusion(speaker_result, spoof_result, script_result).band.value


def _claim_checks() -> list[tuple[str, bool, str]]:
    """Who the caller claims to be (server/claims.py), through resolution and fusion."""
    from contracts import AntiSpoofResult, ScriptAnalysisResult, SpeakerVerificationResult
    from server.claims import Claim, PersonRef, resolve
    from server.orchestrator import _compute_fusion

    papa = PersonRef("p_papa", "Papa", "Father", (), ("+919800000001",), True)

    def band(cos, claim, spoof_risk, text_risk):
        speaker = resolve(SpeakerVerificationResult(details={"scores": {"p_papa": cos}}), [claim], [papa])
        spoof = AntiSpoofResult(risk=spoof_risk, median_score=spoof_risk, peak_score=spoof_risk,
                                details={"available": True})
        return _compute_fusion(speaker, spoof, ScriptAnalysisResult(risk=text_risk)).band.value

    clone = band(0.7619, Claim("transcript", frozenset({"p_papa"}), "Papa"), 0.94, 0.88)
    spoofed = band(0.30, Claim("caller_id", frozenset({"p_papa"}), "+919800000001"), 0.05, 0.05)
    grey = band(0.7912, Claim("user", frozenset({"p_papa"}), "p_papa"), 0.07, 0.10)
    return [("a claimed-Papa clone with a scam script is high_risk", clone == "high_risk", clone),
            ("a spoofed number on a benign call is not red", BAND_COLOUR[spoofed] != "red", spoofed),
            ("a genuine grey-zone caller is not red", BAND_COLOUR[grey] != "red", grey)]


def production_checks() -> list[tuple[str, bool, str]]:
    """(name, passed, observed) for the checks the 12-scenario matrix cannot express."""
    by_num = {name.split()[0]: (sp_, cm_, sc_) for name, sp_, cm_, sc_, _ in SCENARIOS}
    checks = []
    for num, label in (("3", "human scammer, bank/KYC"), ("8", "human, digital arrest")):
        band = production_band(*by_num[num])
        checks.append((f"intent alone reaches high_risk ({label})", band == "high_risk", band))
    band = production_band(*by_num["7"])
    checks.append(("a replay with mild intent is capped at caution", band == "caution", band))
    band = production_band(sp("unknown", 0.10, flagged=1), cm(0.05, 0.08, "bonafide"), sc(0.05))
    checks.append(("a flagged voice with benign words is high_risk", band == "high_risk", band))
    checks += _claim_checks()
    for branch in ("speaker", "spoof", "text"):
        band = production_band(*by_num["4"], degrade=branch)
        checks.append((f"clone stays red with {branch} degraded", BAND_COLOUR[band] == "red", band))
        band = production_band(*by_num["2"], degrade=branch)
        checks.append((f"legit IVR never verified with {branch} degraded", band != "verified", band))
    return checks


def run(write: bool = True) -> int:
    """Run the matrix on both paths. Returns the number of failures."""
    rows, failures = [], 0
    print(f"{'scenario':<40} {'trust':>5}  {'band':<11} {'production':<22} result")
    print("-" * 100)

    for name, speaker, spoof, script, ok_bands in SCENARIOS:
        r = fuse(speaker, spoof, script)
        d = r if isinstance(r, dict) else r.model_dump()
        prod = production_band(speaker, spoof, script)
        prod_colour = BAND_COLOUR[prod]
        passed = d["band"] in ok_bands and prod_colour in ok_bands
        failures += 0 if passed else 1
        print(f"{name:<40} {d['trust_score']:>5}  {d['band']:<11} {prod + ' (' + prod_colour + ')':<22} "
              f"{'PASS' if passed else 'FAIL -> ' + str(sorted(ok_bands))}")
        rows.append({"scenario": name.strip(), "trust": d["trust_score"],
                     "band": d["band"], "mode": d["mode"], "production_band": prod,
                     "expected": sorted(ok_bands), "pass": passed,
                     "breakdown": d["risk_breakdown"]})

    print("\nScenario 11 — escalation over time (must climb monotonically)")
    print("-" * 100)
    prev, esc = 101, []
    for label, script in ESCALATION:
        r = fuse(sp("unknown", 0.12), cm(0.10, 0.16, "bonafide"), script)
        d = r if isinstance(r, dict) else r.model_dump()
        mono = d["trust_score"] <= prev
        failures += 0 if mono else 1
        print(f"{label:<40} {d['trust_score']:>5}  {d['band']:<11} "
              f"{'':<22} {'ok' if mono else 'NOT MONOTONIC'}")
        esc.append({"label": label.strip(), "trust": d["trust_score"],
                    "band": d["band"]})
        prev = d["trust_score"]

    print("\nProduction path checks")
    print("-" * 100)
    checks = []
    for check, passed, observed in production_checks():
        failures += 0 if passed else 1
        print(f"{check:<62} {observed:<12} {'PASS' if passed else 'FAIL'}")
        checks.append({"check": check, "observed": observed, "pass": passed})

    if write:
        os.makedirs("data", exist_ok=True)
        with open("data/scenario_matrix.json", "w") as f:
            json.dump({"scenarios": rows, "escalation": esc, "production_checks": checks,
                       "failures": failures}, f, indent=2)

    print("\n" + ("ALL SCENARIOS PASS" if failures == 0
                  else f"{failures} FAILURE(S) — do not freeze until this is 0"))
    if write:
        print("wrote data/scenario_matrix.json")
    return failures


def main() -> int:
    import logging

    logging.disable(logging.WARNING)   # fusion logs every degraded branch; the table says it
    return 1 if run(write=True) else 0


if __name__ == "__main__":
    raise SystemExit(main())
