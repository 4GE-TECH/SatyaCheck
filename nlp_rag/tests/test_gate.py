"""The text-side gate.

FR-3's quality gate is acoustic — 1.5s of speech, 5 dB SNR. Nothing gates the text.
Whisper small emits fluent phantom sentences and looped repetitions on near-silence, so
on exactly the audio the acoustic gate exists to catch, a hallucination could feed a
confident script risk into fusion. See `nlp_rag/PLAN.md` §7.
"""

from __future__ import annotations

from nlp_rag.gate import evaluate_transcript

CLEAN = "Papa emergency ho gaya hai, police ne pakad liya hai. Turant paise bhejo."


def test_clean_transcript_passes():
    assert evaluate_transcript(CLEAN, no_speech_prob=0.05, avg_logprob=-0.3).ok


def test_clean_transcript_reports_no_reason():
    assert evaluate_transcript(CLEAN, no_speech_prob=0.05, avg_logprob=-0.3).reason is None


def test_high_no_speech_probability_is_rejected():
    result = evaluate_transcript(CLEAN, no_speech_prob=0.95, avg_logprob=-0.3)
    assert not result.ok
    assert result.reason == "no_speech"


def test_low_average_logprob_is_rejected():
    result = evaluate_transcript(CLEAN, no_speech_prob=0.05, avg_logprob=-2.5)
    assert not result.ok
    assert result.reason == "low_confidence"


def test_empty_transcript_is_rejected():
    result = evaluate_transcript("", no_speech_prob=0.05, avg_logprob=-0.3)
    assert not result.ok
    assert result.reason == "empty"


def test_transcript_below_the_token_floor_is_rejected():
    result = evaluate_transcript("Hello?", no_speech_prob=0.05, avg_logprob=-0.3)
    assert not result.ok
    assert result.reason == "too_short"


def test_looped_repetition_is_rejected():
    """The classic Whisper failure on silence: the decoder locks into a phrase."""
    looped = "Thanks for watching. " * 6
    result = evaluate_transcript(looped, no_speech_prob=0.10, avg_logprob=-0.4)
    assert not result.ok
    assert result.reason == "repetition"


def test_a_repeated_word_in_natural_speech_is_not_treated_as_a_loop():
    """Real callers repeat themselves. Only a repeating n-gram is a decoder loop."""
    natural = (
        "Please, please listen to me. I need the money today, "
        "my son is at the police station and I do not know what to do."
    )
    assert evaluate_transcript(natural, no_speech_prob=0.10, avg_logprob=-0.4).ok


def test_devanagari_transcript_is_not_rejected_for_length():
    text = "माँ, मेरा एक्सीडेंट हो गया है और पुलिस ने पकड़ लिया है।"
    assert evaluate_transcript(text, no_speech_prob=0.05, avg_logprob=-0.3).ok


def test_confidence_is_high_for_a_clean_transcript():
    assert evaluate_transcript(CLEAN, no_speech_prob=0.02, avg_logprob=-0.2).confidence > 0.8


def test_confidence_is_zero_when_the_gate_trips():
    assert evaluate_transcript(CLEAN, no_speech_prob=0.99, avg_logprob=-0.3).confidence == 0.0


def test_confidence_falls_as_no_speech_probability_rises():
    confident = evaluate_transcript(CLEAN, no_speech_prob=0.02, avg_logprob=-0.3).confidence
    marginal = evaluate_transcript(CLEAN, no_speech_prob=0.50, avg_logprob=-0.3).confidence
    assert marginal < confident


def test_missing_whisper_metrics_do_not_reject_an_otherwise_good_transcript():
    """Not every ASR path reports these. Absence is not evidence of a hallucination."""
    assert evaluate_transcript(CLEAN, no_speech_prob=None, avg_logprob=None).ok
