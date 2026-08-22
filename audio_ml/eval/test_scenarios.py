"""
audio_ml/eval/test_scenarios.py — the 12-scenario regression matrix

Runs all twelve demo scenarios as SIGNAL-LEVEL inputs (no audio required), so
it can be run from minute one and re-run after every threshold change. This is
the file that tells you instantly whether a calibration tweak has broken the
legitimate-IVR case.

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

from audio_ml.fusion import fuse  # noqa: E402


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


def main() -> int:
    rows, failures = [], 0
    print(f"{'scenario':<40} {'trust':>5}  {'band':<11} {'mode':<16} result")
    print("-" * 92)

    for name, speaker, spoof, script, ok_bands in SCENARIOS:
        r = fuse(speaker, spoof, script)
        d = r if isinstance(r, dict) else r.model_dump()
        passed = d["band"] in ok_bands
        failures += 0 if passed else 1
        print(f"{name:<40} {d['trust_score']:>5}  {d['band']:<11} "
              f"{d['mode']:<16} {'PASS' if passed else 'FAIL -> ' + str(sorted(ok_bands))}")
        rows.append({"scenario": name.strip(), "trust": d["trust_score"],
                     "band": d["band"], "mode": d["mode"],
                     "expected": sorted(ok_bands), "pass": passed,
                     "breakdown": d["risk_breakdown"]})

    print("\nScenario 11 — escalation over time (must climb monotonically)")
    print("-" * 92)
    prev, esc = 101, []
    for label, script in ESCALATION:
        r = fuse(sp("unknown", 0.12), cm(0.10, 0.16, "bonafide"), script)
        d = r if isinstance(r, dict) else r.model_dump()
        mono = d["trust_score"] <= prev
        failures += 0 if mono else 1
        print(f"{label:<40} {d['trust_score']:>5}  {d['band']:<11} "
              f"{'':<16} {'ok' if mono else 'NOT MONOTONIC'}")
        esc.append({"label": label.strip(), "trust": d["trust_score"],
                    "band": d["band"]})
        prev = d["trust_score"]

    os.makedirs("data", exist_ok=True)
    with open("data/scenario_matrix.json", "w") as f:
        json.dump({"scenarios": rows, "escalation": esc,
                   "failures": failures}, f, indent=2)

    print("\n" + ("ALL SCENARIOS PASS" if failures == 0
                  else f"{failures} FAILURE(S) — do not freeze until this is 0"))
    print("wrote data/scenario_matrix.json")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
