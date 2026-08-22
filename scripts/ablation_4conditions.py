"""
scripts/ablation_4conditions.py — Four-condition ablation measuring the gap between
simulated and genuine narrowband audio when condition-matched.

Tests: genuine narrowband probe (friend_test_nb8k_probe.wav, already phone-degraded)
Enrollment: Friend with 3 centroids (wb, nb8k_sim from ffmpeg, nb8k_real from phone)

Conditions:
  1. wideband: genuine narrowband probe vs wb centroid (naive mismatch - baseline)
  2. simulated_matched: genuine narrowband probe vs nb8k_sim (ffmpeg-degraded)
  3. genuine_matched: genuine narrowband probe vs nb8k_real (real phone-degraded)

Expected: wideband > genuine_matched > simulated_matched (in separation)
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from audio_ml.verify import verify_speaker
from audio_ml import embed, enroll
import logging
import numpy as np

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def main():
    print("\n" + "=" * 110)
    print("THREE-CONDITION ABLATION: Genuine Narrowband Probe vs Different Centroids")
    print("=" * 110)

    genuine_probe = "data/demo_clips/friend_test_nb8k_probe.wav"
    impostor_files = [
        "data/eval_set/raw/person1.wav",
        "data/eval_set/raw/person2.wav",
        "data/eval_set/raw/person3.wav",
    ]

    # Load friend's voiceprint with 3 centroids
    voiceprint = enroll.load_voiceprint("friend")
    if not voiceprint:
        logger.error("Friend voiceprint not found")
        return

    # Load genuine probe (narrowband, phone-degraded)
    logger.info(f"Loading genuine probe: {genuine_probe}")
    audio, sr = embed.load_audio(genuine_probe)
    if len(audio) == 0:
        logger.error(f"Failed to load {genuine_probe}")
        return

    condition = embed.detect_condition(audio, sr)
    segments = embed.vad_segments(audio, sr)
    embeddings = embed.embed_chunks(audio, sr, segments)
    probe_emb = np.mean(embeddings, axis=0).astype(np.float32)
    probe_norm = np.linalg.norm(probe_emb)
    if probe_norm > 0:
        probe_emb = probe_emb / probe_norm

    logger.info(f"  Detected condition: {condition}")
    logger.info(f"  Chunks extracted: {len(embeddings)}")
    logger.info(f"  Duration: {len(audio)/sr:.2f}s at {sr}Hz")

    # Genuine scores: compare genuine probe against each centroid
    genuine_scores = {}
    centroid_info = {
        "wideband": ("wb centroid (wideband baseline)", voiceprint["wb"]),
        "simulated_matched": ("nb8k_sim centroid (ffmpeg-degraded)", voiceprint["nb8k_sim"]),
        "genuine_matched": ("nb8k_real centroid (genuine phone-degraded)", voiceprint.get("nb8k_real")),
    }

    print("\n" + "=" * 110)
    print("GENUINE PROBE SCORES")
    print("=" * 110)
    print(f"Probe file: {genuine_probe} (detected as {condition})")
    print(f"{'Condition':<25} {'Centroid':<40} {'Score':<12}")
    print("-" * 110)

    for cond_name, (centroid_desc, centroid) in centroid_info.items():
        if centroid is None:
            genuine_scores[cond_name] = 0.0
            print(f"{cond_name:<25} {centroid_desc:<40} {'N/A (missing)':<12}")
        else:
            score = float(np.dot(probe_emb, centroid))
            genuine_scores[cond_name] = score
            print(f"{cond_name:<25} {centroid_desc:<40} {score:<12.4f}")

    # Impostor scores
    impostor_scores = {}
    for cond_name in centroid_info.keys():
        impostor_scores[cond_name] = []

    print("\n" + "=" * 110)
    print("IMPOSTOR SCORES")
    print("=" * 110)

    for impostor_file in impostor_files:
        logger.info(f"Loading impostor: {Path(impostor_file).name}")
        audio, sr = embed.load_audio(impostor_file)
        if len(audio) == 0:
            logger.warning(f"Failed to load {impostor_file}")
            continue

        condition_imp = embed.detect_condition(audio, sr)
        segments = embed.vad_segments(audio, sr)
        embeddings = embed.embed_chunks(audio, sr, segments)
        impostor_emb = np.mean(embeddings, axis=0).astype(np.float32)
        impostor_norm = np.linalg.norm(impostor_emb)
        if impostor_norm > 0:
            impostor_emb = impostor_emb / impostor_norm

        print(f"\n{Path(impostor_file).name} (detected as {condition_imp}):")
        for cond_name, (centroid_desc, centroid) in centroid_info.items():
            if centroid is None:
                impostor_scores[cond_name].append(0.0)
                print(f"  {cond_name:<23} vs {centroid_desc:<38} = N/A")
            else:
                score = float(np.dot(impostor_emb, centroid))
                impostor_scores[cond_name].append(score)
                print(f"  {cond_name:<23} vs {centroid_desc:<38} = {score:.4f}")

    # Compute stats
    print("\n" + "=" * 110)
    print("SUMMARY: SEPARATION METRICS")
    print("=" * 110)
    print(f"{'Condition':<25} {'Genuine':<12} {'Impostor Avg':<15} {'Separation':<12}")
    print("-" * 110)

    results = {}
    for cond in centroid_info.keys():
        genuine = genuine_scores[cond]
        impostors = impostor_scores[cond]
        impostor_mean = np.mean(impostors) if impostors else 0.0
        separation = genuine - impostor_mean

        results[cond] = {
            "genuine_score": float(genuine),
            "impostor_mean": float(impostor_mean),
            "impostor_scores": [float(s) for s in impostors],
            "separation": float(separation),
        }

        print(f"{cond:<25} {genuine:<12.4f} {impostor_mean:<15.4f} {separation:<12.4f}")

    # Save results
    output_path = Path("data/ablation_4conditions.json")
    with open(output_path, "w") as f:
        json.dump({
            "genuine_probe": genuine_probe,
            "impostor_files": impostor_files,
            "conditions": results,
        }, f, indent=2)

    print(f"\nResults saved to {output_path}")

    # Key finding
    print("\n" + "=" * 110)
    print("KEY FINDING")
    print("=" * 110)

    wb_sep = results["wideband"]["separation"]
    sim_sep = results["simulated_matched"]["separation"]
    gen_sep = results["genuine_matched"]["separation"]

    print(f"Wideband baseline (mismatch):     separation = {wb_sep:.4f}")
    print(f"Simulated (ffmpeg-matched):       separation = {sim_sep:.4f}")
    print(f"Genuine (phone-matched):          separation = {gen_sep:.4f}")

    if gen_sep > sim_sep:
        gap = gen_sep - sim_sep
        pct = (gap / sim_sep * 100) if sim_sep != 0 else 0
        print(f"\nGap (genuine - simulated): {gap:+.4f} ({pct:+.1f}%)")
        print(f"RESULT: Genuine narrowband is {pct:.1f}% BETTER than simulated degradation")
    elif gen_sep < sim_sep:
        gap = sim_sep - gen_sep
        pct = (gap / sim_sep * 100) if sim_sep != 0 else 0
        print(f"\nGap (simulated - genuine): {gap:+.4f} ({pct:+.1f}%)")
        print(f"RESULT: Genuine narrowband is {pct:.1f}% WORSE than simulated degradation")
        print("WARNING: This indicates condition-matched enrollment with genuine audio")
        print("         is NOT improving separation compared to simulated degradation.")
    else:
        print(f"\nNo difference between simulated and genuine")

if __name__ == "__main__":
    main()
