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
from audio_ml.signals import Person

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
            "nb8k_sim": np.array(data["nb8k"], dtype=np.float32),  # Simulated (ffmpeg-degraded)
            "nb8k_real": np.array(data.get("nb8k_real"), dtype=np.float32) if "nb8k_real" in data.files else None,
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


def delete_person(person_id: str) -> bool:
    """Delete a person's voiceprint file. True if one was removed. Never raises."""
    try:
        if not person_id or Path(person_id).name != person_id or person_id in {".", ".."}:
            logger.warning(f"delete_person: refusing suspicious id {person_id!r}")
            return False
        npz_path = ENROLLMENTS_DIR / f"{person_id}.npz"
        if not npz_path.is_file():
            return False
        npz_path.unlink()
        logger.info(f"delete_person({person_id}): removed {npz_path}")
        return True
    except Exception as e:
        logger.error(f"delete_person({person_id}): {type(e).__name__}: {e}")
        return False


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


def legacy_candidates() -> list[dict]:
    """Every person in the legacy data/enrollments/*.npz store, in verify_speaker's
    `candidates` shape: {"person_id", "name", "relationship", "centroids": {condition: vector}}.
    Never raises; an unreadable file is skipped and logged by load_voiceprint."""
    candidates = []
    try:
        for person in list_persons():
            voiceprint = load_voiceprint(person["person_id"])
            if not voiceprint:
                logger.warning(f"legacy_candidates: could not load voiceprint for {person['person_id']}")
                continue
            candidates.append({
                "person_id": person["person_id"],
                "name": person["name"],
                "relationship": person["relationship"],
                "centroids": {k: voiceprint.get(k) for k in ("wb", "nb8k_real", "nb8k_sim")},
            })
    except Exception as e:
        logger.error(f"legacy_candidates: {type(e).__name__}: {e}")
    return candidates


def _centroid(embeddings) -> np.ndarray:
    """L2-normalised mean of chunk embeddings."""
    centroid = np.mean(embeddings, axis=0).astype(np.float32)
    norm = np.linalg.norm(centroid)
    return centroid / norm if norm > 0 else centroid


def _load_concatenated(paths: list[str], label: str) -> Optional[np.ndarray]:
    """Every loadable file in `paths`, concatenated at 16 kHz; None if none loaded."""
    parts = []
    for path in paths:
        audio, _ = embed.load_audio(path)
        if len(audio) == 0:
            logger.warning(f"compute_voiceprint: skipping {path} ({label}, load failed)")
            continue
        parts.append(audio)
    if not parts:
        return None
    return np.concatenate(parts, dtype=np.float32)


def compute_voiceprint(
    wav_paths: list[str],
    nb8k_real_paths: Optional[list[str]] = None,
) -> Optional[dict]:
    """
    Compute condition-matched voiceprints in memory. Writes nothing to disk.

    Returns {"wb": (192,), "nb8k_sim": (192,), "n_samples": int} plus "nb8k_real" when
    `nb8k_real_paths` yields a centroid; every vector is unit length. Returns None
    (logged) when no voiceprint can be built. Never raises.

    Process:
        1. Load and concatenate all wav_paths (wideband)
        2. VAD, chunk and embed -> wb centroid
        3. Degrade to 8 kHz via ffmpeg, embed again -> nb8k_sim centroid
        4. If nb8k_real_paths: embed genuinely narrowband audio -> nb8k_real centroid
    """
    import os
    import wave

    sr = 16000  # All loaded audio is resampled to 16 kHz
    temp_paths: list[str] = []
    try:
        if not wav_paths:
            logger.error("compute_voiceprint: no WAV files provided")
            return None

        full_audio = _load_concatenated(wav_paths, "wideband")
        if full_audio is None:
            logger.error(f"compute_voiceprint: no valid audio loaded from {wav_paths}")
            return None
        logger.info(f"compute_voiceprint: {len(wav_paths)} file(s), {len(full_audio)/sr:.2f}s")

        try:
            wb_embeddings = embed.embed_chunks(full_audio, sr, embed.vad_segments(full_audio, sr))
        except Exception as e:
            logger.error(f"compute_voiceprint: wideband embedding failed: {e}")
            return None
        if not len(wb_embeddings):
            logger.error("compute_voiceprint: no wideband embeddings (no speech found)")
            return None
        voiceprint = {"wb": _centroid(wb_embeddings), "n_samples": int(len(full_audio))}

        # Degrade to narrowband (8 kHz) and re-embed.
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_concat:
            temp_concat_path = temp_concat.name
        temp_paths.append(temp_concat_path)
        with wave.open(temp_concat_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sr)
            wav_file.writeframes((np.clip(full_audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_degraded:
            temp_degraded_path = temp_degraded.name
        temp_paths.append(temp_degraded_path)

        degraded_path = codec.degrade(temp_concat_path, temp_degraded_path, mode="nb8k")
        if not degraded_path:
            logger.error("compute_voiceprint: codec degradation failed")
            return None
        degraded_audio, _ = embed.load_audio(degraded_path)
        if len(degraded_audio) == 0:
            logger.error("compute_voiceprint: could not load degraded audio")
            return None
        try:
            nb8k_embeddings = embed.embed_chunks(degraded_audio, sr, embed.vad_segments(degraded_audio, sr))
        except Exception as e:
            logger.error(f"compute_voiceprint: narrowband embedding failed: {e}")
            return None
        if not len(nb8k_embeddings):
            logger.error("compute_voiceprint: no narrowband embeddings")
            return None
        voiceprint["nb8k_sim"] = _centroid(nb8k_embeddings)

        # Optional: genuinely narrowband audio (e.g. a phone call). Its absence is not a
        # failure; the two centroids above are a complete voiceprint.
        if nb8k_real_paths:
            real_audio = _load_concatenated(nb8k_real_paths, "nb8k_real")
            if real_audio is None:
                logger.warning("compute_voiceprint: no nb8k_real audio loaded; skipping that centroid")
            else:
                try:
                    real_embeddings = embed.embed_chunks(real_audio, sr, embed.vad_segments(real_audio, sr))
                    if len(real_embeddings):
                        voiceprint["nb8k_real"] = _centroid(real_embeddings)
                    else:
                        logger.warning("compute_voiceprint: no nb8k_real embeddings; skipping that centroid")
                except Exception as e:
                    logger.warning(f"compute_voiceprint: nb8k_real embedding failed, skipped: {e}")

        logger.info(f"compute_voiceprint: conditions {[k for k in voiceprint if k != 'n_samples']}")
        return voiceprint

    except Exception as e:
        logger.error(f"compute_voiceprint: {type(e).__name__}: {e}")
        return None
    finally:
        for path in temp_paths:
            if os.path.exists(path):
                os.remove(path)


def enroll_person(
    person_id: str,
    name: str,
    relationship: str,
    wav_paths: list[str],
    nb8k_real_paths: Optional[list[str]] = None
) -> Optional[dict]:
    """
    Enroll a speaker and save the voiceprint to data/enrollments/{person_id}.npz.

    CLI and test path only. The server computes with `compute_voiceprint` and stores the
    vectors in its database; this file store is the legacy one.

    Returns:
        Dict matching Person contract: {person_id, name, relationship, enrolled_at, n_samples, conditions}
        Returns None on failure (logged internally; function never raises).
    """
    try:
        voiceprint = compute_voiceprint(wav_paths, nb8k_real_paths)
        if voiceprint is None:
            logger.error(f"enroll_person({person_id}): no voiceprint computed")
            return None

        ENROLLMENTS_DIR.mkdir(parents=True, exist_ok=True)
        npz_path = ENROLLMENTS_DIR / f"{person_id}.npz"
        enrolled_at = datetime.now(timezone.utc).isoformat()
        save_dict = {
            "wb": voiceprint["wb"],
            "nb8k": voiceprint["nb8k_sim"],
            "name": name,
            "relationship": relationship,
            "n_samples": voiceprint["n_samples"],
            "enrolled_at": enrolled_at,
        }
        conditions = ["wb", "nb8k_sim"]
        if "nb8k_real" in voiceprint:
            save_dict["nb8k_real"] = voiceprint["nb8k_real"]
            conditions.append("nb8k_real")

        np.savez(npz_path, **save_dict)
        logger.info(f"enroll_person({person_id}): saved to {npz_path}")

        result = Person(
            person_id=person_id,
            name=name,
            relationship=relationship,
            enrolled_at=enrolled_at,
            n_samples=voiceprint["n_samples"],
            conditions=conditions,
        )
        logger.info(f"Enrollment complete: {person_id} ({name})")
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
            nb8k_norm = np.linalg.norm(voiceprint["nb8k_sim"])

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
