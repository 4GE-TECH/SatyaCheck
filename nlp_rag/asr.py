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
from typing import Any

import numpy as np

from contracts import TranscriptResult, TranscriptSegment
from nlp_rag import thresholds
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


def _reported_language(info, requested: str | None) -> str:
    """The label C sees in `TranscriptResult.detected_language`.

    An explicit request wins. Otherwise Whisper's own detection, unless it is not
    confident enough to be worth trusting — code-switched Hinglish lands around p=0.55 —
    in which case `config.WHISPER_LANGUAGE` is reported as the deployment's prior. That is
    the "primary language" role the config comment describes, applied to the label rather
    than to decoding, where it does real damage.

    C reads this to pick vernacular warning copy, so a wrong label means a Hindi warning
    on an English call.
    """
    if requested:
        return requested

    detected = getattr(info, "language", None)
    probability = getattr(info, "language_probability", 1.0) or 0.0
    if not detected:
        return DEFAULT_LANGUAGE or "unknown"
    if probability < thresholds.ASR_MIN_LANGUAGE_PROB:
        logger.info(
            "language detection weak (%s p=%.2f); reporting configured primary %s",
            detected, probability, DEFAULT_LANGUAGE,
        )
        return DEFAULT_LANGUAGE or detected
    return detected



def _aggregate_no_speech(segments: Sequence[Any]) -> float:
    """Duration-weighted mean of Whisper's per-segment `no_speech_prob`.

    Weighted mean, not `max()`. Whisper reports this per segment, and a real call is
    mostly pauses, breaths and room tone between utterances — so one quiet segment
    anywhere set the score for the whole clip. Two eval clips of clearly audible
    speech were gated away entirely at 0.642 against a 0.60 threshold, returning an
    empty transcript and abstaining the intent branch on audio Whisper had in fact
    transcribed correctly.

    `max()` is also *anti-monotone in call length*: every additional segment can only
    push the score up, so a long call is gated more readily than a short one saying
    exactly the same thing. Weighting by duration asks the question the gate actually
    means — "what fraction of this audio is not speech" — and stays stable as calls
    grow.

    Never raises: returns 0.0 (treat as speech) if there is nothing usable to weigh,
    because the text gate downstream already rejects an empty transcript on its own.
    """
    total = 0.0
    weighted = 0.0
    for segment in segments:
        probability = float(getattr(segment, "no_speech_prob", 0.0) or 0.0)
        duration = float(getattr(segment, "end", 0.0) or 0.0) - float(
            getattr(segment, "start", 0.0) or 0.0
        )
        if duration <= 0.0:
            # Zero-length or malformed segment: keep its opinion, weight it minimally.
            duration = 1e-3
        total += duration
        weighted += probability * duration

    if total <= 0.0:
        return 0.0
    return max(0.0, min(1.0, weighted / total))


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

        # `language=None` means auto-detect. Do NOT pass DEFAULT_LANGUAGE here.
        #
        # `config.WHISPER_LANGUAGE = "hi"` is commented "Primary language; Whisper
        # auto-detects Hinglish", but passing the parameter is exactly what *prevents*
        # auto-detection -- it forces the decoder into that language. Measured on real
        # audio, forcing "hi" on English speech is:
        #
        #   ~10x slower       1.65-1.82x realtime vs 0.16-0.18x
        #   nondeterministic  identical input, identical settings, different output
        #   lower quality     one run produced Devanagari and CJK characters as a
        #                     transcript of clean English speech
        #
        # All three are the same cause: a forced mismatched language fails Whisper's
        # logprob and compression-ratio checks, which triggers temperature fallback --
        # repeated decodes at rising temperature, and temperature > 0 is sampling.
        #
        # Auto-detection is better for Hindi too, not a trade: on code-switched Hinglish
        # it still returns "hi" and was faster there as well (6.4s vs 16.6s).
        #
        # An explicit `language=` from the caller is still honoured; C never passes one.
        segments, info = model.transcribe(
            source,
            language=language,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        segments = list(segments)
        text = " ".join(s.text.strip() for s in segments).strip()

        no_speech = _aggregate_no_speech(segments)
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
            detected_language=_reported_language(info, language),
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
