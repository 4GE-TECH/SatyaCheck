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
from audio_ml.signals import SpeakerSignal
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

        # L2-normalise the cohort rows.
        #
        # The dot products below ARE cosine similarities, but only if both sides are
        # unit length. data/cohort/cohort.npy ships with row norms of 183–263 — the
        # embeddings were stacked before normalisation — so without this the cohort
        # statistics come out ~200x too large, the z-score collapses toward zero, and
        # sigmoid(0) = 0.5. That is below SPEAKER_UNKNOWN_FLOOR, so *a genuine
        # enrolled speaker returns "unknown"*. Not an error: a legitimate verdict
        # meaning "nobody enrolled is close", which is indistinguishable from working.
        #
        # A cohort is a set of directions. Normalising rows changes no speaker's
        # identity, so the score must not depend on their magnitude — that invariance
        # is what audio_ml/tests/test_snorm.py pins.
        cohort = np.asarray(cohort, dtype=np.float64)
        if not np.all(np.isfinite(cohort)):
            logger.warning("snorm: cohort contains non-finite values, returning raw")
            return raw

        row_norms = np.linalg.norm(cohort, axis=1, keepdims=True)
        usable = row_norms.squeeze(axis=1) > 1e-9
        if usable.sum() < 5:
            logger.warning(
                f"snorm: only {int(usable.sum())} usable cohort rows, returning raw"
            )
            return raw
        cohort = cohort[usable] / row_norms[usable]

        # Compute cosine similarities: probe vs cohort, enrolled vs cohort
        # Both sides are now L2-normalised, so dot == cosine.
        scores_probe = np.dot(cohort, probe_emb)      # (N,)
        scores_enrolled = np.dot(cohort, enrolled_emb)  # (N,)

        mean_probe = np.mean(scores_probe)
        std_probe = np.std(scores_probe)
        mean_enrolled = np.mean(scores_enrolled)
        std_enrolled = np.std(scores_enrolled)

        # Guard against zero std (all cohort members identical).
        # `not (std > 1e-10)` rather than `std < 1e-10` so a NaN std — which
        # compares False against everything — falls back instead of propagating.
        if not (std_probe > 1e-10) or not (std_enrolled > 1e-10):
            logger.debug("snorm: degenerate cohort std, returning raw")
            return raw

        # Apply s-norm formula
        z_score = 0.5 * (
            (raw - mean_enrolled) / std_enrolled +
            (raw - mean_probe) / std_probe
        )

        # Shape the z-score into [0, 1] without saturating.
        #
        # A plain sigmoid does not work here. Against a 40-speaker cohort these
        # z-scores land in roughly [3, 18], and sigmoid(5) is already 0.9933 — so
        # every probe reported the *same* norm_score to four decimal places,
        # genuine speaker and voice clone alike. Clamping at ±5 first made it
        # certain. Dividing by a temperature spreads the real operating range
        # across the output instead of pinning it to the ceiling.
        z_score = float(np.clip(z_score, -config.SNORM_Z_CLAMP, config.SNORM_Z_CLAMP))
        norm = 1.0 / (1.0 + np.exp(-z_score / config.SNORM_TEMPERATURE))

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
        best_condition = "wb"

        for idx, person in enumerate(enrolled_persons):
            person_id = person["person_id"]
            voiceprint = enroll.load_voiceprint(person_id)

            if not voiceprint:
                logger.warning(f"  Could not load voiceprint for {person_id}")
                continue

            # Score against every stored condition and keep the best.
            #
            # This replaces a wideband-only comparison. The earlier ablation that chose
            # wideband-only was run on wideband probes, where it wins by construction;
            # it never saw call audio. Measured on `friend_test.wav` pushed through the
            # codecs a real call actually uses, wideband-only rejects the enrolled
            # speaker outright:
            #
            #   probe                     vs wb    vs nb8k_sim   wb-only verdict
            #   genuine, clean            0.9464     0.7130      match
            #   genuine, mu-law (VoIP)    0.7545     0.9326      MISMATCH  <- false
            #   genuine, AMR-NB (cell)    0.7598     0.9155      MISMATCH  <- false
            #   clone,   AMR-NB (cell)    0.6517     0.8246      mismatch
            #
            # A genuine caller on a mobile network scored 0.7598 against their own
            # voiceprint — below the 0.85 threshold, so the branch accused them. That is
            # the exact failure CLAUDE.md's condition-matched enrollment rule exists to
            # prevent: comparing a phone-quality probe against a studio-quality reference
            # measures the channel, not the speaker.
            #
            # Taking the max over conditions needs no condition detection, which matters
            # because `embed.detect_condition` cannot be trusted here — at sr=16000 its
            # 8–16 kHz band is empty by Nyquist, so its headline test is dead code, and it
            # reads only the first 2048 samples (usually leading silence).
            #
            # The max rule restores both call cases to `match` and moves no other verdict:
            # the clone stays at 0.8246 (mismatch) and impostors stay where they were.
            # Margins on call audio are real but tighter than on clean audio — genuine
            # 0.9155 vs clone 0.8246, with the threshold at 0.85 between them.
            candidates = []
            for key in ("wb", "nb8k_real", "nb8k_sim"):
                centroid = voiceprint.get(key)
                if centroid is None:
                    continue
                centroid = np.asarray(centroid, dtype=np.float32)
                if centroid.size == 0:
                    continue
                centroid_norm = np.linalg.norm(centroid)
                if centroid_norm <= 0:
                    continue
                candidates.append((float(np.dot(probe_emb, centroid / centroid_norm)), key))

            if not candidates:
                logger.warning(f"  No usable centroid for {person_id}")
                continue

            raw_cosine, centroid_type = max(candidates)
            logger.debug(f"  {person['name']}: raw_cosine={raw_cosine:.4f} ({centroid_type})")

            if raw_cosine > best_raw:
                best_raw = raw_cosine
                best_match_idx = idx
                best_condition = centroid_type

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

        # Which stored condition actually produced the match. Reported so the caller can
        # tell a clean-channel verification from one made against the codec-degraded
        # reference — the same cosine means less on narrowband, where the margin between
        # a genuine speaker and a clone is roughly 0.09 rather than 0.18.
        result.condition_used = best_condition

        # Step 4: S-normalise the best raw score
        best_voiceprint = enroll.load_voiceprint(result.best_match_id)
        # S-normalise against the centroid that won, not always the wideband one, or the
        # z-score describes a comparison that was never made.
        best_enrolled = np.asarray(best_voiceprint[best_condition], dtype=np.float32)

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

        # Step 5: Determine verdict from thresholds, on the RAW COSINE.
        #
        # Not on norm_score, and this is measured rather than assumed. Against the
        # eval clips with the real ECAPA checkpoint, raw cosine separates a voice
        # clone from every genuine probe and the s-norm z-score does not:
        #
        #   probe        vs enrolled  raw      z       truth
        #   friend       friend       0.9684   17.47   genuine
        #   friend_test  friend       0.9241   16.91   genuine
        #   me_test2     me           0.8287   10.23   genuine
        #   cloned_scam  friend       0.7537   12.39   CLONE
        #
        # The clone's z (12.39) lands *inside* the genuine band [10.23, 17.47], so
        # no z threshold can accept me_test2 and reject the clone. On raw cosine the
        # clone is the lowest of the four and 0.85 cuts cleanly above it. These are
        # also the cut points A calibrated (their measurements: 0.9464 genuine,
        # 0.7631 clone), so this is A's intended behaviour restored, not new tuning.
        #
        # `norm_score` is still computed, reported and stored — it is the calibrated
        # quantity for anyone fusing scores directly. What fusion actually consumes
        # from this branch is the discrete risk that
        # `server/audio_adapter.to_speaker_result` derives from `verdict`, so no
        # un-normalised score reaches the weighted sum.
        #
        # Worth knowing before trusting this branch: a good clone can defeat ECAPA
        # outright. cloned_scam scores 0.7537 here, above the 0.60 floor, so it is
        # `mismatch` rather than `unknown` — caught, but only just. Intent is what
        # actually flags that clip (script risk 0.67 with a cited playbook).
        if best_raw >= config.SPEAKER_MATCH_THRESHOLD:
            result.verdict = "match"
        elif best_raw >= config.SPEAKER_UNKNOWN_FLOOR:
            result.verdict = "mismatch"
        else:
            result.verdict = "unknown"

        logger.info(
            f"  Verdict: {result.verdict} "
            f"(raw={best_raw:.4f} vs threshold {config.SPEAKER_MATCH_THRESHOLD}, "
            f"norm={norm_score:.4f} reported)"
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
