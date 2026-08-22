"""
scripts/ablation_4conditions.py — Four-condition ablation: WB, naive NB8K, simulated-matched, genuine-matched.

Measures the gap between computationally-simulated codec degradation (ffmpeg)
and genuine phone-quality narrowband audio.

Probe: held-out narrowband test portion (friend_test_nb8k_probe.wav)
Genuine source: narrowband enrollment portion (friend_test_nb8k_enroll.wav)
Impostors: person1.wav, person2.wav, person3.wav
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from audio_ml.verify import verify_speaker
from audio_ml import embed, enroll, codec
import logging
import numpy as np

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def main():
    print("\n" + "=" * 100)
    print("FOUR-CONDITION ABLATION: Simulated vs Genuine Narrowband")
    print("=" * 100)

    genuine_file = "data/demo_clips/friend_test_nb8k_probe.wav"
    impostor_files = [
        "data/eval_set/raw/person1.wav",
        "data/eval_set/raw/person2.wav",
        "data/eval_set/raw/person3.wav",
    ]

    # Load genuine speaker's voiceprint
    voiceprint = enroll.load_voiceprint("friend")
    if not voiceprint:
        logger.error("Friend voiceprint not found")
        return

    # Load genuine probe embedding
    audio, sr = embed.load_audio(genuine_file)
    if len(audio) == 0:
        logger.error(f"Failed to load {genuine_file}")
        return

    segments = embed.vad_segments(audio, sr)
    embeddings = embed.embed_chunks(audio, sr, segments)
    probe_emb = np.mean(embeddings, axis=0).astype(np.float32)
    probe_norm = np.linalg.norm(probe_emb)
    if probe_norm > 0:
        probe_emb = probe_emb / probe_norm

    logger.info(f"Genuine probe: {len(embeddings)} chunks from {genuine_file}")

    # Load impostor embeddings and score them
    impostor_scores_all = {}
    for cond_name in ["wideband", "naive_nb8k", "simulated_matched", "genuine_matched"]:
        impostor_scores_all[cond_name] = []

    for impostor_file in impostor_files:
        audio, sr = embed.load_audio(impostor_file)
        if len(audio) == 0:
            logger.warning(f"Failed to load {impostor_file}")
            continue

        segments = embed.vad_segments(audio, sr)
        embeddings = embed.embed_chunks(audio, sr, segments)
        impostor_emb = np.mean(embeddings, axis=0).astype(np.float32)
        impostor_norm = np.linalg.norm(impostor_emb)
        if impostor_norm > 0:
            impostor_emb = impostor_emb / impostor_norm

        logger.info(f"  Impostor {Path(impostor_file).name}: {len(embeddings)} chunks")

        # Score impostor against each centroid
        impostor_scores_all["wideband"].append(float(np.dot(impostor_emb, voiceprint["wb"])))
        impostor_scores_all["naive_nb8k"].append(float(np.dot(impostor_emb, voiceprint["wb"])))  # impostor vs wb centroid
        impostor_scores_all["simulated_matched"].append(float(np.dot(impostor_emb, voiceprint["nb8k_sim"])))
        impostor_scores_all["genuine_matched"].append(float(np.dot(impostor_emb, voiceprint["nb8k_real"])) if (voiceprint.get("nb8k_real") is not None) else 0.0)

    # Compute genuine scores
    genuine_scores = {
        "wideband": float(np.dot(probe_emb, voiceprint["wb"])),
        "naive_nb8k": float(np.dot(probe_emb, voiceprint["wb"])),  # nb8k probe vs wb centroid
        "simulated_matched": float(np.dot(probe_emb, voiceprint["nb8k_sim"])),
        "genuine_matched": float(np.dot(probe_emb, voiceprint["nb8k_real"])) if (voiceprint.get("nb8k_real") is not None) else 0.0,
    }

    # Compute stats
    print("\n" + "=" * 100)
    print("RESULTS")
    print("=" * 100)
    print(f"{'Condition':<30} {'Genuine':<12} {'Impostor Avg':<15} {'Separation':<12}")
    print("-" * 100)

    results = {}
    for cond in ["wideband", "naive_nb8k", "simulated_matched", "genuine_matched"]:
        genuine = genuine_scores[cond]
        impostors = impostor_scores_all[cond]
        impostor_mean = np.mean(impostors) if impostors else 0.0
        separation = genuine - impostor_mean

        results[cond] = {
            "genuine_score": float(genuine),
            "impostor_mean": float(impostor_mean),
            "impostor_scores": [float(s) for s in impostors],
            "separation": float(separation),
        }

        print(f"{cond:<30} {genuine:<12.4f} {impostor_mean:<15.4f} {separation:<12.4f}")

    # Save results
    output_path = Path("data/ablation_4conditions.json")
    with open(output_path, "w") as f:
        json.dump({
            "genuine_file": genuine_file,
            "impostor_files": impostor_files,
            "conditions": results,
        }, f, indent=2)

    print(f"\nResults saved to {output_path}")

    # Key finding
    print("\n" + "=" * 100)
    print("KEY FINDING")
    print("=" * 100)
    if "simulated_matched" in results and "genuine_matched" in results:
        sim_sep = results["simulated_matched"]["separation"]
        gen_sep = results["genuine_matched"]["separation"]
        gap = gen_sep - sim_sep
        pct_improvement = (gap / sim_sep * 100) if sim_sep != 0 else 0
        print(f"Simulated codec (ffmpeg):     separation = {sim_sep:.4f}")
        print(f"Genuine narrowband (phone):  separation = {gen_sep:.4f}")
        print(f"Gap (genuine - simulated):   {gap:+.4f} ({pct_improvement:+.1f}%)")
        print("\nInterpretation:")
        if gap > 0:
            print(f"  Genuine phone audio matches {pct_improvement:.1f}% BETTER than simulated degradation.")
        else:
            print(f"  Genuine phone audio matches {abs(pct_improvement):.1f}% WORSE than simulated degradation.")
        print("  This quantifies the difference between real telephony and computational simulation.")

if __name__ == "__main__":
    main()
