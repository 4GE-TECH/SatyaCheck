"""Does moving the models to the GPU change any verdict? (GPU plan, Phase 0.)

Run once on CPU to freeze a baseline, then on CUDA to compare against it:

    python -m scripts.device_parity --device cpu  --baseline   # before installing CUDA torch
    python -m scripts.device_parity --device cuda              # after; exits 1 on any breach
    python -m scripts.device_parity --device cpu  --baseline   # again after a scoring change

The baseline freezes the enrollment centroids too (computed on CPU, as every stored voiceprint
was). The CUDA run reuses them, so it measures what production will do: GPU probes against
CPU-made voiceprints. Nothing here rewrites claim_calibration.json.

Per probe, the CUDA run must stay within:
    identity      |Δ cosine| <= 0.005 and no claim-outcome flip (match / inconclusive / low)
    authenticity  |Δ median|, |Δ peak| <= 0.01 and the same verdict
    intent        same retrieval top-3, |Δ risk| <= 0.02, same markers   (fixed texts)
    ASR           same markers and the same intent band (either side of CORROBORATION_FLOOR and
                  SCRIPT_HIGH_RISK) on transcribed held-out clips. The two devices decode
                  different text (int8 CPU vs float16 GPU), so a fixed risk delta would gate
                  ASR noise rather than verdicts; the text and the delta are reported.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "measurements"
CENTROIDS = OUT_DIR / "device_parity_centroids.npz"
LIMITS = {"cosine": 0.005, "spoof": 0.01, "risk_text": 0.02}


def _intent_band(risk: float) -> str:
    from nlp_rag import thresholds

    return ("high" if risk >= thresholds.SCRIPT_HIGH_RISK
            else "suspicious" if risk >= thresholds.CORROBORATION_FLOOR else "low")

# Fixed intent texts: Hindi, English and Hinglish, scam and benign, so retrieval and markers
# are compared on identical input (transcription is compared separately).
TEXTS = [
    "This is CBI calling, you are under digital arrest, do not tell anyone and stay on the line",
    "Beta main police station mein hoon, jaldi se UPI pe paise bhejo, Papa ko mat batana",
    "Your KYC is expiring today, share the OTP you just received to keep your account active",
    "Hi, it's your delivery driver, I'm outside the gate, can you come down?",
    "Mummy main theek hoon, accident chhota tha, doctor se baat kar lo, Papa ko call karo",
    "आपका बिजली कनेक्शन आज रात काट दिया जाएगा, तुरंत इस नंबर पर भुगतान करें",
    "Sir, your parcel contains illegal drugs, the customs officer will connect you now",
    "Hello, this is the bank, we noticed a login from a new device, was this you?",
]


def _env(device: str) -> None:
    os.environ["SATYACHECK_DEVICE"] = device
    os.environ["WHISPER_DEVICE"] = device


def _side(cosine: float, channel: str, thresholds: dict) -> str:
    t = thresholds[channel]
    return "match" if cosine >= t["match"] else "inconclusive" if cosine >= t["low"] else "low"


def measure(device: str, freeze: bool) -> dict:
    import numpy as np

    import config
    from audio_ml.api import compute_voiceprint, detect_spoof, verify_speaker
    from audio_ml.augment import apply_codec
    from nlp_rag.api import analyze_script, configure
    from nlp_rag.asr import transcribe_file
    from contracts import TranscriptResult
    from scripts.calibrate_claims import CLIPS, CONDITIONS, _pairs

    report: dict = {"device": device, "identity": [], "authenticity": [], "intent": [], "asr": []}

    if freeze:
        people = {}
        for who in ("friend", "me"):
            vp = compute_voiceprint([str(CLIPS / f"{who}.wav")])
            if not vp:
                sys.exit(f"could not enroll {who}")
            people[who] = {k: np.asarray(v, dtype=np.float32) for k, v in vp.items() if k != "n_samples"}
        np.savez(CENTROIDS, **{f"{who}__{cond}": v for who, conds in people.items() for cond, v in conds.items()})
    if not CENTROIDS.is_file():
        sys.exit(f"no frozen centroids at {CENTROIDS}; run --device cpu --baseline first")
    frozen = np.load(CENTROIDS)
    people = {}
    for key in frozen.files:
        who, cond = key.split("__", 1)
        people.setdefault(who, {})[cond] = frozen[key]
    candidates = [{"person_id": who, "name": who.title(), "relationship": "test", "centroids": c}
                  for who, c in people.items()]

    with tempfile.TemporaryDirectory() as tmp:
        for channel, codecs in CONDITIONS.items():
            for codec in codecs:
                for probe, claimed, kind in _pairs():
                    path = CLIPS / f"{probe}.wav"
                    if codec:
                        coded = Path(tmp) / f"{probe}_{codec}.wav"
                        if not coded.exists():
                            apply_codec(path, coded, codec)
                        path = coded
                    sig = verify_speaker(str(path), candidates=candidates, claimed_person_id=claimed)
                    report["identity"].append({
                        "key": f"{channel}/{codec or 'clean'}/{probe}->{claimed}", "kind": kind,
                        "scored": sig.best_match_id is not None, "cosine": round(float(sig.raw_cosine), 5),
                        "side": _side(float(sig.raw_cosine), channel, config.CLAIM_THRESHOLDS)})

    for clip in sorted((ROOT / "data" / "eval_set" / "clips").glob("*.wav")):
        s = detect_spoof(str(clip))
        report["authenticity"].append({"key": clip.stem, "median": round(float(s.score), 5),
                                       "peak": round(float(s.peak), 5), "verdict": s.verdict,
                                       "n_chunks": s.n_chunks})

    configure()
    for i, text in enumerate(TEXTS):
        r = analyze_script(TranscriptResult(text=text))
        report["intent"].append({
            "key": f"text{i}", "risk": round(float(r.risk), 5),
            "top3": [p.playbook_id for p in r.playbooks[:3]],
            "markers": sorted(m.marker_id for m in r.incriminating_markers + r.exculpatory_markers)})

    for clip in sorted(CLIPS.glob("held-*.wav")):
        t = transcribe_file(str(clip))
        r = analyze_script(t)
        report["asr"].append({
            "key": clip.stem, "text": t.text, "risk": round(float(r.risk), 5),
            "markers": sorted(m.marker_id for m in r.incriminating_markers + r.exculpatory_markers)})
    return report


def compare(base: dict, new: dict) -> list[str]:
    """Every breach of the limits, as readable lines. Empty means parity."""
    breaches = []

    def by_key(rows):
        return {r["key"]: r for r in rows}

    for section in ("identity", "authenticity", "intent", "asr"):
        old, cur = by_key(base[section]), by_key(new[section])
        if old.keys() != cur.keys():
            breaches.append(f"{section}: probe sets differ ({sorted(old.keys() ^ cur.keys())[:5]})")
        for key in old.keys() & cur.keys():
            a, b = old[key], cur[key]
            if section == "identity":
                if a["scored"] != b["scored"]:
                    breaches.append(f"identity {key}: scored {a['scored']} -> {b['scored']}")
                elif a["scored"]:
                    if abs(a["cosine"] - b["cosine"]) > LIMITS["cosine"]:
                        breaches.append(f"identity {key}: cosine {a['cosine']} -> {b['cosine']}")
                    if a["side"] != b["side"]:
                        breaches.append(f"identity {key}: outcome {a['side']} -> {b['side']}")
            elif section == "authenticity":
                for f in ("median", "peak"):
                    if abs(a[f] - b[f]) > LIMITS["spoof"]:
                        breaches.append(f"authenticity {key}: {f} {a[f]} -> {b[f]}")
                if a["verdict"] != b["verdict"]:
                    breaches.append(f"authenticity {key}: verdict {a['verdict']} -> {b['verdict']}")
            else:
                if section == "intent" and abs(a["risk"] - b["risk"]) > LIMITS["risk_text"]:
                    breaches.append(f"intent {key}: risk {a['risk']} -> {b['risk']}")
                if section == "asr" and _intent_band(a["risk"]) != _intent_band(b["risk"]):
                    breaches.append(f"asr {key}: intent band {_intent_band(a['risk'])} ({a['risk']}) -> "
                                    f"{_intent_band(b['risk'])} ({b['risk']})")
                if a["markers"] != b["markers"]:
                    breaches.append(f"{section} {key}: markers {a['markers']} -> {b['markers']}")
                if section == "intent" and a["top3"] != b["top3"]:
                    breaches.append(f"intent {key}: top3 {a['top3']} -> {b['top3']}")
    return breaches


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--device", choices=["cpu", "cuda"], required=True)
    ap.add_argument("--baseline", action="store_true", help="write the CPU baseline (freezes centroids once)")
    ap.add_argument("--refreeze", action="store_true",
                    help="recompute the frozen centroids too (only when the stored voiceprints change)")
    args = ap.parse_args()
    if args.baseline and args.device != "cpu":
        sys.exit("the baseline is CPU by definition")
    _env(args.device)
    sys.path.insert(0, str(ROOT))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Re-baselining after a scoring change keeps the original CPU centroids: the question is
    # still "GPU probes against CPU-made voiceprints".
    report = measure(args.device, freeze=args.baseline and (args.refreeze or not CENTROIDS.is_file()))
    out = OUT_DIR / f"device_parity_{args.device}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out} ({sum(len(v) for v in report.values() if isinstance(v, list))} measurements)")
    if args.baseline:
        return 0

    base = json.loads((OUT_DIR / "device_parity_cpu.json").read_text(encoding="utf-8"))
    breaches = compare(base, report)
    for row_old, row_new in zip(base["asr"], report["asr"]):
        if abs(row_old["risk"] - row_new["risk"]) > 0.02:
            print(f"  asr risk moved (reported; gated on band) {row_new['key']}: {row_old['risk']} -> {row_new['risk']}")
        if row_old["text"] != row_new["text"]:
            print(f"  asr text differs (reported, not gated) {row_new['key']}:\n    cpu:  {row_old['text']}\n"
                  f"    cuda: {row_new['text']}")
    if breaches:
        print(f"PARITY FAILED: {len(breaches)} breach(es)")
        for line in breaches:
            print("  " + line)
        return 1
    print("PARITY OK: no verdict-relevant difference between CPU and CUDA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
