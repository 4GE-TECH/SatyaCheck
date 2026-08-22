"""
audio_ml/verify.py — Speaker verification with s-normalisation.

Pure inference: embed probe, compare against enrolled speakers and cohort,
return s-normalised score with verdict (match/mismatch/unknown).

All errors caught internally; public functions return valid defaults.
"""

from __future__ import annotations

import logging
import numpy as np
from pathlib import Path
from typing import Optional

from . import embed, enroll
from contracts import SpeakerSignal
import config

logger = logging.getLogger(__name__)


# ===================================================================
# build_cohort(folder) — stack background speaker embeddings
# ===================================================================

def build_cohort(folder: str) -> None:
    """
    Build cohort from a folder of background speaker embeddings.

    Scans folder for .npy files, loads each as an embedding vector,
    stacks into (N, 192) array, saves to data/cohort/cohort.npy.

    Args:
        folder: Path to directory containing speaker .npy files

    Returns:
        None (saves directly to data/cohort/cohort.npy)

    Raises:
        Never. Logs warnings on error and returns gracefully.
    """
    try:
        folder_path = Path(folder)

        if not folder_path.exists():
            logger.warning(f"build_cohort: folder not found: {folder}")
            return

        # Collect all .npy files
        npy_files = sorted(folder_path.glob("*.npy"))

        if not npy_files:
            logger.warning(f"build_cohort: no .npy files in {folder}")
            return

        # Load and stack embeddings
        embeddings = []
        for npy_path in npy_files:
            try:
                emb = np.load(npy_path)
                if emb.ndim != 1 or emb.shape[0] != 192:
                    logger.warning(f"  Skipping {npy_path.name} (wrong shape: {emb.shape})")
                    continue
                embeddings.append(emb.astype(np.float32))
            except Exception as e:
                logger.warning(f"  Skipping {npy_path.name}: {type(e).__name__}")
                continue

        if not embeddings:
            logger.warning(f"build_cohort: no valid embeddings loaded from {folder}")
            return

        cohort = np.stack(embeddings, axis=0).astype(np.float32)
        n_speakers = cohort.shape[0]

        if n_speakers < 5:
            logger.warning(
                f"build_cohort: only {n_speakers} speakers (target ~50). "
                "S-normalisation may be unreliable."
            )

        # Ensure output directory exists
        cohort_dir = Path(config.COHORT_DIR)
        cohort_dir.mkdir(parents=True, exist_ok=True)

        # Save cohort
        cohort_path = cohort_dir / "cohort.npy"
        np.save(cohort_path, cohort)

        logger.info(
            f"build_cohort: saved {n_speakers} speaker(s) to {cohort_path} "
            f"(shape: {cohort.shape})"
        )

    except Exception as e:
        logger.error(f"build_cohort({folder}): {type(e).__name__}: {e}")


# ===================================================================
# snorm(raw, probe_emb, enrolled_emb, cohort) — s-normalisation
# ===================================================================

def snorm(
    raw: float,
    probe_emb: np.ndarray,
    enrolled_emb: np.ndarray,
    cohort: Optional[np.ndarray] = None,
) -> float:
    """
    Adaptive s-normalisation using cohort statistics.

    Formula:
        norm = 0.5 * ((raw - mean_enrolled) / std_enrolled
                    + (raw - mean_probe)    / std_probe)

    where mean/std are computed from cohort's cosine similarities.

    Args:
        raw: Raw cosine similarity (unnormalised)
        probe_emb: Probe embedding (192-dim, L2-normalised)
        enrolled_emb: Enrolled speaker centroid (192-dim, L2-normalised)
        cohort: Background cohort array (N, 192); if None or too small, returns raw

    Returns:
        Normalised score (float)

    Raises:
        Never. Returns raw score on error.
    """
    try:
        # Lazy-load cohort if not provided
        if cohort is None:
            cohort_path = Path(config.COHORT_DIR) / "cohort.npy"
            if cohort_path.exists():
                cohort = np.load(cohort_path)
            else:
                logger.debug(f"snorm: cohort not found at {cohort_path}, returning raw")
                return raw

        # Validate cohort size
        if cohort.ndim != 2 or cohort.shape[0] < 5:
            logger.debug(
                f"snorm: cohort too small ({cohort.shape[0]} < 5), returning raw"
            )
            return raw

        # Compute cosine similarities: probe vs cohort, enrolled vs cohort
        # Cosine = dot(a, b) when both are L2-normalised
        scores_probe = np.dot(cohort, probe_emb)      # (N,)
        scores_enrolled = np.dot(cohort, enrolled_emb)  # (N,)

        mean_probe = np.mean(scores_probe)
        std_probe = np.std(scores_probe)
        mean_enrolled = np.mean(scores_enrolled)
        std_enrolled = np.std(scores_enrolled)

        # Guard against zero std (all cohort members identical)
        if std_probe < 1e-10 or std_enrolled < 1e-10:
            logger.debug(f"snorm: zero cohort std, returning raw")
            return raw

        # Apply s-norm formula
        z_score = 0.5 * (
            (raw - mean_enrolled) / std_enrolled +
            (raw - mean_probe) / std_probe
        )

        # Clamp z-score to [-5, 5] range for numerical stability
        z_score = np.clip(z_score, -5.0, 5.0)

        # Map z-score to [0, 1] using sigmoid
        # sigmoid(z) = 1 / (1 + exp(-z))
        # This preserves ordering: higher raw -> higher sigmoid output
        norm = 1.0 / (1.0 + np.exp(-z_score))

        # If s-norm pushes a high-scoring speaker below 0.5, it's not helping.
        # Fall back to raw score if it's better for speaker verification.
        if raw > 0.7 and norm < 0.5:
            return raw

        return float(norm)

    except Exception as e:
        logger.error(f"snorm: {type(e).__name__}: {e}")
        return raw


# ===================================================================
# verify_speaker(wav_path) — main verification
# ===================================================================

def verify_speaker(wav_path: str) -> SpeakerSignal:
    """
    Verify speaker identity from audio file.

    Steps:
      1. Embed probe audio; detect condition (wb/nb8k)
      2. Load all enrolled speakers
      3. For each enrolled person, compute cosine vs matching centroid
      4. Select best match; s-normalise the score
      5. Determine verdict from thresholds
      6. Check against flagged-voice cohort
      7. Return SpeakerSignal with all fields filled

    Args:
        wav_path: Path to audio file

    Returns:
        SpeakerSignal with verdict, scores, best_match_name, etc.
        On any error, returns SpeakerSignal(verdict="unknown") with defaults.

    Raises:
        Never. All errors caught internally.
    """
    result = SpeakerSignal(verdict="unknown")

    try:
        # Step 1: Load and embed probe
        logger.info(f"verify_speaker({wav_path})")
        audio, sr = embed.load_audio(wav_path)

        if len(audio) == 0:
            logger.warning(f"verify_speaker: failed to load audio from {wav_path}")
            return result

        # Detect condition (wideband vs narrowband)
        condition = embed.detect_condition(audio, sr)
        result.condition_used = condition

        # Extract embeddings from probe
        segments = embed.vad_segments(audio, sr)
        try:
            embeddings = embed.embed_chunks(audio, sr, segments)
        except Exception as e:
            logger.error(f"verify_speaker: embed_chunks failed: {e}")
            return result

        if not embeddings:
            logger.warning(f"verify_speaker: no embeddings extracted")
            return result

        # Use mean of embeddings as probe embedding
        probe_emb = np.mean(embeddings, axis=0).astype(np.float32)
        probe_norm = np.linalg.norm(probe_emb)
        if probe_norm > 0:
            probe_emb = probe_emb / probe_norm  # L2-normalise
        logger.info(f"  Probe embedding: {len(embeddings)} chunks, condition={condition}")

        # Step 2: Load all enrolled speakers
        enrolled_persons = enroll.list_persons()
        if not enrolled_persons:
            logger.warning(f"verify_speaker: no enrolled speakers")
            return result

        # Step 3: Compare against each enrolled speaker
        best_raw = -2.0
        best_match_idx = -1

        for idx, person in enumerate(enrolled_persons):
            person_id = person["person_id"]
            voiceprint = enroll.load_voiceprint(person_id)

            if not voiceprint:
                logger.warning(f"  Could not load voiceprint for {person_id}")
                continue

            # Pick matching centroid based on detected probe condition
            if condition == "nb8k":
                # Probe is narrowband: try genuine narrowband centroid first, fall back to simulated
                if voiceprint.get("nb8k_real") is not None:
                    enrolled_centroid = voiceprint["nb8k_real"]
                    centroid_type = "nb8k_real"
                else:
                    enrolled_centroid = voiceprint["nb8k_sim"]
                    centroid_type = "nb8k_sim"
            else:
                # Probe is wideband: use wideband centroid
                enrolled_centroid = voiceprint["wb"]
                centroid_type = "wb"

            # Compute cosine similarity (both L2-normalised)
            raw_cosine = float(np.dot(probe_emb, enrolled_centroid))
            logger.debug(f"  {person['name']}: raw_cosine={raw_cosine:.4f} ({centroid_type})")

            if raw_cosine > best_raw:
                best_raw = raw_cosine
                best_match_idx = idx

        if best_match_idx < 0:
            logger.warning(f"verify_speaker: no valid enrolled persons matched")
            return result

        result.raw_cosine = best_raw
        best_match = enrolled_persons[best_match_idx]
        result.best_match_id = best_match["person_id"]
        result.best_match_name = best_match["name"]
        result.relationship = best_match["relationship"]

        logger.info(
            f"  Best match: {result.best_match_name} (raw_cosine={best_raw:.4f})"
        )

        # Step 4: S-normalise the best raw score
        best_voiceprint = enroll.load_voiceprint(result.best_match_id)
        if condition == "nb8k":
            if best_voiceprint.get("nb8k_real") is not None:
                best_enrolled = best_voiceprint["nb8k_real"]
            else:
                best_enrolled = best_voiceprint["nb8k_sim"]
        else:
            best_enrolled = best_voiceprint["wb"]

        # Load cohort for s-norm
        cohort_path = Path(config.COHORT_DIR) / "cohort.npy"
        cohort = None
        if cohort_path.exists():
            try:
                cohort = np.load(cohort_path)
            except Exception as e:
                logger.warning(f"verify_speaker: could not load cohort: {e}")

        norm_score = snorm(best_raw, probe_emb, best_enrolled, cohort)
        result.norm_score = norm_score

        logger.info(f"  S-normalised score: {norm_score:.4f}")

        # Step 5: Determine verdict from thresholds
        if norm_score >= config.SPEAKER_MATCH_THRESHOLD:
            result.verdict = "match"
        elif norm_score >= config.SPEAKER_UNKNOWN_FLOOR:
            result.verdict = "mismatch"
        else:
            result.verdict = "unknown"

        logger.info(
            f"  Verdict: {result.verdict} "
            f"(norm={norm_score:.4f}, threshold={config.SPEAKER_MATCH_THRESHOLD})"
        )

        # Step 6: Check against flagged voices
        flagged_dir = Path(config.FLAGGED_DIR)
        if flagged_dir.exists():
            flagged_hits = 0
            for npy_path in flagged_dir.glob("*.npy"):
                try:
                    flagged_emb = np.load(npy_path)
                    if flagged_emb.ndim == 1 and flagged_emb.shape[0] == 192:
                        # L2-normalise if needed
                        flagged_norm = np.linalg.norm(flagged_emb)
                        if flagged_norm > 0:
                            flagged_emb = flagged_emb / flagged_norm

                        flagged_cosine = float(np.dot(probe_emb, flagged_emb))
                        if flagged_cosine >= config.SPEAKER_MATCH_THRESHOLD:
                            flagged_hits += 1
                except Exception as e:
                    logger.debug(f"verify_speaker: error loading flagged {npy_path.name}: {e}")
                    continue

            result.flagged_voice_hits = flagged_hits
            if flagged_hits > 0:
                logger.info(f"  Flagged voice hits: {flagged_hits}")

        return result

    except Exception as e:
        logger.error(f"verify_speaker({wav_path}): {type(e).__name__}: {e}")
        return SpeakerSignal(verdict="unknown")


# ===================================================================
# add_flagged_voice(session_id, wav_path) — save probe embedding
# ===================================================================

def add_flagged_voice(session_id: str, wav_path: str) -> None:
    """
    Save probe embedding to flagged-voice cohort.

    Embeds the audio and stores its mean embedding centroid to
    data/flagged/{session_id}.npy for future replay/match detection.

    Args:
        session_id: Unique session identifier (used as filename)
        wav_path: Path to audio file to embed

    Returns:
        None (saves directly to data/flagged/{session_id}.npy)

    Raises:
        Never. Logs warnings on error and returns gracefully.
    """
    try:
        # Load and embed
        audio, sr = embed.load_audio(wav_path)

        if len(audio) == 0:
            logger.warning(f"add_flagged_voice({session_id}): failed to load audio")
            return

        segments = embed.vad_segments(audio, sr)
        try:
            embeddings = embed.embed_chunks(audio, sr, segments)
        except Exception as e:
            logger.error(f"add_flagged_voice: embed_chunks failed: {e}")
            return

        if not embeddings:
            logger.warning(f"add_flagged_voice: no embeddings extracted")
            return

        # Compute centroid
        centroid = np.mean(embeddings, axis=0).astype(np.float32)

        # Ensure output directory exists
        flagged_dir = Path(config.FLAGGED_DIR)
        flagged_dir.mkdir(parents=True, exist_ok=True)

        # Save centroid
        flagged_path = flagged_dir / f"{session_id}.npy"
        np.save(flagged_path, centroid)

        logger.info(f"add_flagged_voice({session_id}): saved to {flagged_path}")

    except Exception as e:
        logger.error(f"add_flagged_voice({session_id}, {wav_path}): {type(e).__name__}: {e}")


# ===================================================================
# __main__ smoke test
# ===================================================================

if __name__ == "__main__":
    """
    Smoke test: verify_speaker from command line.

    Usage:
        python -m audio_ml.verify <wav_path>

    Prints: verdict, raw_cosine, norm_score, best_match_name,
            condition_used, flagged_voice_hits
    """
    import sys

    # Configure logging for test
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s"
    )

    print("\n" + "=" * 70)
    print("audio_ml.verify smoke test")
    print("=" * 70)

    if len(sys.argv) < 2:
        print("\nUsage: python -m audio_ml.verify <wav_path>")
        print("\nExample:")
        print("  python -m audio_ml.verify data/uploads/call_001.wav")
        sys.exit(1)

    wav_path = sys.argv[1]

    print(f"\nVerifying: {wav_path}\n")

    # Verify speaker
    signal = verify_speaker(wav_path)

    # Print results
    print("-" * 70)
    print(f"verdict:              {signal.verdict}")
    print(f"raw_cosine:           {signal.raw_cosine:.4f}")
    print(f"norm_score:           {signal.norm_score:.4f}")
    print(f"best_match_name:      {signal.best_match_name}")
    print(f"condition_used:       {signal.condition_used}")
    print(f"flagged_voice_hits:   {signal.flagged_voice_hits}")
    print("-" * 70)
    print()

    sys.exit(0)
