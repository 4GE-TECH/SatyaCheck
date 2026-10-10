"""Upgrade plan, Phase 3: bounded, committing live ASR (nlp_rag.streaming.CommittingTranscriber).

StreamingTranscriber re-decodes the WHOLE call every time, so its work grows for as long
as the call lasts. The committing transcriber decodes only the uncommitted tail (capped),
commits a segment once two consecutive decodes agree on it (LocalAgreement-2), and keeps
what is committed fixed. A fake decoder stands in for Whisper: every second of audio
carries its own index, and the newest second's word is unstable between decodes.
"""

from __future__ import annotations

import numpy as np
import pytest

from contracts import TranscriptResult, TranscriptSegment
from nlp_rag.streaming import CommittingTranscriber

SR = 16_000


def _audio(start_s: int, seconds: int) -> np.ndarray:
    """Second k of the call holds the constant k/1000, so the decoder can tell where it is."""
    return np.concatenate([np.full(SR, k / 1000.0, dtype=np.float32) for k in range(start_s, start_s + seconds)])


class FakeWhisper:
    def __init__(self, language="hi"):
        self.inputs: list[float] = []      # seconds of audio per decode
        self.calls = 0
        self.language = language

    def __call__(self, audio, language=None):
        self.calls += 1
        audio = np.asarray(audio)
        self.inputs.append(len(audio) / SR)
        seconds = [int(round(float(audio[i * SR]) * 1000)) for i in range(len(audio) // SR)]
        segments = []
        for j, k in enumerate(seconds):
            unstable = j == len(seconds) - 1
            text = f"w{k}" + (f"~{self.calls}" if unstable else "")
            segments.append(TranscriptSegment(start_s=float(j), end_s=float(j + 1), text=text, language=self.language))
        return TranscriptResult(text=" ".join(s.text for s in segments), segments=segments,
                                detected_language=self.language, confidence=0.9)


def _feed(t: CommittingTranscriber, start_s: int, seconds: int):
    out = None
    for k in range(start_s, start_s + seconds):
        out = t.push(_audio(k, 1), sample_rate=SR)
    return out


def _make(**kw):
    fake = FakeWhisper()
    kw = {"min_first_s": 4.0, "decode_every_s": 2.0, "max_tail_s": 8.0, "guard_s": 1.0, **kw}
    return CommittingTranscriber(transcribe=fake, **kw), fake


def test_nothing_is_decoded_before_the_first_window():
    t, fake = _make()
    _feed(t, 0, 3)
    assert fake.calls == 0 and t.last.text == ""


def test_segments_commit_only_once_two_decodes_agree():
    t, fake = _make()
    _feed(t, 0, 4)                      # first decode: nothing agreed yet
    assert fake.calls == 1 and t.last.text == ""
    assert t.tentative_text.startswith("w0")
    _feed(t, 4, 2)                      # second decode agrees on the early words
    assert t.last.text.startswith("w0 w1 w2")
    assert "~" not in t.last.text, "an unstable word was committed"


def test_committed_text_never_changes_and_only_grows():
    t, _ = _make()
    seen = []
    for k in range(0, 40):
        t.push(_audio(k, 1), sample_rate=SR)
        seen.append(t.last.text)
    for earlier, later in zip(seen, seen[1:]):
        assert later.startswith(earlier), (earlier, later)
    assert len(seen[-1].split()) >= 30


def test_decoding_work_is_bounded_however_long_the_call():
    t, fake = _make()
    _feed(t, 0, 120)
    assert max(fake.inputs) <= 8.0 + 2.0 + 1e-6, fake.inputs[-5:]


def test_flush_commits_the_tail():
    t, _ = _make()
    _feed(t, 0, 9)
    final = t.flush()
    assert final.text.split()[-1].startswith("w8")
    assert t.tentative_text == ""


def test_committed_segments_carry_call_time_not_tail_time():
    t, _ = _make()
    _feed(t, 0, 20)
    starts = [s.start_s for s in t.last.segments]
    assert starts == sorted(starts) and starts[-1] > 8.0, "segment times must be absolute"


def test_the_language_is_pinned_after_a_confident_detection():
    t, fake = _make()
    _feed(t, 0, 6)
    assert t.language == "hi"
    fake.language = "en"
    _feed(t, 6, 6)
    assert t.last.detected_language == "hi"


def test_a_failed_decode_keeps_what_was_committed():
    t, fake = _make()
    _feed(t, 0, 8)
    committed = t.last.text

    def boom(audio, language=None):
        raise RuntimeError("cuda out of memory")

    t._transcribe = boom
    assert _feed(t, 8, 4).text == committed
