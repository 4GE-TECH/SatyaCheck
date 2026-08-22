"""The ASR adapter — the module Block 2 turns on.

`asr.py` was dead code until the real NLP branch was switched on, and it had no tests.
Two things are covered here, and they need different treatment:

**Pure logic** — waveform handling and the reported-language rule — runs everywhere.

**Real-decoder behaviour** — skipped unless `models/faster-whisper-small` is present, so
the suite still passes on a machine that has not downloaded 461MB. Audio is generated in
process with `numpy` + `wave`, deliberately not `ffmpeg`: the degenerate cases that matter
here are silence and noise, and synthesising them directly keeps the tests dependency-free.

`PLAN.md` §7 exists because Whisper `small` emits fluent phantom sentences on near-silence
— on exactly the audio the acoustic gate was built to catch. That claim had never been
tested against a real decoder.
"""

from __future__ import annotations

import math
import wave

import numpy as np
import pytest

from nlp_rag import asr, thresholds

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

requires_model = pytest.mark.skipif(
    not asr.MODEL_DIR.exists(),
    reason=f"faster-whisper not downloaded at {asr.MODEL_DIR}",
)


# --- audio helpers -----------------------------------------------------------

def _write_wav(path, samples: np.ndarray, rate: int = 16000) -> str:
    pcm = np.clip(samples, -1.0, 1.0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((pcm * 32767).astype("<i2").tobytes())
    return str(path)


def silence(seconds: float, rate: int = 16000) -> np.ndarray:
    return np.zeros(int(seconds * rate), dtype=np.float32)


def noise(seconds: float, amplitude: float = 0.02, rate: int = 16000) -> np.ndarray:
    rng = np.random.default_rng(0)
    return (rng.standard_normal(int(seconds * rate)) * amplitude).astype(np.float32)


def tone(seconds: float, hz: float = 440.0, rate: int = 16000) -> np.ndarray:
    t = np.arange(int(seconds * rate), dtype=np.float32) / rate
    return (0.3 * np.sin(2 * math.pi * hz * t)).astype(np.float32)


# --- prepare_audio: C calls `transcribe(wav_path or waveform)` ---------------

def test_a_path_is_passed_through_as_a_path(tmp_path):
    path = _write_wav(tmp_path / "a.wav", tone(0.5))
    assert asr.prepare_audio(path) == path


def test_a_waveform_becomes_a_float32_array():
    prepared = asr.prepare_audio([0.0, 0.5, -0.5])
    assert isinstance(prepared, np.ndarray) and prepared.dtype == np.float32


def test_a_numpy_waveform_is_accepted():
    prepared = asr.prepare_audio(np.array([0.1, 0.2], dtype=np.float64))
    assert prepared.dtype == np.float32


def test_a_missing_file_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        asr.prepare_audio(tmp_path / "nope.wav")


def test_an_empty_waveform_is_rejected():
    """C computes `wav_path or waveform`, so an empty list is a live input."""
    with pytest.raises(ValueError):
        asr.prepare_audio([])


def test_an_unsupported_input_is_rejected():
    with pytest.raises(ValueError):
        asr.prepare_audio(object())


# --- the reported language ---------------------------------------------------
# C reads `detected_language` to choose vernacular warning copy, so a wrong label puts a
# Hindi warning on an English call.

class _Info:
    def __init__(self, language, probability):
        self.language = language
        self.language_probability = probability


def test_a_confident_detection_is_reported():
    assert asr._reported_language(_Info("en", 1.0), None) == "en"


def test_an_explicit_request_overrides_detection():
    assert asr._reported_language(_Info("en", 1.0), "hi") == "hi"


def test_a_weak_detection_falls_back_to_the_configured_primary():
    """Code-switched Hinglish detects around p=0.55 — genuinely uncertain, and exactly
    where the deployment's primary language is the better label."""
    weak = thresholds.ASR_MIN_LANGUAGE_PROB - 0.05
    assert asr._reported_language(_Info("en", weak), None) == asr.DEFAULT_LANGUAGE


def test_a_detection_exactly_at_the_threshold_is_trusted():
    at = thresholds.ASR_MIN_LANGUAGE_PROB
    assert asr._reported_language(_Info("ta", at), None) == "ta"


def test_a_missing_detection_degrades_to_the_configured_primary():
    assert asr._reported_language(_Info(None, 0.0), None) == asr.DEFAULT_LANGUAGE


# --- degradation without a model ---------------------------------------------

def test_a_missing_file_returns_empty_rather_than_raising(tmp_path):
    assert asr.transcribe_file(tmp_path / "absent.wav").text == ""


def test_an_empty_waveform_returns_empty_rather_than_raising():
    assert asr.transcribe_file([]).text == ""


# --- against the real decoder -------------------------------------------------

@requires_model
def test_the_model_loads():
    assert asr._load_model() is not None


@requires_model
@pytest.mark.parametrize(
    "signal", [silence(6.0), noise(6.0), tone(6.0)], ids=["silence", "noise", "tone"]
)
def test_non_speech_is_gated_rather_than_hallucinated(tmp_path, signal):
    """The §7 guard, against a real decoder instead of an assertion.

    Whisper `small` invents fluent sentences on near-silence. If any survives to
    `analyze_script`, a confident script_risk is computed from a phantom transcript.
    """
    path = _write_wav(tmp_path / "x.wav", signal)
    assert asr.transcribe_file(path).text == ""


@requires_model
def test_audio_below_the_speech_floor_is_gated(tmp_path):
    path = _write_wav(tmp_path / "short.wav", tone(0.4))
    assert asr.transcribe_file(path).text == ""


@requires_model
def test_a_gated_transcript_reports_no_language(tmp_path):
    """`unknown` rather than the configured primary: nothing was detected at all, and
    claiming a language for silence would be inventing evidence."""
    path = _write_wav(tmp_path / "s.wav", silence(6.0))
    assert asr.transcribe_file(path).detected_language == "unknown"


@requires_model
def test_a_waveform_and_its_file_transcribe_identically(tmp_path):
    """C passes whichever it has; the two paths must not diverge."""
    signal = tone(3.0)
    path = _write_wav(tmp_path / "t.wav", signal)
    assert asr.transcribe_file(path).text == asr.transcribe_file(signal).text
