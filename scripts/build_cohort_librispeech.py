"""
scripts/build_cohort_librispeech.py — Build speaker cohort from LibriSpeech dev-clean.

Extracts ECAPA-TDNN embeddings from LibriSpeech speakers and saves as cohort.npy
for s-normalisation in speaker verification.

Usage:
    python scripts/build_cohort_librispeech.py
"""

import os
import subprocess
import logging
from pathlib import Path
import numpy as np
import sys

# Add parent directory to path so we can import audio_ml
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio_ml import embed
from audio_ml.verify import build_cohort

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

LIBRISPEECH_DIR = Path("LibriSpeech/dev-clean")
COHORT_BG_DIR = Path("data/cohort/bg")
MAX_SPEAKERS = 40
MAX_DURATION_S = 60.0  # Cap each speaker at ~60 seconds


def get_flac_files(speaker_dir: Path) -> list:
    """Get all .flac files recursively from speaker directory."""
    return sorted(speaker_dir.glob("*/*.flac"))


def get_duration(flac_path: Path) -> float:
    """Get duration of a flac file in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1:noprint_wrappers=1",
             str(flac_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"Could not get duration of {flac_path}: {e}")
        return 0.0


def concatenate_flacs_to_wav(flac_files: list, output_wav: Path, max_duration: float) -> bool:
    """
    Concatenate multiple FLAC files into a single WAV, capping at max_duration.

    Uses ffmpeg concat demuxer for fast concatenation.
    """
    if not flac_files:
        return False

    try:
        total_duration = 0.0
        selected_files = []

        for flac_path in flac_files:
            duration = get_duration(flac_path)
            if total_duration + duration > max_duration:
                break
            selected_files.append(flac_path)
            total_duration += duration

        if not selected_files:
            logger.warning(f"No flac files selected for {output_wav.stem}")
            return False

        logger.info(
            f"  Concatenating {len(selected_files)} flac files "
            f"({total_duration:.1f}s) -> {output_wav.name}"
        )

        # Build filter_complex for concatenating multiple files
        # This avoids the concat demuxer and concat file issues
        filter_parts = []
        for i, flac_path in enumerate(selected_files):
            filter_parts.append(f"[{i}:a]")
        filter_str = "".join(filter_parts) + f"concat=n={len(selected_files)}:v=0:a=1[out]"

        cmd = ["ffmpeg", "-loglevel", "error", "-y"]
        for flac_path in selected_files:
            cmd.extend(["-i", str(flac_path)])

        cmd.extend([
            "-filter_complex", filter_str,
            "-map", "[out]",
            "-c:a", "pcm_s16le",  # Output codec
            "-ar", "16000",        # Resample to 16kHz
            "-ac", "1",            # Mono
            str(output_wav)
        ])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            logger.error(f"  ffmpeg failed: {result.stderr}")
            return False

        logger.info(f"  ✓ Created {output_wav.name}")
        return True

    except Exception as e:
        logger.error(f"Failed to concatenate flacs: {e}")
        return False


def main():
    """Build cohort from LibriSpeech dev-clean."""

    if not LIBRISPEECH_DIR.exists():
        logger.error(f"LibriSpeech directory not found: {LIBRISPEECH_DIR}")
        sys.exit(1)

    # Create output directory
    COHORT_BG_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {COHORT_BG_DIR}")

    # Get speaker directories
    speaker_dirs = sorted(
        [d for d in LIBRISPEECH_DIR.iterdir() if d.is_dir()]
    )[:MAX_SPEAKERS]

    logger.info(f"Found {len(speaker_dirs)} speaker(s), processing first {MAX_SPEAKERS}")

    # Process each speaker
    successful = 0
    for idx, speaker_dir in enumerate(speaker_dirs, 1):
        speaker_id = speaker_dir.name
        flac_files = get_flac_files(speaker_dir)

        if not flac_files:
            logger.warning(f"[{idx}/{len(speaker_dirs)}] {speaker_id}: no flac files")
            continue

        output_wav = COHORT_BG_DIR / f"{speaker_id}.wav"

        logger.info(f"[{idx}/{len(speaker_dirs)}] {speaker_id}: {len(flac_files)} flac files")

        if concatenate_flacs_to_wav(flac_files, output_wav, MAX_DURATION_S):
            successful += 1
        else:
            logger.warning(f"  Failed to process {speaker_id}")

    logger.info(f"\n{'='*60}")
    logger.info(f"Successfully processed {successful}/{len(speaker_dirs)} speakers")
    logger.info(f"{'='*60}\n")

    # Extract embeddings from each wav file
    logger.info(f"Extracting ECAPA-TDNN embeddings from {successful} speakers...")
    embedded = 0
    for wav_path in sorted(COHORT_BG_DIR.glob("*.wav")):
        try:
            audio, sr = embed.load_audio(str(wav_path))
            if len(audio) == 0:
                logger.warning(f"  {wav_path.name}: empty audio")
                continue

            embeddings = embed.embed_chunks(audio, sr, [])
            if not embeddings:
                logger.warning(f"  {wav_path.name}: no embeddings")
                continue

            # Average embeddings across chunks
            avg_embedding = np.mean(embeddings, axis=0).astype(np.float32)

            # Save as .npy
            npy_path = wav_path.with_suffix(".npy")
            np.save(npy_path, avg_embedding)
            embedded += 1
            logger.info(f"  ✓ {wav_path.name} -> {npy_path.name}")

        except Exception as e:
            logger.warning(f"  {wav_path.name}: {type(e).__name__}: {e}")

    logger.info(f"Extracted {embedded} embeddings\n")

    # Build cohort from .npy files
    logger.info(f"Building cohort from {embedded} embeddings...")
    build_cohort(str(COHORT_BG_DIR))

    # Verify cohort was created
    cohort_path = Path("data/cohort/cohort.npy")
    if cohort_path.exists():
        cohort = np.load(cohort_path)
        logger.info(f"✓ Cohort created: {cohort.shape}")
        logger.info(f"  {cohort.shape[0]} speakers × {cohort.shape[1]} dims")
        logger.info(f"  Ready for s-normalisation in verify_speaker()")
    else:
        logger.error("Cohort was not created!")
        sys.exit(1)


if __name__ == "__main__":
    main()
