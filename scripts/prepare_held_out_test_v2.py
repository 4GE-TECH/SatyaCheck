"""
Create enrollment centroids from both wideband and degraded nb8k versions.
"""

import os
import sys
import logging
import numpy as np
from pathlib import Path
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio_ml import embed, codec

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ENROLL_WB = "data/cohort/bg/friend_enrollment.wav"
ENROLL_NB8K_TEMP = "data/cohort/bg/friend_enrollment_nb8k_temp.wav"
ENROLL_DIR = Path("data/enrollments")


def extract_centroid(wav_path: str, condition: str) -> np.ndarray:
    """Extract and normalize centroid from wav file."""
    logger.info(f"Extracting {condition} centroid from {Path(wav_path).name}...")

    audio, sr = embed.load_audio(wav_path)
    if len(audio) == 0:
        logger.error(f"  Could not load audio")
        return None

    vad_segments = embed.vad_segments(audio, sr)
    embeddings = embed.embed_chunks(audio, sr, vad_segments)

    if not embeddings:
        logger.error(f"  No embeddings extracted")
        return None

    logger.info(f"  Extracted {len(embeddings)} embedding(s)")

    # Compute and normalize centroid
    centroid = np.mean(embeddings, axis=0).astype(np.float32)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid = centroid / norm

    return centroid


def main():
    ENROLL_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Creating condition-matched enrollment centroids...\n")

    # Extract wideband centroid
    logger.info("=" * 60)
    logger.info("WIDEBAND CENTROID")
    logger.info("=" * 60)
    wb_centroid = extract_centroid(ENROLL_WB, "wideband")
    if wb_centroid is None:
        logger.error("Failed to extract wideband centroid")
        sys.exit(1)

    # Save wideband
    wb_path = ENROLL_DIR / "friend_wb.npy"
    np.save(wb_path, wb_centroid)
    logger.info(f"✓ Saved to {wb_path}\n")

    # Create nb8k version of enrollment audio
    logger.info("=" * 60)
    logger.info("NARROWBAND (8kHz) CENTROID")
    logger.info("=" * 60)
    logger.info(f"Degrading enrollment audio to 8kHz...")
    result = codec.degrade(ENROLL_WB, ENROLL_NB8K_TEMP, "nb8k")
    if result is None:
        logger.error("Failed to degrade audio to 8kHz")
        sys.exit(1)

    # Extract narrowband centroid
    nb8k_centroid = extract_centroid(ENROLL_NB8K_TEMP, "narrowband")
    if nb8k_centroid is None:
        logger.error("Failed to extract narrowband centroid")
        sys.exit(1)

    # Save narrowband
    nb8k_path = ENROLL_DIR / "friend_nb8k.npy"
    np.save(nb8k_path, nb8k_centroid)
    logger.info(f"✓ Saved to {nb8k_path}\n")

    # Compute similarity between the two centroids
    similarity = float(np.dot(wb_centroid, nb8k_centroid))
    logger.info(f"Centroid similarity (wb vs nb8k): {similarity:.4f}")
    logger.info(f"(Values < 0.95 indicate meaningful channel difference)\n")

    # Save metadata
    metadata = {
        "person_id": "friend",
        "name": "Friend",
        "enroll_wb_centroid": str(wb_path),
        "enroll_nb8k_centroid": str(nb8k_path),
        "centroid_similarity": round(similarity, 4),
    }
    metadata_path = ENROLL_DIR / "friend_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"✓ Saved metadata to {metadata_path}\n")

    # Cleanup
    Path(ENROLL_NB8K_TEMP).unlink(missing_ok=True)

    logger.info("=" * 60)
    logger.info("✓ Condition-matched enrollment ready for ablation!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
