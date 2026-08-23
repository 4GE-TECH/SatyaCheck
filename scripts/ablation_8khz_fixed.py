"""
scripts/ablation_8khz_fixed.py — Fixed ablation with held-out test and separation metric.

Measures condition-matched enrollment effectiveness using SEPARATION:
  separation = mean(genuine_scores) - mean(impostor_scores)

Genuine: friend_test.wav (held-out, 10.4s from friend)
Impostors: person1, person2, person3 (unenrolled strangers)
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

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GENUINE_FILE = "data/demo_clips/friend_test.wav"

IMPOSTOR_FILES = [
    "data/eval_set/raw/person1.wav",
    "data/eval_set/raw/person2.wav",
    "data/eval_set/raw/person3.wav",
]

TEMP_DIR = Path("data/ablation_tmp")


def cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """Compute cosine similarity between two L2-normalized vectors."""
    return float(np.dot(emb1, emb2))


def get_best_match_score(probe_emb: np.ndarray, condition: str = "wb") -> float:
    """Get best match score against enrolled speakers for given condition."""
    best_score = -1.0
    for person_id in ["alice", "friend"]:
        voiceprint = load_voiceprint(person_id)
        if not voiceprint:
            continue

        # Select centroid based on condition
        if condition == "nb8k" and voiceprint.get("nb8k") is not None:
            centroid = voiceprint["nb8k"]
        else:
            centroid = voiceprint["wb"]

        score = cosine_similarity(probe_emb, centroid)
        best_score = max(best_score, score)

    return best_score if best_score >= 0 else 0.0


def process_file(test_file: str, label: str, condition: str = "wb") -> float:
    """
    Process a test file and return best match score.

    Args:
        test_file: Path to audio file
        label: Label for logging
        condition: "wb" or "nb8k"

    Returns:
        Best match cosine similarity
    """
    audio, sr = embed.load_audio(test_file)
    if len(audio) == 0:
        logger.warning(f"  {label}: could not load")
        return None

    embeddings = embed.embed_chunks(audio, sr, [])
    if not embeddings:
        logger.warning(f"  {label}: no embeddings")
        return None

    probe_emb = np.mean(embeddings, axis=0).astype(np.float32)
    probe_emb = probe_emb / (np.linalg.norm(probe_emb) + 1e-10)

    score = get_best_match_score(probe_emb, condition)
    logger.info(f"  {label}: {score:.4f}")
    return score


def run_ablation():
    """Run ablation experiment with separation metric."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    results = {
        "genuine_file": GENUINE_FILE,
        "impostor_files": IMPOSTOR_FILES,
        "by_condition": {}
    }

    print("\n" + "=" * 120)
    print("8kHz Ablation (Fixed): Condition-Matched Enrollment via SEPARATION")
    print("=" * 120)
    print()

    # Process each condition
    for condition_name, degradation_mode, centroid_condition in [
        ("wideband", None, "wb"),
        ("naive_nb8k", "nb8k", "wb"),  # Naive: degraded audio, wideband centroid (WRONG)
        ("condition_matched_nb8k", "nb8k", "nb8k"),  # Matched: degraded audio, nb8k centroid (RIGHT)
    ]:
        logger.info(f"\n{'='*60}")
        logger.info(f"Condition: {condition_name}")
        logger.info(f"{'='*60}")

        genuine_scores = []
        impostor_scores = []

        # Process genuine (friend_test.wav)
        logger.info("Genuine (friend_test.wav):")
        if degradation_mode:
            # Degrade to nb8k
            degraded = TEMP_DIR / "friend_test_nb8k.wav"
            codec.degrade(GENUINE_FILE, str(degraded), degradation_mode)
            test_path = str(degraded)
        else:
            test_path = GENUINE_FILE

        score = process_file(test_path, "friend_test", centroid_condition)
        if score is not None:
            genuine_scores.append(score)

        # Process impostors
        logger.info("Impostors:")
        for impostor_file in IMPOSTOR_FILES:
            if degradation_mode:
                # Degrade to nb8k
                degraded = TEMP_DIR / f"{Path(impostor_file).stem}_nb8k.wav"
                codec.degrade(impostor_file, str(degraded), degradation_mode)
                test_path = str(degraded)
            else:
                test_path = impostor_file

            score = process_file(
                test_path,
                Path(impostor_file).name,
                centroid_condition
            )
            if score is not None:
                impostor_scores.append(score)

        # Calculate separation
        if genuine_scores and impostor_scores:
            genuine_mean = np.mean(genuine_scores)
            impostor_mean = np.mean(impostor_scores)
            separation = genuine_mean - impostor_mean

            results["by_condition"][condition_name] = {
                "genuine_mean": round(genuine_mean, 4),
                "genuine_scores": [round(s, 4) for s in genuine_scores],
                "impostor_mean": round(impostor_mean, 4),
                "impostor_scores": [round(s, 4) for s in impostor_scores],
                "separation": round(separation, 4),
                "n_genuine": len(genuine_scores),
                "n_impostors": len(impostor_scores),
            }

            logger.info(f"\nSeparation: {separation:.4f}")
            logger.info(f"  Genuine mean: {genuine_mean:.4f} (scores: {[round(s, 4) for s in genuine_scores]})")
            logger.info(f"  Impostor mean: {impostor_mean:.4f} (scores: {[round(s, 4) for s in impostor_scores]})")

    # Save results
    output_path = Path("data/ablation_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"\nResults saved to {output_path}\n")

    # Print summary table
    print("\n" + "=" * 120)
    print("Separation Results (Higher = Better Discrimination)")
    print("=" * 120)
    print(f"{'Condition':<25} {'Genuine':<12} {'Impostor':<12} {'Separation':<12}")
    print("-" * 120)

    for cond in ["wideband", "naive_nb8k", "condition_matched_nb8k"]:
        if cond in results["by_condition"]:
            data = results["by_condition"][cond]
            print(
                f"{cond:<25} "
                f"{data['genuine_mean']:<12.4f} "
                f"{data['impostor_mean']:<12.4f} "
                f"{data['separation']:<12.4f}"
            )

    print("=" * 120)
    print("\nInterpretation:")
    print("  - Separation = genuine_mean - impostor_mean")
    print("  - Higher separation = better discrimination at a threshold")
    print("  - Condition-matched should maintain or improve separation vs naive")
    print("=" * 120)

    # Cleanup
    import shutil
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)


if __name__ == "__main__":
    run_ablation()
