"""Item 3: one rolling buffer per session, emitting overlapping windows with context.

Today `ws_router.SessionState` appends each chunk and scores the trailing 9 s once per
chunk, so how often a call is re-scored depends on how big the client's chunks happen to
be, and every chunk costs two ffmpeg passes. `SessionBuffer` decouples the two:
frames of any size go in, and a window comes out every `STREAM_HOP_S` of audio, each
holding the trailing `STREAM_CONTEXT_S` (less at the start of a call).

Windows end on hop boundaries, so a 3 s frame yields one window and leaves 1 s waiting
for the next frame; a 30 s upload yields fifteen. `flush()` scores the tail at the end
of a call. `ingest_pcm` builds the quality gate straight from those samples — no ffmpeg.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import numpy as np
import pytest

import config
from contracts import AudioFrame
from server.audio_ingest import ingest_audio, ingest_pcm
from server.pipeline.buffer import SessionBuffer

SR = 16_000


def _signal(seconds: float) -> np.ndarray:
    """A ramp, so every sample's position can be recovered from its value."""
    n = int(seconds * SR)
    return ((np.arange(n) % 30000) - 15000).astype("<i2")


def _frames(samples: np.ndarray, frame_s: float, session_id: str = "s", final: bool = True):
    step = int(frame_s * SR)
    out = []
    for i, start in enumerate(range(0, len(samples), step)):
        chunk = samples[start:start + step]
        out.append(AudioFrame(session_id=session_id, seq=i, t_start_s=start / SR,
                              pcm_s16le=chunk.tobytes(),
                              is_final=final and start + step >= len(samples)))
    return out


def _run(buffer: SessionBuffer, frames):
    windows = []
    for f in frames:
        windows += buffer.push(f)
    return windows


def _buffer(**kw) -> SessionBuffer:
    return SessionBuffer("s", window_s=kw.pop("window_s", 9.0), hop_s=kw.pop("hop_s", 2.0), **kw)


def test_defaults_come_from_config():
    b = SessionBuffer("s")
    assert b.window_s == config.STREAM_CONTEXT_S
    assert b.hop_s == config.STREAM_HOP_S == 2.0


def test_three_second_frames_give_a_window_every_hop():
    windows = _run(_buffer(), _frames(_signal(12.0), 3.0, final=False))
    assert [w.end_s for w in windows] == [2.0, 4.0, 6.0, 8.0, 10.0, 12.0]
    assert [w.start_s for w in windows] == [0.0, 0.0, 0.0, 0.0, 1.0, 3.0]
    assert [w.index for w in windows] == list(range(6))


def test_a_long_frame_yields_every_window_it_spans():
    windows = _run(_buffer(), _frames(_signal(30.0), 30.0, final=False))
    assert len(windows) == 15
    assert windows[-1].start_s == 21.0 and windows[-1].end_s == 30.0


def test_window_contents_are_the_exact_samples():
    source = _signal(12.0)
    for w in _run(_buffer(), _frames(source, 0.5, final=False)):
        expected = source[int(w.start_s * SR):int(w.end_s * SR)].astype(np.float32) / 32768.0
        assert np.array_equal(w.pcm, expected), (w.start_s, w.end_s)


def test_full_windows_overlap_by_window_minus_hop():
    windows = [w for w in _run(_buffer(), _frames(_signal(20.0), 1.0, final=False))
               if w.end_s - w.start_s == 9.0]
    for a, b in zip(windows, windows[1:]):
        assert a.end_s - b.start_s == pytest.approx(7.0)


def test_the_final_frame_flushes_the_tail():
    windows = _run(_buffer(), _frames(_signal(7.0), 3.0, final=True))
    assert [w.end_s for w in windows] == [2.0, 4.0, 6.0, 7.0]
    assert windows[-1].is_final


def test_a_final_frame_on_a_hop_boundary_is_not_scored_twice():
    windows = _run(_buffer(), _frames(_signal(6.0), 3.0, final=True))
    assert [w.end_s for w in windows] == [2.0, 4.0, 6.0]
    assert windows[-1].is_final


def test_flush_without_new_audio_emits_nothing():
    b = _buffer()
    _run(b, _frames(_signal(4.0), 2.0, final=False))
    assert b.flush() == []


def test_memory_is_bounded_to_about_one_window():
    b = _buffer()
    _run(b, _frames(_signal(120.0), 1.0, final=False))
    assert b.retained_samples <= int((9.0 + 2.0) * SR)


def test_window_hash_is_the_hash_of_its_samples():
    w = _run(_buffer(), _frames(_signal(4.0), 4.0, final=False))[0]
    assert w.sha256 == hashlib.sha256(w.pcm.tobytes()).hexdigest()


def test_a_sequence_gap_is_logged_and_scoring_continues(caplog):
    frames = _frames(_signal(8.0), 2.0, final=False)
    del frames[1]
    with caplog.at_level(logging.WARNING, logger="satyacheck.pipeline.buffer"):
        windows = _run(_buffer(), frames)
    assert windows
    assert any("gap" in r.getMessage() for r in caplog.records)


def test_windows_after_a_sequence_gap_keep_real_session_time():
    """A lost frame must not shift later windows earlier, or splice the two sides together.

    Spoof timelines, max_synth_run_s and reason-code citations all read window times;
    a hybrid attack's synthetic span would otherwise be cited at the wrong moment.
    """
    source = _signal(8.0)
    frames = _frames(source, 2.0, final=False)
    del frames[1]                                    # seq 1 (2-4 s) never arrives
    windows = _run(_buffer(window_s=8.0), frames)
    assert [(w.start_s, w.end_s) for w in windows] == [(0.0, 2.0), (4.0, 6.0), (4.0, 8.0)]
    for w in windows:
        expected = source[int(w.start_s * SR):int(w.end_s * SR)].astype(np.float32) / 32768.0
        assert np.array_equal(w.pcm, expected), (w.start_s, w.end_s)


def test_the_tail_before_a_gap_is_still_scored():
    source = _signal(8.0)
    frames = _frames(source, 3.0, final=False)       # 0-3, 3-6, 6-8
    del frames[1]
    windows = _run(_buffer(), frames)
    assert [(w.start_s, w.end_s) for w in windows] == [(0.0, 2.0), (0.0, 3.0), (6.0, 8.0)]


def test_an_out_of_order_frame_is_dropped_and_logged(caplog):
    frames = _frames(_signal(6.0), 2.0, final=False)
    frames[1], frames[2] = frames[2], frames[1]
    b = _buffer()
    with caplog.at_level(logging.WARNING, logger="satyacheck.pipeline.buffer"):
        _run(b, frames)
    assert any("out of order" in r.getMessage() for r in caplog.records)
    assert b.total_s == pytest.approx(4.0)


def test_a_frame_for_another_session_is_ignored_and_logged(caplog):
    b = _buffer()
    stray = _frames(_signal(4.0), 4.0, session_id="other", final=False)
    with caplog.at_level(logging.WARNING, logger="satyacheck.pipeline.buffer"):
        assert _run(b, stray) == []
    assert any("other" in r.getMessage() for r in caplog.records)


def test_the_session_length_cap_stops_scoring_loudly(caplog):
    b = _buffer(max_session_s=6.0)
    with caplog.at_level(logging.WARNING, logger="satyacheck.pipeline.buffer"):
        windows = _run(b, _frames(_signal(12.0), 2.0, final=False))
    assert windows[-1].end_s <= 6.0
    assert sum("STREAM_MAX_SESSION_S" in r.getMessage() for r in caplog.records) == 1


def test_odd_byte_pcm_is_rejected_not_misaligned(caplog):
    b = _buffer()
    bad = AudioFrame(session_id="s", seq=0, t_start_s=0.0, pcm_s16le=b"\x00\x01\x02")
    with caplog.at_level(logging.WARNING, logger="satyacheck.pipeline.buffer"):
        assert b.push(bad) == []
    assert b.total_s == 0.0


# --- ingest_pcm: the quality gate without ffmpeg ------------------------------------

CLIP = config.REPO_ROOT / "data" / "eval_set" / "clips" / "friend_test.wav"


@pytest.mark.skipif(not CLIP.is_file(), reason="needs data/eval_set/clips/")
def test_ingest_pcm_matches_ingest_audio_on_the_same_samples():
    via_file = ingest_audio(audio_path=str(CLIP))
    samples = np.asarray(via_file.waveform, dtype=np.float32)
    via_pcm = ingest_pcm(samples)
    try:
        assert via_pcm.quality.passed == via_file.quality.passed
        assert via_pcm.quality.speech_duration_s == via_file.quality.speech_duration_s
        assert via_pcm.quality.snr_db == pytest.approx(via_file.quality.snr_db, abs=0.01)
        assert via_pcm.total_duration_s == pytest.approx(via_file.total_duration_s, abs=1e-3)
        assert Path(via_pcm.normalized_wav_path).is_file()
    finally:
        for p in (via_file.normalized_wav_path, via_pcm.normalized_wav_path):
            Path(p).unlink(missing_ok=True)


def test_ingest_pcm_refuses_silence_and_empty_input():
    for samples in (np.zeros(0, dtype=np.float32), np.zeros(SR * 3, dtype=np.float32)):
        result = ingest_pcm(samples)
        assert not result.quality.passed
        if result.normalized_wav_path:
            Path(result.normalized_wav_path).unlink(missing_ok=True)
