"""
audio_ml/enroll.py — Enroll a speaker by extracting and storing voiceprints.

Public API for enrollment. Produces condition-matched voiceprints:
  - wb (wideband):  embeddings of concatenated audio at 16 kHz
  - nb8k (narrowband): embeddings of codec-degraded audio at 8 kHz

Two conditions prevent channel difference from masquerading as speaker difference.
All errors are caught internally; functions return valid defaults.
"""

from __future__ import annotations

import logging
import numpy as np
import tempfile
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from . import embed, codec
from contracts import Person

logger = logging.getLogger(__name__)

# Enrollment storage
ENROLLMENTS_DIR = Path(__file__).parent.parent / "data" / "enrollments"


def load_voiceprint(person_id: str) -> Optional[dict]:
    """
    Load a saved voiceprint from disk.

    Args:
        person_id: Person identifier (filename stem without .npz)

    Returns:
        Dict with keys: wb, nb8k, name, relationship, n_samples, enrolled_at
        Returns None if file not found or corrupted.
    """
    try:
        npz_path = ENROLLMENTS_DIR / f"{person_id}.npz"

        if not npz_path.exists():
            logger.warning(f"Enrollment not found: {npz_path}")
            return None

        data = np.load(npz_path, allow_pickle=True)

        # Verify all required keys are present
        required_keys = {"wb", "nb8k", "name", "relationship", "n_samples", "enrolled_at"}
        if not required_keys.issubset(data.files):
            logger.error(f"Enrollment {person_id} missing required keys. Has: {set(data.files)}")
            return None

        voiceprint = {
            "wb": np.array(data["wb"], dtype=np.float32),
            "nb8k": np.array(data["nb8k"], dtype=np.float32),
            "name": str(data["name"]),
            "relationship": str(data["relationship"]),
            "n_samples": int(data["n_samples"]),
            "enrolled_at": str(data["enrolled_at"]),
        }

        logger.info(f"Loaded voiceprint for {voiceprint['name']} ({person_id})")
        return voiceprint

    except Exception as e:
        logger.error(f"load_voiceprint({person_id}): {type(e).__name__}: {e}")
        return None


def list_persons() -> list[dict]:
    """
    List all enrolled persons.

    Returns:
        List of Person-shaped dicts for every .npz in data/enrollments/
        Returns empty list on error or if no enrollments exist.
    """
    try:
        if not ENROLLMENTS_DIR.exists():
            logger.debug(f"Enrollments directory does not exist: {ENROLLMENTS_DIR}")
            return []

        persons = []
        for npz_path in ENROLLMENTS_DIR.glob("*.npz"):
            person_id = npz_path.stem
            voiceprint = load_voiceprint(person_id)

            if voiceprint:
                person = Person(
                    person_id=person_id,
                    name=voiceprint["name"],
                    relationship=voiceprint["relationship"],
                    enrolled_at=voiceprint["enrolled_at"],
                    n_samples=voiceprint["n_samples"],
                    conditions=["wb", "nb8k"],
                )
                persons.append(person.model_dump())

        logger.info(f"list_persons: found {len(persons)} enrollment(s)")
        return persons

    except Exception as e:
        logger.error(f"list_persons: {type(e).__name__}: {e}")
        return []


def enroll_person(
    person_id: str,
    name: str,
    relationship: str,
    wav_paths: list[str]
) -> Optional[dict]:
    """
    Enroll a speaker by extracting and storing condition-matched voiceprints.

    Args:
        person_id: Unique identifier for the person (e.g., "alice_001")
        name: Display name
        relationship: Relationship type (e.g., "family", "friend", "colleague")
        wav_paths: List of paths to WAV files to enroll

    Returns:
        Dict matching Person contract: {person_id, name, relationship, enrolled_at, n_samples, conditions}
        Returns None on failure (logged internally; function never raises).

    Process:
        1. Load and concatenate all wav_paths
        2. Extract VAD segments
        3. Chunk and embed the concatenated audio → wb_centroid
        4. Degrade audio to 8 kHz (nb8k mode) via ffmpeg
        5. Chunk and embed degraded audio → nb8k_centroid
        6. Save both centroids to data/enrollments/{person_id}.npz
    """
    try:
        if not wav_paths:
            logger.error(f"enroll_person({person_id}): no WAV files provided")
            return None

        # Ensure enrollment directory exists
        ENROLLMENTS_DIR.mkdir(parents=True, exist_ok=True)

        # Step 1: Load and concatenate all audio
        logger.info(f"enroll_person({person_id}): loading {len(wav_paths)} audio file(s)")
        concatenated_audio = []
        sr = 16000  # All loaded audio is resampled to 16 kHz
        total_samples = 0

        for wav_path in wav_paths:
            audio, _ = embed.load_audio(wav_path)
            if len(audio) == 0:
                logger.warning(f"  Skipping {wav_path} (load failed)")
                continue
            concatenated_audio.append(audio)
            total_samples += len(audio)

        if not concatenated_audio:
            logger.error(f"enroll_person({person_id}): no valid audio loaded from {wav_paths}")
            return None

        # Concatenate with small padding to avoid artifacts
        full_audio = np.concatenate(concatenated_audio, dtype=np.float32)
        logger.info(f"  Concatenated {len(concatenated_audio)} file(s): {total_samples} samples ({total_samples/sr:.2f}s)")

        # Step 2: Extract VAD segments and embed
        logger.info(f"enroll_person({person_id}): extracting VAD segments and embeddings")
        segments = embed.vad_segments(full_audio, sr)
        logger.info(f"  VAD found {len(segments)} speech segment(s)")

        # Step 3: Chunk and embed at wideband (16 kHz)
        try:
            wb_embeddings = embed.embed_chunks(full_audio, sr, segments)
        except Exception as e:
            logger.error(f"enroll_person({person_id}): failed to extract wideband embeddings: {e}")
            return None

        # Compute wideband centroid (L2-normalised mean)
        wb_centroid = np.mean(wb_embeddings, axis=0).astype(np.float32)
        wb_norm = np.linalg.norm(wb_centroid)
        if wb_norm > 0:
            wb_centroid = wb_centroid / wb_norm
        logger.info(f"  WB centroid: L2 norm = {np.linalg.norm(wb_centroid):.6f}")

        # Step 4: Degrade to narrowband (8 kHz) and re-embed
        logger.info(f"enroll_person({person_id}): degrading audio to narrowband (8 kHz)")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_concat:
            temp_concat_path = temp_concat.name

        try:
            # Write concatenated audio to temp file
            import wave
            with wave.open(temp_concat_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sr)
                wav_file.writeframes((full_audio * 32767).astype(np.int16).tobytes())

            # Degrade to nb8k
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_degraded:
                temp_degraded_path = temp_degraded.name

            degraded_path = codec.degrade(temp_concat_path, temp_degraded_path, mode="nb8k")
            if not degraded_path:
                logger.error(f"enroll_person({person_id}): codec degradation failed")
                return None

            # Load degraded audio
            degraded_audio, _ = embed.load_audio(degraded_path)
            if len(degraded_audio) == 0:
                logger.error(f"enroll_person({person_id}): could not load degraded audio")
                return None

            # Extract VAD segments and embed degraded audio
            segments_degraded = embed.vad_segments(degraded_audio, sr)
            try:
                nb8k_embeddings = embed.embed_chunks(degraded_audio, sr, segments_degraded)
            except Exception as e:
                logger.error(f"enroll_person({person_id}): failed to extract narrowband embeddings: {e}")
                return None

            # Compute narrowband centroid (L2-normalised mean)
            nb8k_centroid = np.mean(nb8k_embeddings, axis=0).astype(np.float32)
            nb8k_norm = np.linalg.norm(nb8k_centroid)
            if nb8k_norm > 0:
                nb8k_centroid = nb8k_centroid / nb8k_norm
            logger.info(f"  NB8K centroid: L2 norm = {np.linalg.norm(nb8k_centroid):.6f}")

        finally:
            # Clean up temp files
            import os
            if os.path.exists(temp_concat_path):
                os.remove(temp_concat_path)
            if os.path.exists(temp_degraded_path):
                os.remove(temp_degraded_path)

        # Step 5: Save to .npz
        npz_path = ENROLLMENTS_DIR / f"{person_id}.npz"
        enrolled_at = datetime.now(timezone.utc).isoformat()

        np.savez(
            npz_path,
            wb=wb_centroid,
            nb8k=nb8k_centroid,
            name=name,
            relationship=relationship,
            n_samples=len(full_audio),
            enrolled_at=enrolled_at,
        )
        logger.info(f"enroll_person({person_id}): saved to {npz_path}")

        # Step 6: Return Person contract
        result = Person(
            person_id=person_id,
            name=name,
            relationship=relationship,
            enrolled_at=enrolled_at,
            n_samples=len(full_audio),
            conditions=["wb", "nb8k"],
        )
        logger.info(f"✓ Enrollment complete: {person_id} ({name})")
        return result.model_dump()

    except Exception as e:
        logger.error(f"enroll_person({person_id}): {type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    """
    Smoke test: enroll from a folder of wavs and print results.

    Usage:
        python -m audio_ml.enroll <input_folder> [person_id] [name] [relationship]

    Example:
        python -m audio_ml.enroll data/cohort/alice alice Alice family
    """
    import sys

    # Configure logging for test
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s"
    )

    print("\n" + "=" * 70)
    print("audio_ml.enroll smoke test")
    print("=" * 70)

    # Parse arguments
    if len(sys.argv) < 2:
        print("\nUsage: python -m audio_ml.enroll <input_folder> [person_id] [name] [relationship]")
        print("\nExample:")
        print("  python -m audio_ml.enroll data/cohort/alice alice Alice family")
        print("  python -m audio_ml.enroll data/cohort/bob bob Bob colleague")
        sys.exit(1)

    input_folder = sys.argv[1]
    person_id = sys.argv[2] if len(sys.argv) > 2 else Path(input_folder).name
    name = sys.argv[3] if len(sys.argv) > 3 else person_id.title()
    relationship = sys.argv[4] if len(sys.argv) > 4 else "family"

    # Collect WAV files
    folder_path = Path(input_folder)
    if not folder_path.exists():
        print(f"\n✗ Folder not found: {input_folder}")
        sys.exit(1)

    wav_files = sorted(folder_path.glob("*.wav"))
    if not wav_files:
        print(f"\n✗ No .wav files found in {input_folder}")
        sys.exit(1)

    print(f"\nEnrolling {len(wav_files)} audio file(s) from {input_folder}")
    print(f"  person_id: {person_id}")
    print(f"  name: {name}")
    print(f"  relationship: {relationship}")

    wav_paths = [str(wf) for wf in wav_files]

    # Enroll
    result = enroll_person(person_id, name, relationship, wav_paths)

    print("\n" + "-" * 70)
    if result:
        # Load back the voiceprint to report centroids
        voiceprint = load_voiceprint(person_id)
        if voiceprint:
            wb_norm = np.linalg.norm(voiceprint["wb"])
            nb8k_norm = np.linalg.norm(voiceprint["nb8k"])

            print("✓ ENROLLMENT SUCCESSFUL")
            print(f"\n  person_id: {result['person_id']}")
            print(f"  name: {result['name']}")
            print(f"  relationship: {result['relationship']}")
            print(f"  n_samples: {result['n_samples']}")
            print(f"  enrolled_at: {result['enrolled_at']}")
            print(f"  WB centroid L2 norm: {wb_norm:.6f} (expect ~1.0)")
            print(f"  NB8K centroid L2 norm: {nb8k_norm:.6f} (expect ~1.0)")
            print()
            sys.exit(0)
        else:
            print("✗ ENROLLMENT FAILED: could not reload voiceprint")
            sys.exit(1)
    else:
        print("✗ ENROLLMENT FAILED: enroll_person returned None")
        sys.exit(1)
