"""
scripts/prepare_held_out_test.py — Create held-out test set from friend.wav.

Split friend.wav:
  - First 20 seconds: re-enrollment data
  - Last 10 seconds: held-out test data (friend_test.wav)

Then rebuild the friend voiceprint from only the first 20s.
"""

import os
import sys
import logging
import numpy as np
from pathlib import Path
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio_ml import embed, enroll
from contracts import Person

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ORIGINAL = "data/demo_clips/friend.wav"
ENROLL_OUT = "data/cohort/bg/friend_enrollment.wav"
TEST_OUT = "data/demo_clips/friend_test.wav"

ENROLL_DURATION = 20.0  # First 20 seconds
TEST_OFFSET = 20.0      # Last 10 seconds start at 20s


def split_audio_with_ffmpeg(input_path: str, enroll_out: str, test_out: str):
    """Split audio file into enrollment and test portions using ffmpeg."""
    logger.info(f"Splitting {input_path}...")

    # Create enrollment portion (0-20s)
    cmd_enroll = [
        "ffmpeg",
        "-i", input_path,
        "-ss", "0",
        "-t", str(ENROLL_DURATION),
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-loglevel", "error",
        "-y",
        enroll_out
    ]
    result = subprocess.run(cmd_enroll, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Failed to create enrollment portion: {result.stderr}")
        return False
    logger.info(f"✓ Enrollment portion (0-{ENROLL_DURATION}s) → {enroll_out}")

    # Create test portion (20s onward)
    cmd_test = [
        "ffmpeg",
        "-i", input_path,
        "-ss", str(TEST_OFFSET),
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-loglevel", "error",
        "-y",
        test_out
    ]
    result = subprocess.run(cmd_test, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Failed to create test portion: {result.stderr}")
        return False
    logger.info(f"✓ Test portion ({TEST_OFFSET}s-end) → {test_out}")

    return True


def rebuild_enrollment(wav_path: str, person_id: str, name: str):
    """Re-enroll person from new wav file."""
    logger.info(f"\nRe-enrolling {name} from {wav_path}...")

    # Load audio
    audio, sr = embed.load_audio(wav_path)
    if len(audio) == 0:
        logger.error(f"Could not load audio")
        return False

    # Detect condition
    condition = embed.detect_condition(audio, sr)
    logger.info(f"Detected condition: {condition}")

    # Extract embeddings
    vad_segments = embed.vad_segments(audio, sr)
    embeddings = embed.embed_chunks(audio, sr, vad_segments)

    if not embeddings:
        logger.error(f"Could not extract embeddings")
        return False

    logger.info(f"Extracted {len(embeddings)} embedding(s)")

    # Compute centroid
    centroid = np.mean(embeddings, axis=0).astype(np.float32)
    centroid_norm = np.linalg.norm(centroid)
    if centroid_norm > 0:
        centroid = centroid / centroid_norm

    # Create enrollment directory
    enroll_dir = Path("data/enrollments")
    enroll_dir.mkdir(parents=True, exist_ok=True)

    # Save centroid by condition
    wb_path = enroll_dir / f"{person_id}_wb.npy"
    nb8k_path = enroll_dir / f"{person_id}_nb8k.npy"

    if condition == "wb":
        np.save(wb_path, centroid)
        logger.info(f"✓ Saved wideband centroid to {wb_path}")

        # Also ensure nb8k exists (copy or load from old if available)
        if not nb8k_path.exists():
            # Try to load old nb8k enrollment
            old_nb8k = Path("data/enrollments_backup") / f"{person_id}_nb8k.npy"
            if old_nb8k.exists():
                import shutil
                shutil.copy(old_nb8k, nb8k_path)
                logger.info(f"✓ Restored nb8k centroid from backup")
            else:
                # Use wb centroid as fallback
                np.save(nb8k_path, centroid)
                logger.info(f"✓ Saved wideband centroid as nb8k fallback")
    else:
        np.save(nb8k_path, centroid)
        logger.info(f"✓ Saved narrowband centroid to {nb8k_path}")

        # Ensure wb exists
        if not wb_path.exists():
            np.save(wb_path, centroid)
            logger.info(f"✓ Saved narrowband centroid as wideband fallback")

    # Save metadata
    metadata_path = enroll_dir / f"{person_id}_metadata.json"
    import json
    metadata = {
        "person_id": person_id,
        "name": name,
        "condition_used": condition,
        "n_embeddings": len(embeddings),
    }
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"✓ Saved metadata to {metadata_path}")
    return True


def main():
    if not Path(ORIGINAL).exists():
        logger.error(f"Original file not found: {ORIGINAL}")
        sys.exit(1)

    # Step 1: Split audio
    Path(ENROLL_OUT).parent.mkdir(parents=True, exist_ok=True)
    if not split_audio_with_ffmpeg(ORIGINAL, ENROLL_OUT, TEST_OUT):
        sys.exit(1)

    # Step 2: Verify split files
    for fpath in [ENROLL_OUT, TEST_OUT]:
        audio, sr = embed.load_audio(fpath)
        duration = len(audio) / sr
        logger.info(f"{Path(fpath).name}: {duration:.1f}s")

    # Step 3: Rebuild enrollment from first 20s
    if not rebuild_enrollment(ENROLL_OUT, "friend", "Friend"):
        sys.exit(1)

    logger.info("\n" + "="*60)
    logger.info("✓ Held-out test set prepared!")
    logger.info(f"  Enrollment data: {ENROLL_OUT}")
    logger.info(f"  Test data: {TEST_OUT}")
    logger.info("="*60)


if __name__ == "__main__":
    main()
