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
import re
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from contracts import TranscriptResult, TranscriptSegment
from nlp_rag import thresholds

logger = logging.getLogger(__name__)

__all__ = ["CommittingTranscriber", "StreamingTranscriber"]

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


def _norm(text: str) -> str:
    """Segment text for agreement: case and punctuation do not count as disagreement."""
    return " ".join(re.sub(r"[^\w]+", " ", text.casefold()).split())


class CommittingTranscriber(StreamingTranscriber):
    """Bounded live transcription with LocalAgreement-2 commits (upgrade plan, Phase 3).

    StreamingTranscriber re-decodes the whole call every time, so its work grows with the
    call. This one decodes only the uncommitted tail:

      * the first decode waits `min_first_s` (STREAM_MIN_DECODE_S, the hallucination floor);
      * afterwards the tail is re-decoded every `decode_every_s` of new audio;
      * a segment is committed once two consecutive decodes agree on it (same words in the
        same position) and it ends at least `guard_s` before the newest audio;
      * past `max_tail_s` the oldest uncommitted segments are committed anyway, and
        speechless audio is dropped, so a decode never sees more than ~max_tail_s.

    `last` is the committed transcript (absolute call times; it only grows) — what intent
    is scored on. `tentative_text` is the newest, still-changing words, for display.
    Never raises; a failed decode keeps everything committed so far.
    """

    def __init__(
        self,
        transcribe: "Callable[..., TranscriptResult] | None" = None,
        min_first_s: float | None = None,
        decode_every_s: float | None = None,
        max_tail_s: float | None = None,
        guard_s: float | None = None,
    ) -> None:
        self._min_first_s = thresholds.STREAM_MIN_DECODE_S if min_first_s is None else min_first_s
        self._decode_every_s = thresholds.STREAM_COMMIT_EVERY_S if decode_every_s is None else decode_every_s
        self._max_tail_s = thresholds.STREAM_COMMIT_MAX_TAIL_S if max_tail_s is None else max_tail_s
        self._guard_s = thresholds.STREAM_COMMIT_GUARD_S if guard_s is None else guard_s
        super().__init__(transcribe=transcribe, min_decode_s=self._min_first_s)

    def reset(self) -> None:
        super().reset()
        self._tail: list[np.ndarray] = []
        self._tail_start_s = 0.0
        self._received_s = 0.0
        self._last_decode_at: float | None = None
        self._previous: list[tuple] = []          # last decode's uncommitted segments
        self._committed: list[TranscriptSegment] = []
        self._tentative = ""

    @property
    def tentative_text(self) -> str:
        return self._tentative

    @property
    def buffered_seconds(self) -> float:
        return self._received_s

    def push(
        self, chunk: Sequence[float] | np.ndarray, sample_rate: int = DEFAULT_SAMPLE_RATE
    ) -> TranscriptResult:
        try:
            samples = np.asarray(chunk, dtype=np.float32).reshape(-1)
            if samples.size:
                self._tail.append(samples)
                self._sample_rate = int(sample_rate) or DEFAULT_SAMPLE_RATE
                self._received_s += samples.size / self._sample_rate
            first = self._last_decode_at is None and self._received_s >= self._min_first_s
            again = (self._last_decode_at is not None
                     and self._received_s - self._last_decode_at >= self._decode_every_s)
            if first or again:
                self._commit(final=False)
        except Exception as exc:  # noqa: BLE001 - rule 5, this is on a live socket
            logger.warning("committing push failed (%s); keeping the committed transcript", exc)
        return self._last

    def flush(self) -> TranscriptResult:
        try:
            if self._tail and sum(len(a) for a in self._tail):
                self._commit(final=True)
        except Exception as exc:  # noqa: BLE001 - rule 5
            logger.warning("committing flush failed (%s)", exc)
        self._tentative = ""
        return self._last

    def _commit(self, final: bool) -> None:
        self._last_decode_at = self._received_s
        audio = np.concatenate(self._tail) if self._tail else np.zeros(0, dtype=np.float32)
        if not audio.size:
            return
        result = self._decode_once(audio)
        if result is None:
            return
        self._pin_language(result)
        sr = self._sample_rate
        tail_end = self._tail_start_s + audio.size / sr
        hyp = [(self._tail_start_s + float(s.start_s), self._tail_start_s + float(s.end_s), _norm(s.text),
                s.text.strip(), s.language) for s in result.segments if s.text.strip()]

        if final:
            commit = list(hyp)
        else:
            commit = []
            for i, seg in enumerate(hyp):
                agreed = i < len(self._previous) and seg[2] == self._previous[i][2]
                if not (agreed and seg[1] <= tail_end - self._guard_s):
                    break
                commit.append(seg)
            remaining = hyp[len(commit):]
            cut = commit[-1][1] if commit else self._tail_start_s
            while remaining and tail_end - cut > self._max_tail_s:
                forced = remaining.pop(0)            # bounded tail: commit the oldest anyway
                commit.append(forced)
                cut = forced[1]
                logger.debug("committing transcriber: forced commit at %.1fs (tail cap)", cut)

        self._committed += [TranscriptSegment(start_s=round(a, 3), end_s=round(b, 3), text=t, language=lang)
                            for a, b, _, t, lang in commit]
        remaining = hyp[len(commit):]
        cut = commit[-1][1] if commit else self._tail_start_s
        if not remaining and not final and tail_end - cut > self._max_tail_s:
            cut = tail_end - self._max_tail_s       # no speech to hold on to: drop old audio
        self._trim_to(cut, audio, sr)
        self._previous = [] if final else remaining
        self._tentative = "" if final else " ".join(seg[3] for seg in remaining)
        self._last = TranscriptResult(
            text=" ".join(s.text for s in self._committed),
            segments=list(self._committed),
            detected_language=self._language or result.detected_language,
            confidence=result.confidence,
        )

    def _trim_to(self, cut_s: float, audio: np.ndarray, sr: int) -> None:
        drop = int(round(max(0.0, cut_s - self._tail_start_s) * sr))
        rest = audio[drop:]
        self._tail = [rest] if rest.size else []
        self._tail_start_s = max(self._tail_start_s, cut_s)


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
