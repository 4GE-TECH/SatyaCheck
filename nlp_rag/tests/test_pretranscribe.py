"""Pre-transcribed demo clips — the latency mitigation the risk register names.

`PLAN.md` §8: faster-whisper pads every input to a 30-second mel window, and §8.1 measured
the cost as ~1.2s fixed plus ~0.1s per second of speech. On stage that is the difference
between a meter that moves and one the audience watches spin.

Keyed on the SHA-256 of the audio, not its path: a clip renamed or moved between
rehearsal and demo must still hit, and a clip that was silently re-recorded must miss.
"""

from __future__ import annotations

import json
import math
import wave

import numpy as np
import pytest

from nlp_rag import api, asr, pretranscribe


def _wav(path, seconds=1.0, hz=440.0, rate=16000):
    t = np.arange(int(seconds * rate), dtype=np.float32) / rate
    pcm = (0.3 * np.sin(2 * math.pi * hz * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return str(path)


@pytest.fixture
def cache(tmp_path):
    clip = _wav(tmp_path / "demo.wav")
    path = tmp_path / "pretranscribed.json"
    pretranscribe.write(
        {pretranscribe.audio_hash(clip): {
            "text": "turant paise bhejo", "language": "hi", "confidence": 0.91}},
        path,
    )
    return clip, path


# --- lookup ------------------------------------------------------------------

def test_a_known_clip_is_returned_from_cache(cache):
    clip, path = cache
    assert pretranscribe.lookup(clip, path).text == "turant paise bhejo"


def test_the_cached_language_and_confidence_survive(cache):
    clip, path = cache
    result = pretranscribe.lookup(clip, path)
    assert result.detected_language == "hi" and result.confidence == pytest.approx(0.91)


def test_an_unknown_clip_misses(tmp_path, cache):
    _, path = cache
    other = _wav(tmp_path / "other.wav", hz=880.0)
    assert pretranscribe.lookup(other, path) is None


def test_a_renamed_clip_still_hits(tmp_path, cache):
    """Keyed on content. Renaming between rehearsal and demo must not cost the cache."""
    clip, path = cache
    renamed = tmp_path / "renamed.wav"
    renamed.write_bytes(open(clip, "rb").read())
    assert pretranscribe.lookup(renamed, path) is not None


def test_a_re_recorded_clip_misses(tmp_path, cache):
    """The other half of content-keying: same name, different audio, no stale hit."""
    clip, path = cache
    _wav(clip, hz=1000.0)
    assert pretranscribe.lookup(clip, path) is None


# --- degradation --------------------------------------------------------------

def test_a_missing_cache_file_is_a_miss_not_a_crash(tmp_path):
    assert pretranscribe.lookup(_wav(tmp_path / "a.wav"), tmp_path / "absent.json") is None


def test_a_corrupt_cache_is_a_miss_not_a_crash(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert pretranscribe.lookup(_wav(tmp_path / "a.wav"), bad) is None


def test_a_waveform_cannot_be_looked_up(cache):
    """C calls transcribe(wav_path or waveform). A raw buffer has no file to hash."""
    _, path = cache
    assert pretranscribe.lookup([0.1, 0.2, 0.3], path) is None


def test_a_missing_audio_file_is_a_miss_not_a_crash(tmp_path, cache):
    _, path = cache
    assert pretranscribe.lookup(tmp_path / "nope.wav", path) is None


# --- the point of the whole thing --------------------------------------------

def test_a_cached_clip_never_reaches_the_decoder(cache, monkeypatch):
    """If the model still runs, the cache has bought nothing."""
    clip, path = cache
    monkeypatch.setattr(pretranscribe, "DEFAULT_CACHE", path)

    def explode(*a, **k):
        raise AssertionError("decoder was invoked for a pre-transcribed clip")

    monkeypatch.setattr(api, "transcribe_file", explode)
    assert api.transcribe(clip).text == "turant paise bhejo"


def test_an_uncached_clip_still_reaches_the_decoder(tmp_path, cache, monkeypatch):
    _, path = cache
    monkeypatch.setattr(pretranscribe, "DEFAULT_CACHE", path)
    called = {}

    def fake(source, language=None):
        called["yes"] = True
        from contracts import TranscriptResult
        return TranscriptResult.empty()

    monkeypatch.setattr(api, "transcribe_file", fake)
    api.transcribe(_wav(tmp_path / "new.wav", hz=1200.0))
    assert called.get("yes")


# --- build --------------------------------------------------------------------

def test_build_indexes_every_clip_in_a_directory(tmp_path, monkeypatch):
    clips = tmp_path / "clips"; clips.mkdir()
    for i, hz in enumerate((440.0, 880.0)):
        _wav(clips / f"c{i}.wav", hz=hz)

    from contracts import TranscriptResult
    monkeypatch.setattr(
        asr, "transcribe_file",
        lambda s, language=None: TranscriptResult(
            text="hello", segments=[], detected_language="en", confidence=0.9),
    )
    out = tmp_path / "out.json"
    written = pretranscribe.build(clips, out)
    assert len(written) == 2
    assert len(json.loads(out.read_text(encoding="utf-8"))) == 2


def test_build_skips_clips_the_decoder_could_not_read(tmp_path, monkeypatch):
    """An unreadable clip must not land in the cache as an empty transcript — that would
    pin a silent result for a clip that merely failed once."""
    clips = tmp_path / "clips"; clips.mkdir()
    _wav(clips / "a.wav")

    from contracts import TranscriptResult
    monkeypatch.setattr(asr, "transcribe_file", lambda s, language=None: TranscriptResult.empty())
    assert pretranscribe.build(clips, tmp_path / "out.json") == {}
