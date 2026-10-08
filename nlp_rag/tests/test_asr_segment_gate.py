"""The confidence gate works per segment, not on the whole transcript.

Seen live on an Exotel call: 73 s of a caller reading a bank-OTP scam script came back
`transcript gated: low_confidence` on every decode, so the intent branch abstained for the
whole call and the verdict sat at "unverified". `avg_logprob` was averaged over every
segment, so a few garbled stretches of 8 kHz phone audio dragged the mean under the floor
and threw away the clearly heard sentences with them — and the longer the call, the more
garbled stretches it has.

Each segment is now judged on its own confidence; the confident ones are kept and the
whole-transcript gate runs on those. A rejection logs the numbers (rule: log why a branch
degrades), never the text.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import numpy as np
import pytest

from nlp_rag import asr, thresholds


def _seg(text, logprob, start, no_speech=0.05):
    return SimpleNamespace(text=text, avg_logprob=logprob, no_speech_prob=no_speech,
                           start=start, end=start + 3.0)


@pytest.fixture
def decode(monkeypatch):
    """Point transcribe_file at a fake model returning the given segments."""
    def _set(segments):
        model = SimpleNamespace(transcribe=lambda *a, **k: (
            iter(segments), SimpleNamespace(language="en", language_probability=0.99)))
        monkeypatch.setattr(asr, "_load_model", lambda: model)
        return asr.transcribe_file(np.zeros(16000 * 9, dtype=np.float32))
    return _set


CLEAR = "we have sent you an OTP please tell me the OTP right now"


def test_garbled_segments_no_longer_sink_the_clear_ones(decode):
    floor = thresholds.ASR_MIN_AVG_LOGPROB
    result = decode([
        _seg("hello sir I am calling from SBI head office", floor + 0.6, 0.0),
        _seg("mm arr gha", floor - 1.5, 3.0),
        _seg(CLEAR, floor + 0.5, 6.0),
        _seg("sss", floor - 1.4, 9.0),
    ])
    # The whole-transcript mean is below the floor; the clear sentences must survive.
    assert "OTP" in result.text and "SBI" in result.text
    assert "arr gha" not in result.text
    assert [s.text for s in result.segments] == ["hello sir I am calling from SBI head office", CLEAR]


def test_all_low_confidence_is_still_rejected_and_logged_without_text(decode, caplog):
    floor = thresholds.ASR_MIN_AVG_LOGPROB
    with caplog.at_level(logging.INFO, logger=asr.logger.name):
        result = decode([_seg("secret words here", floor - 0.3, 0.0),
                         _seg("more secret words", floor - 0.2, 3.0)])
    assert result.text == ""
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "low_confidence" in msgs and "0/2 segment" in msgs
    assert "secret" not in msgs  # transcripts never go to the log


def test_a_confident_transcript_is_unchanged(decode):
    result = decode([_seg("hello this is a normal call", -0.2, 0.0), _seg(CLEAR, -0.3, 3.0)])
    assert result.text == f"hello this is a normal call {CLEAR}"
    assert result.confidence > 0.5


def test_dropping_segments_is_logged_with_counts(decode, caplog):
    floor = thresholds.ASR_MIN_AVG_LOGPROB
    with caplog.at_level(logging.INFO, logger=asr.logger.name):
        decode([_seg(CLEAR, floor + 0.5, 0.0), _seg("gha", floor - 1.0, 3.0)])
    assert any("kept 1/2 segment" in r.getMessage() for r in caplog.records)


def test_confidently_decoded_speech_is_not_silence(decode):
    """Replayed from a live call: a cloned voice and the callee, 12 clear segments at
    avg_logprob -0.24, carried no_speech_prob 0.76 on most of them, so the whole call
    was gated "no_speech" and the intent branch abstained. Whisper's own rule treats a
    segment as silent only when it is ALSO poorly decoded."""
    result = decode([_seg("hello I enjoy visiting this cafe in my free time", -0.24, 0.0, no_speech=0.76),
                     _seg("I think you got a wrong number please cut the call", -0.27, 3.0, no_speech=0.76)])
    assert "wrong number" in result.text


def test_extreme_no_speech_is_still_silence_even_when_fluent(decode):
    # Whisper's fluent phantom sentences on near-silence (PLAN.md section 7).
    result = decode([_seg("thank you for watching please subscribe", -0.2, 0.0, no_speech=0.95)])
    assert result.text == ""
