"""
audio_ml/spoof.py — Synthetic voice detection via anti-spoof model.

Pure pretrained inference. No training, no network calls.
All errors caught internally; public functions return valid defaults.
"""

from __future__ import annotations

import logging
import numpy as np
from pathlib import Path
from typing import List, Tuple

from . import embed
from .spoof_aggregate import aggregate
from audio_ml.signals import SpoofSignal

logger = logging.getLogger(__name__)

# Model paths
MODELS_DIR = Path(__file__).parent.parent / "models"
ANTISPOOF_MODEL_PATH = MODELS_DIR / "antispoof"

# Audio constants from embed.py
TARGET_SR = 16000
CHUNK_LENGTH_S = 3.0
CHUNK_OVERLAP_S = 1.0


def _load_antispoof_model():
    """
    Load pretrained anti-spoof model.

    Placeholder for Block 3 integration. Currently unavailable on this machine.
    Returns None; detect_spoof() will return neutral default (score=0.5).

    Returns:
        None (model not yet available)
    """
    logger.warning(
        "Anti-spoof model unavailable on this machine. "
        "detect_spoof() will return neutral score (0.5) with verdict='uncertain'. "
        "Real model checkpoint will be integrated in Block 3."
    )
    return None


# Global model cache
_antispoof_model_cache = None


def detect_spoof(wav_path: str) -> SpoofSignal:
    """
    Detect synthetic speech in audio file.

    Placeholder implementation: returns neutral default until anti-spoof
    model is available (Block 3). Chunking and aggregation logic are in place
    for easy integration of the real model.

    Args:
        wav_path: Path to audio file (wav, mp3, m4a, etc.)

    Returns:
        SpoofSignal(score=0.5, verdict="uncertain") — neutral default.
        Never raises.

    Behavior:
        - Anti-spoof model unavailable on this machine.
        - Returns neutral default with clear warning log.
        - Structure preserved for real model integration in Block 3.
    """
    try:
        # Load audio (validates file exists and is readable)
        audio, sr = embed.load_audio(wav_path)

        if len(audio) == 0:
            logger.warning(f"detect_spoof({wav_path}): audio is empty")
            return SpoofSignal(score=0.5, verdict="uncertain")

        # BLOCK 3: Real model will be integrated here.
        # For now, return neutral default.
        logger.info(
            f"detect_spoof({wav_path}): anti-spoof model unavailable, "
            "returning neutral verdict"
        )
        return SpoofSignal(score=0.5, verdict="uncertain")

        # ===== BLOCK 3: Replace above with real model =====
        # Load model (cached)
        # global _antispoof_model_cache
        # if _antispoof_model_cache is None:
        #     _antispoof_model_cache = _load_antispoof_model()
        # model = _antispoof_model_cache
        # if model is None:
        #     return SpoofSignal(score=0.5, verdict="uncertain")
        #
        # # Extract chunks with 3s length and 1s overlap
        # chunk_samples = int(CHUNK_LENGTH_S * sr)
        # overlap_samples = int(CHUNK_OVERLAP_S * sr)
        # stride_samples = chunk_samples - overlap_samples
        # chunk_scores = []
        # chunk_spans = []
        # pos = 0
        # while pos + chunk_samples <= len(audio):
        #     chunk = audio[pos : pos + chunk_samples]
        #     start_s = pos / sr
        #     end_s = (pos + chunk_samples) / sr
        #     score = _score_chunk(model, chunk, sr)
        #     chunk_scores.append(score)
        #     chunk_spans.append((start_s, end_s))
        #     pos += stride_samples
        # if not chunk_scores:
        #     return SpoofSignal(score=0.5, verdict="uncertain")
        # result = aggregate(chunk_scores, chunk_spans)
        # logger.info(f"detect_spoof({wav_path}): {len(chunk_scores)} chunk(s), verdict={result.verdict}")
        # return result
        # ===== END BLOCK 3 =====

    except Exception as e:
        logger.error(f"detect_spoof({wav_path}): {type(e).__name__}: {e}")
        return SpoofSignal(score=0.5, verdict="uncertain")


if __name__ == "__main__":
    """
    Smoke test: verify detect_spoof returns valid SpoofSignal.
    """
    import sys

    # Configure logging for test
    logging.basicConfig(
        level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s"
    )

    print("\n" + "=" * 60)
    print("audio_ml.spoof smoke test")
    print("=" * 60)

    # Test with nonexistent file (should return neutral default)
    print("\n[1] Testing error handling (nonexistent file)...")
    result = detect_spoof("/nonexistent/file.wav")
    assert isinstance(result, SpoofSignal), f"Result is not SpoofSignal: {type(result)}"
    assert result.score == 0.5, f"Score should be 0.5, got {result.score}"
    assert result.verdict == "uncertain", f"Verdict should be 'uncertain', got {result.verdict}"
    print(f"    ✓ Graceful fallback to neutral SpoofSignal")

    # Test return type validation
    print("\n[2] Testing return type...")
    assert hasattr(result, "score"), "Missing 'score' field"
    assert hasattr(result, "verdict"), "Missing 'verdict' field"
    assert hasattr(result, "peak"), "Missing 'peak' field"
    assert hasattr(result, "max_synth_run_s"), "Missing 'max_synth_run_s' field"
    assert hasattr(result, "timeline"), "Missing 'timeline' field"
    assert hasattr(result, "n_chunks"), "Missing 'n_chunks' field"
    print(f"    ✓ SpoofSignal has all required fields")
    print(f"      verdict:        {result.verdict}")
    print(f"      score:          {result.score:.4f}")
    print(f"      peak:           {result.peak:.4f}")
    print(f"      max_synth_run:  {result.max_synth_run_s:.2f}s")
    print(f"      n_chunks:       {result.n_chunks}")

    print("\n" + "=" * 60)
    print("✓ All smoke tests passed!")
    print("=" * 60)
    sys.exit(0)
