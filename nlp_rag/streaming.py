"""Streaming transcription state for the live-call path.

C owns the WebSocket session; this owns the two rules about *when* and *how* to decode,
because both are facts about Whisper rather than about session management.

    from nlp_rag.api import StreamingTranscriber

    stream = StreamingTranscriber()            # once per session
    transcript = stream.push(chunk, sample_rate=16_000)   # every chunk
    transcript = stream.flush()                            # at end of call

`push` returns the current best transcript on every call, so the caller can rescore as
often as it likes. It only *decodes* when enough new audio has arrived.

WHY THIS EXISTS — two defects, both measured on real audio.

**Short windows hallucinate.** The live path used to transcribe every 3-second chunk on
its own. Whisper does not stay silent on too-little audio; it produces confident nonsense
("Thank you.", "Subtitles by…", or here `'alert can product us from with the minger'`).
Only at ~9 seconds did the same clip yield its actual sentence. `PLAN.md` §7's ASR gate
does not catch this — it checks `no_speech_prob` and repetition, and a fluent
hallucination trips neither, so the garbage reaches retrieval and markers as if it were
speech.

**The language label flips.** The same audio detected `en` at one window size and `hi` at
another. That selects which vernacular warning is spoken, so a warning could switch
language between two rescores two seconds apart.

Note this does *not* contradict `INTEGRATION.md` §5, which measured that auto-detection
beats forcing a language. That was about forcing `hi` a priori on audio nobody had heard.
Pinning uses what Whisper itself detected, once, on a long-enough window of this call.

Waiting is close to free: faster-whisper pads every input to a 30-second mel window
(`PLAN.md` §8.1), so decoding 9 seconds costs about what decoding 3 seconds costs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from contracts import TranscriptResult
from nlp_rag import thresholds

logger = logging.getLogger(__name__)

__all__ = ["StreamingTranscriber"]

#: What C's audio pipeline normalises to. Used only when a caller omits the rate.
DEFAULT_SAMPLE_RATE = 16_000


class StreamingTranscriber:
    """Accumulating, language-pinning transcriber for one call.

    Not thread-safe and not shared between sessions: one instance per session, dropped
    when the session ends. Holds the audio for the whole call, which at 16 kHz mono
    float32 is ~1.9 MB for a five-minute call.
    """

    def __init__(
        self,
        transcribe: "Callable[..., TranscriptResult] | None" = None,
        min_decode_s: float | None = None,
    ) -> None:
        """
        Args:
            transcribe: the decoder to call. Defaults to `nlp_rag.api.transcribe`.
                Injected so tests can assert on decode *cadence* rather than only output,
                which is the property that actually broke.
            min_decode_s: seconds of new audio required before decoding again.
        """
        self._transcribe = transcribe
        self._min_decode_s = (
            thresholds.STREAM_MIN_DECODE_S if min_decode_s is None else min_decode_s
        )
        self.reset()

    # --- state ----------------------------------------------------------------

    def reset(self) -> None:
        """Clear the buffer and the pinned language. A new call is a new language."""
        self._buffer: list[np.ndarray] = []
        self._sample_rate: int = DEFAULT_SAMPLE_RATE
        self._buffered_s: float = 0.0
        self._decoded_s: float = 0.0
        self._language: str | None = None
        self._last: TranscriptResult = TranscriptResult.empty()

    @property
    def language(self) -> str | None:
        """The pinned language, or None if nothing confident has been detected yet."""
        return self._language

    @property
    def last(self) -> TranscriptResult:
        """The most recent transcript. Never None, never regresses to empty."""
        return self._last

    @property
    def buffered_seconds(self) -> float:
        return self._buffered_s

    # --- the public surface ---------------------------------------------------

    def push(
        self, chunk: Sequence[float] | np.ndarray, sample_rate: int = DEFAULT_SAMPLE_RATE
    ) -> TranscriptResult:
        """Add a chunk and return the current best transcript. Never raises.

        Decodes only once `min_decode_s` of *new* audio has accumulated since the last
        decode; otherwise returns the previous transcript unchanged. Returning the
        previous one matters: an empty result between decodes would make
        `details["available"]` flap, and fusion would drop and restore `w_text` on
        alternate rescores.
        """
        try:
            samples = np.asarray(chunk, dtype=np.float32).reshape(-1)
            if samples.size:
                self._buffer.append(samples)
                self._sample_rate = int(sample_rate) or DEFAULT_SAMPLE_RATE
                self._buffered_s += samples.size / self._sample_rate

            if self._buffered_s - self._decoded_s >= self._min_decode_s:
                self._decode()
        except Exception as exc:  # noqa: BLE001 - rule 5, this is on a live socket
            logger.warning("streaming push failed (%s); keeping previous transcript", exc)
        return self._last

    def flush(self) -> TranscriptResult:
        """Decode whatever remains. Call at end of call. Never raises.

        Without this a final four-second utterance — often the sentence that names the
        payment — is discarded because it never reached the window.
        """
        try:
            if self._buffered_s > self._decoded_s:
                self._decode()
        except Exception as exc:  # noqa: BLE001 - rule 5
            logger.warning("streaming flush failed (%s)", exc)
        return self._last

    # --- internals ------------------------------------------------------------

    def _decode(self) -> None:
        """Decode the whole accumulated call, not the newest slice.

        The window grows and never slides. `analyze_script` is stateless and scores the
        *cumulative* transcript (`PLAN.md` §1) — retrieval over a fragment is meaningless
        because "turant 50000 bhejo" spans chunks.
        """
        if not self._buffer:
            return

        audio = np.concatenate(self._buffer)
        result = self._decode_once(audio)
        self._decoded_s = self._buffered_s

        if result is None:
            return

        # A decode that produced nothing must not erase what we already had. Mid-call
        # this happens on a stretch of silence, and the evidence so far is still true.
        if not result.text.strip() and self._last.text.strip():
            logger.debug("streaming decode returned empty; keeping previous transcript")
            return

        self._pin_language(result)
        if self._language:
            result = result.model_copy(update={"detected_language": self._language})
        self._last = result

    def _decode_once(self, audio: np.ndarray) -> TranscriptResult | None:
        """Run the decoder, passing the pinned language when there is one."""
        decoder = self._transcribe
        if decoder is None:
            from nlp_rag.api import transcribe as decoder  # local: avoids a cycle

        try:
            return decoder(audio, language=self._language)
        except Exception as exc:  # noqa: BLE001 - rule 5
            logger.warning("streaming decode failed (%s); keeping previous transcript", exc)
            return None

    def _pin_language(self, result: TranscriptResult) -> None:
        """Fix the session's language after the first confident detection.

        Three things are never pinned, each for its own reason:
          * an already-pinned language — that is the point
          * `unknown` — what an abstention reports; pinning it forces it forever
          * a low-confidence guess — Hinglish genuinely lands near p=0.54, and committing
            the rest of the call to a coin flip is worse than re-detecting on more audio
        """
        if self._language is not None:
            return

        detected = (getattr(result, "detected_language", "") or "").strip()
        if not detected or detected == "unknown":
            return

        confidence = float(getattr(result, "confidence", 0.0) or 0.0)
        if confidence < thresholds.STREAM_PIN_LANGUAGE_PROB:
            logger.debug(
                "language %r detected at %.2f, below the pin threshold; re-detecting",
                detected, confidence,
            )
            return

        self._language = detected
        logger.info("streaming language pinned to %r (p=%.2f)", detected, confidence)


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    def _fake(audio: Any, language: str | None = None) -> TranscriptResult:
        seconds = len(audio) / DEFAULT_SAMPLE_RATE
        print(f"    decoded {seconds:5.1f}s   language={language!r}")
        return TranscriptResult(
            text=f"transcript of {seconds:.0f}s", detected_language="hi", confidence=0.9
        )

    stream = StreamingTranscriber(transcribe=_fake)
    print(f"pushing 3s chunks, decode floor {thresholds.STREAM_MIN_DECODE_S}s\n")
    for index in range(1, 8):
        stream.push(np.zeros(3 * DEFAULT_SAMPLE_RATE, dtype=np.float32))
        print(f"  chunk {index} ({index * 3:2d}s buffered) -> {stream.last.text!r}")
    stream.flush()
    print(f"\nlanguage pinned to {stream.language!r}")
    sys.exit(0)
