"""
scripts/ablation_8khz.py — Condition-matched enrollment ablation experiment.

Demonstrates that condition-matched enrollment (separate centroids for wideband
and 8kHz) recovers performance on narrowband-degraded audio.

For each test file:
  1. Verify wideband (baseline)
  2. Verify nb8k degraded against wideband centroid (naive, should degrade)
  3. Verify nb8k degraded against nb8k centroid (condition-matched, should recover)

Saves results to data/ablation_results.json.
"""

import os
import json
import logging
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio_ml import embed, codec
from audio_ml.enroll import load_voiceprint
from contracts import SpeakerSignal

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

TEST_FILES = [
    "data/demo_clips/friend.wav",
    "data/demo_clips/cloned_scam.wav",
    "data/demo_clips/me_test2.wav",
    "data/eval_set/raw/person1.wav",
    "data/eval_set/raw/person2.wav",
    "data/eval_set/raw/person3.wav",
]

# Enrolled speakers: alice and friend
ENROLLED = {
    "alice": "alice",
    "friend": "friend",
}

TEMP_DIR = Path("data/ablation_tmp")


def cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """Compute cosine similarity between two L2-normalized vectors."""
    return float(np.dot(emb1, emb2))


def compute_score_against_centroid(
    probe_emb: np.ndarray,
    centroid: np.ndarray
) -> float:
    """Compute cosine similarity between probe and centroid."""
    return cosine_similarity(probe_emb, centroid)


def get_best_match_score(probe_emb: np.ndarray, condition: str = "wb") -> float:
    """Get best match score against enrolled speakers for given condition."""
    best_score = -1.0
    for person_id in ENROLLED.values():
        voiceprint = load_voiceprint(person_id)
        if not voiceprint:
            continue

        # Select centroid based on condition
        if condition == "nb8k" and voiceprint.get("nb8k") is not None:
            centroid = voiceprint["nb8k"]
        else:
            centroid = voiceprint["wb"]

        score = compute_score_against_centroid(probe_emb, centroid)
        best_score = max(best_score, score)

    return best_score if best_score >= 0 else 0.0


def run_ablation():
    """Run ablation experiment."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    results = {}

    print("\n" + "=" * 120)
    print("8kHz Ablation Experiment: Condition-Matched Enrollment")
    print("=" * 120)
    print()

    for test_file in TEST_FILES:
        if not Path(test_file).exists():
            logger.warning(f"Test file not found: {test_file}")
            continue

        fname = Path(test_file).name
        logger.info(f"Processing {fname}...")

        # Step 1: Get wideband baseline
        audio_wb, sr = embed.load_audio(test_file)
        if len(audio_wb) == 0:
            logger.warning(f"  Could not load audio")
            continue

        embeddings_wb = embed.embed_chunks(audio_wb, sr, [])
        if not embeddings_wb:
            logger.warning(f"  Could not extract embeddings (wb)")
            continue

        # Average embeddings and L2-normalize
        probe_emb_wb = np.mean(embeddings_wb, axis=0).astype(np.float32)
        probe_emb_wb = probe_emb_wb / (np.linalg.norm(probe_emb_wb) + 1e-10)
        score_wb = get_best_match_score(probe_emb_wb, "wb")

        # Step 2: Degrade to nb8k
        degraded_path = TEMP_DIR / f"{Path(test_file).stem}_nb8k.wav"
        result = codec.degrade(test_file, str(degraded_path), "nb8k")

        if result is None:
            logger.warning(f"  Could not degrade to nb8k")
            continue

        # Step 3: Verify degraded audio against wideband centroid (naive)
        audio_nb8k, sr_nb8k = embed.load_audio(str(degraded_path))
        if len(audio_nb8k) == 0:
            logger.warning(f"  Could not load degraded audio")
            continue

        embeddings_nb8k = embed.embed_chunks(audio_nb8k, sr_nb8k, [])
        if not embeddings_nb8k:
            logger.warning(f"  Could not extract embeddings (nb8k)")
            continue

        probe_emb_nb8k = np.mean(embeddings_nb8k, axis=0).astype(np.float32)
        probe_emb_nb8k = probe_emb_nb8k / (np.linalg.norm(probe_emb_nb8k) + 1e-10)

        # Naive: compare against wideband centroid
        score_naive = get_best_match_score(probe_emb_nb8k, "wb")

        # Condition-matched: compare against nb8k centroid
        score_condition_matched = get_best_match_score(probe_emb_nb8k, "nb8k")

        # Calculate relative drops
        if score_wb > 0:
            drop_naive = (score_wb - score_naive) / score_wb
            drop_recovered = (score_wb - score_condition_matched) / score_wb
        else:
            drop_naive = 0.0
            drop_recovered = 0.0

        results[fname] = {
            "wideband": round(score_wb, 4),
            "naive_nb8k": round(score_naive, 4),
            "condition_matched_nb8k": round(score_condition_matched, 4),
            "drop_naive_pct": round(drop_naive * 100, 1),
            "drop_recovered_pct": round(drop_recovered * 100, 1),
        }

        logger.info(
            f"  wb={score_wb:.4f} naive={score_naive:.4f} "
            f"cm={score_condition_matched:.4f} "
            f"drop={drop_naive*100:.1f}% recovery={drop_recovered*100:.1f}%"
        )

    # Save results
    output_path = Path("data/ablation_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"\nResults saved to {output_path}\n")

    # Print table
    print("=" * 120)
    print("Ablation Results Table")
    print("=" * 120)
    print(f"{'File':<30} {'Wideband':<12} {'Naive 8k':<12} {'Cond.Match':<12} "
          f"{'Drop %':<12} {'Recovery %':<12}")
    print("-" * 120)

    for fname, data in sorted(results.items()):
        print(
            f"{fname:<30} "
            f"{data['wideband']:<12.4f} "
            f"{data['naive_nb8k']:<12.4f} "
            f"{data['condition_matched_nb8k']:<12.4f} "
            f"{data['drop_naive_pct']:<12.1f} "
            f"{data['drop_recovered_pct']:<12.1f}"
        )

    print("=" * 120)
    print("\nInterpretation:")
    print("  Drop %      = (wideband - naive_nb8k) / wideband * 100")
    print("  Recovery %  = (wideband - condition_matched) / wideband * 100")
    print("  Low recovery % means condition-matched enrollment recovered the loss.")
    print("=" * 120)

    # Cleanup
    import shutil
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)


if __name__ == "__main__":
    run_ablation()
