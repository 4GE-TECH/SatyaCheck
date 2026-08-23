"""Streaming transcription — accumulate before decoding, and pin the language.

TWO DEFECTS THIS EXISTS TO FIX, both measured on real audio before it was written.

`server/ws_router.py` ingests and transcribes every 3-second chunk independently, with no
accumulated state. Running `friend_test.wav` through three window sizes, same audio:

    3s   ''  ''  'alert can product us from with the minger next week'  ''    en
    6s   ''  'alert can product us from with the minger next weekend.'        hi
    9s   'never send money to unknown people and always verify before…'       hi

**1 · Short windows hallucinate.** Only the 9-second window recovers the real sentence.
Whisper is not silent on too-little audio, it is confidently wrong — the well-known
"Thank you." / "Subtitles by..." failure. `PLAN.md` §7 built the ASR gate for this, but the
gate checks `no_speech_prob` and repetition, and a fluent hallucination trips neither. The
garbage then reaches retrieval and markers as if it were speech.

**2 · The language label flips.** The same audio detects `en` at one window size and `hi` at
another. Mid-call that changes which vernacular warnings are chosen, so the spoken warning
can switch language between one 2-second rescore and the next.

This does NOT contradict `INTEGRATION.md` §5, which measured that auto-detection beats
forcing a language. That was about forcing `hi` a priori on unheard audio. Pinning uses what
Whisper itself detected on a long-enough window of *this* call — using detection once,
rather than re-litigating it every two seconds on progressively different slices.
"""

from __future__ import annotations

import numpy as np
import pytest

from contracts import TranscriptResult
from nlp_rag import thresholds

SR = 16_000


def _audio(seconds: float) -> np.ndarray:
    """A waveform of the right length. Content is irrelevant — the decoder is faked."""
    return np.zeros(int(seconds * SR), dtype=np.float32)


class FakeDecoder:
    """Records every call so tests can assert on decode cadence, not just output."""

    def __init__(self, *results: TranscriptResult) -> None:
        self.results = list(results)
        self.calls: list[tuple[float, str | None]] = []

    def __call__(self, audio, language=None):  # noqa: ANN001 - matches transcribe()
        self.calls.append((len(audio) / SR, language))
        if self.results:
            return self.results.pop(0)
        return TranscriptResult(text="ok", detected_language="en", confidence=0.9)

    @property
    def languages_requested(self) -> list[str | None]:
        return [lang for _, lang in self.calls]

    @property
    def window_lengths(self) -> list[float]:
        return [seconds for seconds, _ in self.calls]


def _transcriber(decoder):
    from nlp_rag.streaming import StreamingTranscriber

    return StreamingTranscriber(transcribe=decoder)


# --- 1 · accumulate before decoding -------------------------------------------

def test_a_short_chunk_does_not_reach_the_decoder():
    """The core fix. A 3-second slice is where Whisper invents sentences."""
    decoder = FakeDecoder()
    stream = _transcriber(decoder)

    stream.push(_audio(3.0), sample_rate=SR)

    assert decoder.calls == [], (
        "a 3-second chunk was decoded on its own — this is the hallucination case"
    )


def test_chunks_accumulate_until_the_window_is_long_enough():
    """Three 3-second chunks make one 9-second decode, not three 3-second ones."""
    decoder = FakeDecoder()
    stream = _transcriber(decoder)

    for _ in range(3):
        stream.push(_audio(3.0), sample_rate=SR)

    assert len(decoder.calls) == 1, f"expected one decode, got {len(decoder.calls)}"
    assert decoder.window_lengths[0] >= thresholds.STREAM_MIN_DECODE_S


def test_the_decoder_always_sees_the_whole_call_not_the_latest_slice():
    """`analyze_script` scores the *cumulative* transcript — PLAN.md §1.

    Retrieval over a fragment is meaningless because "turant 50000 bhejo" spans chunks.
    The window must grow, never slide.
    """
    decoder = FakeDecoder()
    stream = _transcriber(decoder)

    for _ in range(6):
        stream.push(_audio(3.0), sample_rate=SR)

    assert len(decoder.calls) == 2
    assert decoder.window_lengths[1] > decoder.window_lengths[0], (
        f"second decode saw {decoder.window_lengths[1]:.1f}s after "
        f"{decoder.window_lengths[0]:.1f}s — the window is sliding, not growing"
    )
    assert decoder.window_lengths[1] == pytest.approx(18.0, abs=0.1)


def test_the_previous_transcript_is_returned_between_decodes():
    """A caller polling every 2s must never see the text vanish and reappear.

    Returning empty between decodes would make `details["available"]` flap, and fusion
    would drop and restore `w_text` on alternate rescores.
    """
    decoder = FakeDecoder(TranscriptResult(text="first pass", detected_language="en", confidence=0.9))
    stream = _transcriber(decoder)

    for _ in range(3):
        stream.push(_audio(3.0), sample_rate=SR)
    settled = stream.push(_audio(3.0), sample_rate=SR)

    assert settled.text == "first pass", "the transcript regressed between decodes"


def test_a_final_flush_decodes_whatever_is_left():
    """End of call. A 4-second final utterance must not be silently discarded."""
    decoder = FakeDecoder()
    stream = _transcriber(decoder)

    stream.push(_audio(4.0), sample_rate=SR)
    assert decoder.calls == []

    result = stream.flush()
    assert len(decoder.calls) == 1, "flush did not decode the tail"
    assert result.text


def test_flush_on_an_empty_stream_abstains_rather_than_raising():
    """CLAUDE.md rule 5, and the abstention contract fusion depends on."""
    stream = _transcriber(FakeDecoder())
    result = stream.flush()

    assert isinstance(result, TranscriptResult)
    assert result.text == ""


# --- 2 · pin the language -----------------------------------------------------

def test_the_language_is_pinned_after_the_first_confident_detection():
    """The flip fix. Detection happens once; every later decode is told the answer."""
    decoder = FakeDecoder(
        TranscriptResult(text="pehli baar", detected_language="hi", confidence=0.9),
        TranscriptResult(text="dusri baar", detected_language="en", confidence=0.9),
    )
    stream = _transcriber(decoder)

    for _ in range(6):
        stream.push(_audio(3.0), sample_rate=SR)

    assert decoder.languages_requested[0] is None, "the first decode must auto-detect"
    assert decoder.languages_requested[1] == "hi", (
        f"second decode requested {decoder.languages_requested[1]!r} — the language was "
        "not pinned and will flip mid-call"
    )


def test_the_reported_language_stays_pinned_even_if_the_decoder_disagrees():
    """Whisper returning `en` on a later window must not change the session's language.

    This is what selects the vernacular warning. A warning that switches language
    between two rescores of the same call is worse than one in the wrong language.
    """
    decoder = FakeDecoder(
        TranscriptResult(text="pehli baar", detected_language="hi", confidence=0.9),
        TranscriptResult(text="dusri baar", detected_language="en", confidence=0.9),
    )
    stream = _transcriber(decoder)

    for _ in range(6):
        stream.push(_audio(3.0), sample_rate=SR)

    assert stream.language == "hi"
    assert stream.last.detected_language == "hi"


def test_an_uncertain_detection_is_not_pinned():
    """Pinning a guess is worse than re-detecting.

    `ASR_MIN_LANGUAGE_PROB` exists because code-switched Hinglish genuinely lands around
    p=0.54. Locking that in for the rest of the call commits to a coin flip.
    """
    decoder = FakeDecoder(
        TranscriptResult(text="unsure", detected_language="hi", confidence=0.30),
        TranscriptResult(text="clearer", detected_language="hi", confidence=0.95),
    )
    stream = _transcriber(decoder)

    for _ in range(6):
        stream.push(_audio(3.0), sample_rate=SR)

    assert decoder.languages_requested[1] is None, (
        "a low-confidence detection was pinned; it should re-detect"
    )


def test_an_unknown_language_is_never_pinned():
    """`unknown` is what an abstention reports. Pinning it would force it forever.

    The realistic shape of this: a call opens with a few seconds of silence or noise, so
    the first decode abstains. Detection must stay open, and the first *real* speech is
    what gets pinned.
    """
    decoder = FakeDecoder(
        TranscriptResult(text="", detected_language="unknown", confidence=0.0),
        TranscriptResult(text="real speech now", detected_language="en", confidence=0.9),
    )
    stream = _transcriber(decoder)

    for _ in range(3):
        stream.push(_audio(3.0), sample_rate=SR)
    assert stream.language is None, "'unknown' was pinned as if it were a language"

    for _ in range(3):
        stream.push(_audio(3.0), sample_rate=SR)

    assert decoder.languages_requested[1] is None, (
        "the second decode was told a language, but nothing had been pinned yet"
    )
    assert stream.language == "en", "detection did not resume after the abstention"


def test_reset_clears_both_the_buffer_and_the_pin():
    """The ws protocol has a `reset` message; a new call is a new language."""
    decoder = FakeDecoder(
        TranscriptResult(text="hindi call", detected_language="hi", confidence=0.9)
    )
    stream = _transcriber(decoder)
    for _ in range(3):
        stream.push(_audio(3.0), sample_rate=SR)
    assert stream.language == "hi"

    stream.reset()

    assert stream.language is None
    assert stream.last.text == ""
    stream.push(_audio(3.0), sample_rate=SR)
    assert len(decoder.calls) == 1, "buffer was not cleared by reset"


# --- degradation ---------------------------------------------------------------

def test_a_decoder_failure_returns_the_last_good_transcript():
    """CLAUDE.md rule 5. One bad decode must not wipe the evidence so far."""
    def explode(audio, language=None):  # noqa: ANN001
        raise RuntimeError("decoder died")

    decoder = FakeDecoder(TranscriptResult(text="good so far", detected_language="en", confidence=0.9))
    stream = _transcriber(decoder)
    for _ in range(3):
        stream.push(_audio(3.0), sample_rate=SR)

    stream._transcribe = explode  # type: ignore[attr-defined]
    result = stream.push(_audio(9.0), sample_rate=SR)

    assert result.text == "good so far"


def test_the_window_is_measured_in_seconds_not_samples():
    """Sample rate is how seconds are computed — narrowband audio is half the samples.

    A real call arrives at 8 kHz. Counting samples instead of seconds would decode at
    ~4.5 seconds of speech, back inside the hallucination zone, while the counter claimed
    9. The transcriber must honour the declared rate.
    """
    decoder = FakeDecoder()
    stream = _transcriber(decoder)

    # Three 3-second chunks *at 8 kHz* — half the samples of the 16 kHz case, same
    # duration. Nine seconds of audio has arrived, so exactly one decode is due.
    for _ in range(3):
        stream.push(np.zeros(3 * 8_000, dtype=np.float32), sample_rate=8_000)

    assert len(decoder.calls) == 1, (
        f"expected one decode after 9s of 8 kHz audio, got {len(decoder.calls)}"
    )
    assert stream.buffered_seconds == pytest.approx(9.0, abs=0.01), (
        f"buffered {stream.buffered_seconds:.1f}s — samples are being counted as if 16 kHz"
    )
