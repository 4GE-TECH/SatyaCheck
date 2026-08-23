"""How per-segment ASR confidence is aggregated into one gate decision.

The defect: `no_speech_prob` was aggregated with `max()` across segments. Whisper
reports that probability *per segment*, and a real 34-second call is mostly pauses,
breaths and room tone between utterances — so one quiet segment anywhere set the
whole clip's score. Two clips of clearly audible speech (`me.wav`, a story about
Chhatrapati Shivaji and the iPhone; `me_test2.wav`, an investment pitch) were gated
away entirely at 0.642 against a 0.60 threshold, returning an empty transcript with
`available=False`.

That is not a harmless miss. An empty transcript means the intent branch abstains,
fusion drops `w_text` and renormalises, and the *one branch that catches a scam by
what it says* is silently absent — on a clip whose speech Whisper transcribed fine.

`max()` also gets less accurate the longer the call, which is backwards: more audio
should mean more confidence, not less. A duration-weighted mean asks the right
question — "what fraction of the audio is non-speech" — and is stable as calls grow.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from nlp_rag.asr import _aggregate_no_speech


def _seg(start: float, end: float, no_speech: float) -> SimpleNamespace:
    return SimpleNamespace(start=start, end=end, no_speech_prob=no_speech)


def test_one_quiet_segment_does_not_gate_a_long_clip():
    """The shipped failure, reduced: 30s of speech and one 2s pause."""
    segments = [
        _seg(0.0, 10.0, 0.05),
        _seg(10.0, 20.0, 0.08),
        _seg(20.0, 22.0, 0.95),   # a pause between sentences
        _seg(22.0, 32.0, 0.06),
    ]

    assert _aggregate_no_speech(segments) < 0.20, (
        "a single pause dominated 30 seconds of clear speech"
    )


def test_genuinely_silent_audio_is_still_gated():
    """The gate must keep working — refusing to score silence is a feature."""
    segments = [_seg(0.0, 5.0, 0.93), _seg(5.0, 10.0, 0.97)]

    assert _aggregate_no_speech(segments) > 0.60


def test_longer_segments_carry_more_weight():
    """Duration-weighted, not a plain mean: 20s of speech outvotes a 1s blip."""
    speech_dominant = [_seg(0.0, 20.0, 0.05), _seg(20.0, 21.0, 0.99)]
    silence_dominant = [_seg(0.0, 1.0, 0.05), _seg(1.0, 21.0, 0.99)]

    assert _aggregate_no_speech(speech_dominant) < 0.20
    assert _aggregate_no_speech(silence_dominant) > 0.80


def test_the_result_does_not_degrade_as_a_call_gets_longer():
    """More audio must not mean less confidence.

    Under `max()` every added segment could only push the score up, so a long call
    was gated more readily than a short one saying the same thing.
    """
    short = [_seg(0.0, 5.0, 0.10), _seg(5.0, 7.0, 0.70)]
    long = short + [_seg(7.0 + i * 5, 12.0 + i * 5, 0.10) for i in range(10)]

    assert _aggregate_no_speech(long) < _aggregate_no_speech(short)


def test_empty_and_malformed_segments_do_not_raise():
    """CLAUDE.md rule 5 — this runs inside a live request."""
    assert _aggregate_no_speech([]) == 0.0
    assert _aggregate_no_speech([_seg(0.0, 0.0, 0.5)]) == pytest.approx(0.5)
    assert 0.0 <= _aggregate_no_speech([SimpleNamespace()]) <= 1.0


@pytest.mark.parametrize("probability", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_a_single_segment_reports_its_own_probability(probability):
    assert _aggregate_no_speech([_seg(0.0, 3.0, probability)]) == pytest.approx(probability)
