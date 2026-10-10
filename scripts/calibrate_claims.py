"""Calibrate the claim-check thresholds (upgrade plan, Phase 2).

A claim ("this is Papa") is checked 1:1 against the claimed person's voiceprint, through
the production path (`verify_speaker(..., claimed_person_id=...)`). Three outcomes need
two thresholds per channel:

    cosine >= MATCH          match         (no clone or stranger may reach it)
    LOW <= cosine < MATCH    inconclusive  (no accusation; ask the challenge question)
    cosine < LOW             mismatch      (only for a user pick or a spoken claim;
                                            no genuine caller may fall here)

Pairs measured, on every channel (clean wideband, G.711 mu-law, AMR-NB 12.2k):
  genuine   friend_test -> Friend, me_test2 -> Me
  clone     friend_clone, cloned_scam -> Friend
  stranger  every held-* scam recording -> Friend and -> Me

Writes data/measurements/claim_calibration.json and prints the thresholds it would set.
Speakerphone (room acoustics) is not simulated here; re-measure with real calls.

Usage:  python -m scripts.calibrate_claims
"""

from __future__ import annotations

import json
import logging
import sys
import tempfile
from pathlib import Path

import config

CLIPS = config.REPO_ROOT / "data" / "eval_set" / "clips"
OUT = config.REPO_ROOT / "data" / "measurements" / "claim_calibration.json"
CONDITIONS = {"wideband": [None], "narrowband": ["g711_ulaw", "amr_nb"]}
MARGIN = 0.02


def _pairs() -> list[tuple[str, str, str]]:
    """(probe clip, claimed person, kind)."""
    pairs = [("friend_test", "friend", "genuine"), ("me_test2", "me", "genuine"),
             ("friend_clone", "friend", "clone"), ("cloned_scam", "friend", "clone")]
    strangers = sorted(p.stem for p in CLIPS.glob("held-*.wav") if not p.stem.endswith("_nb8k"))
    pairs += [(s, who, "stranger") for s in strangers for who in ("friend", "me")]
    return pairs


def measure() -> list[dict]:
    from audio_ml.api import compute_voiceprint, verify_speaker
    from audio_ml.augment import apply_codec

    people = {}
    for who, clip in (("friend", "friend"), ("me", "me")):
        vp = compute_voiceprint([str(CLIPS / f"{clip}.wav")])
        if not vp:
            sys.exit(f"could not enroll {who} from {clip}.wav")
        people[who] = {"person_id": who, "name": who.title(), "relationship": "test",
                       "centroids": {k: v for k, v in vp.items() if k != "n_samples"}}
    rows = []
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
                    sig = verify_speaker(str(path), candidates=list(people.values()), claimed_person_id=claimed)
                    # No best match means the probe could not be embedded (e.g. no speech
                    # chunks found): a failure, not a similarity of 0. Recorded, not used.
                    scored = sig.best_match_id is not None
                    rows.append({"probe": probe, "claimed": claimed, "kind": kind, "channel": channel,
                                 "codec": codec or "clean", "cosine": round(sig.raw_cosine, 4),
                                 "scored": scored, "condition_used": sig.condition_used})
                    print(f"  {channel:<10} {codec or 'clean':<10} {kind:<8} {probe:<28} -> {claimed:<6} "
                          f"{sig.raw_cosine:.4f}")
    return rows


def thresholds(rows: list[dict]) -> dict:
    out = {}
    for channel in CONDITIONS:
        usable = [r for r in rows if r["channel"] == channel and r.get("scored", True)]
        genuine = [r["cosine"] for r in usable if r["kind"] == "genuine"]
        attack = [r["cosine"] for r in usable if r["kind"] != "genuine"]
        match = round(max(attack) + MARGIN, 3)          # nothing hostile verifies
        low = round(min(genuine) - MARGIN, 3)           # nobody genuine is accused
        low = min(low, match)
        out[channel] = {"match": match, "low": low, "genuine_min": min(genuine), "genuine_max": max(genuine),
                        "attack_max": max(attack), "attack_min": min(attack),
                        "attacks_below_low": sum(a < low for a in attack), "attacks": len(attack),
                        "genuine_in_grey_zone": sum(low <= g < match for g in genuine), "genuine": len(genuine),
                        "unscored": sum(1 for r in rows if r["channel"] == channel and not r.get("scored", True))}
    return out


def main() -> int:
    logging.disable(logging.WARNING)
    rows = measure()
    result = {"pairs": rows, "thresholds": thresholds(rows), "margin": MARGIN,
              "note": "2 enrolled speakers, 2 genuine probes, 2 clones, held-* strangers; "
                      "speakerphone not simulated. Small set: re-measure with real calls."}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["thresholds"], indent=2))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
