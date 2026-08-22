"""faster-whisper adapter, plus the transcription entry point.

The gate logic lives in `nlp_rag.gate` and is pure. This module is the thin shell around
the model, and is the second of the two files that change when A's H0 downloads land.

Decoding settings are not incidental (see `nlp_rag/PLAN.md` §8):

- `condition_on_previous_text=False` — the single flag that kills Whisper's looped
  repetition hallucination on near-silence.
- `beam_size=1`, `compute_type="int8"`, `model="small"` — `medium` is not viable on a
  laptop CPU, and the demo laptop is running four other models.
- The caller batches ~9s before calling: faster-whisper pads every input to a 30-second
  mel window, so a 3-second chunk costs roughly what 30 seconds costs.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from contracts import TranscriptResult, TranscriptSegment
from nlp_rag.gate import evaluate_transcript

logger = logging.getLogger(__name__)

#: `CLAUDE.md` rule 4 — everything loads from ./models/. Paths and decoding settings
#: come from C's `config.py`; the fallbacks apply only before it is importable.
try:  # pragma: no cover - depends on whether C has shipped config.py yet
    import config as _config
except ImportError:  # pragma: no cover
    _config = None

_MODELS_DIR = getattr(_config, "MODELS_DIR", None) or (
    Path(__file__).resolve().parent.parent / "models"
)
MODEL_SIZE: str = getattr(_config, "WHISPER_MODEL_SIZE", "small")
COMPUTE_TYPE: str = getattr(_config, "WHISPER_COMPUTE_TYPE", "int8")
DEFAULT_LANGUAGE: str | None = getattr(_config, "WHISPER_LANGUAGE", None)

MODEL_DIR = Path(_MODELS_DIR) / f"faster-whisper-{MODEL_SIZE}"

_model = None
_load_attempted = False


def _load_model():
    """Load once, cache, and never retry a failure — this sits in the request path."""
    global _model, _load_attempted
    if _load_attempted:
        return _model
    _load_attempted = True

    if not MODEL_DIR.exists():
        logger.warning("faster-whisper not found at %s; transcription disabled", MODEL_DIR)
        return None
    try:
        from faster_whisper import WhisperModel  # deferred: heavy import

        _model = WhisperModel(str(MODEL_DIR), device="cpu", compute_type=COMPUTE_TYPE)
    except Exception as exc:  # noqa: BLE001 - any load failure degrades identically
        logger.warning("faster-whisper failed to load (%s); transcription disabled", exc)
        _model = None
    return _model


def prepare_audio(source: str | Path | Sequence[float]):
    """Normalise C's `wav_path or waveform` into something faster-whisper accepts.

    `server/orchestrator.py` calls `transcribe(wav_path or waveform)`, so the input is
    either a path or a raw 16 kHz mono waveform. faster-whisper takes a float32 numpy
    array directly, so a waveform needs no temporary file.

    Returns a `str` path or a float32 array; raises ValueError if neither is usable.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.is_file():
            raise ValueError(f"audio file not found: {path}")
        return str(path)

    if isinstance(source, np.ndarray):
        samples = source.astype(np.float32, copy=False)
    elif isinstance(source, Sequence):
        samples = np.asarray(source, dtype=np.float32)
    else:
        raise ValueError(f"unsupported audio input: {type(source).__name__}")

    if samples.size == 0:
        raise ValueError("empty waveform")
    return samples


def transcribe_file(
    audio_path: str | Path | Sequence[float], language: str | None = None
) -> TranscriptResult:
    """Transcribe a file path or a raw waveform, gated. Never raises."""
    try:
        try:
            source = prepare_audio(audio_path)
        except ValueError as exc:
            logger.warning("unusable audio input (%s)", exc)
            return TranscriptResult.empty()

        model = _load_model()
        if model is None:
            return TranscriptResult.empty()

        segments, info = model.transcribe(
            source,
            language=language or DEFAULT_LANGUAGE,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        segments = list(segments)
        text = " ".join(s.text.strip() for s in segments).strip()

        no_speech = max((getattr(s, "no_speech_prob", 0.0) for s in segments), default=0.0)
        logprobs = [getattr(s, "avg_logprob", 0.0) for s in segments]
        avg_logprob = sum(logprobs) / len(logprobs) if logprobs else 0.0

        verdict = evaluate_transcript(text, no_speech, avg_logprob)
        if not verdict.ok:
            logger.info("transcript gated: %s", verdict.reason)
            return TranscriptResult.empty()

        return TranscriptResult(
            text=text,
            segments=[
                TranscriptSegment(
                    start_s=s.start, end_s=s.end, text=s.text.strip(),
                    language=getattr(info, "language", None),
                )
                for s in segments
            ],
            detected_language=getattr(info, "language", "unknown") or "unknown",
            confidence=verdict.confidence,
        )
    except Exception as exc:  # noqa: BLE001 - rule 5: degrade, never raise into C
        logger.warning("transcription failed (%s)", exc)
        return TranscriptResult.empty()


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "data/demo_clips/sample.wav"
    result = transcribe_file(target)
    print(f"language={result.detected_language} confidence={result.confidence:.2f}")
    print(f"text: {result.text or '(empty — model absent or transcript gated)'}")
