"""Text-side quality gate for ASR output.

The acoustic quality gate (FR-3) checks duration and SNR. It cannot check whether the
words Whisper produced were actually spoken. Whisper `small` hallucinates fluent text on
near-silence and locks into repeating n-grams, so on exactly the audio the acoustic gate
exists to catch, a phantom sentence could feed a confident script risk into fusion.

`TranscriptResult` carries no `details` dict, so the *reason* a transcript was rejected
cannot ride on the contract object. It travels two other ways: folded into `confidence`,
and surfaced as an `RC_TRANSCRIPT_UNRELIABLE` reason code with `signal=QUALITY`, so an
abstention is visible in the evidence panel rather than silent.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from nlp_rag import thresholds

_WORD = re.compile(r"\w+", re.UNICODE)

#: Reasons are stable keys, not prose — reason codes and `details` both index on them.
Reason = str


@dataclass(frozen=True)
class GateResult:
    ok: bool
    confidence: float
    reason: Reason | None = None


def _max_ngram_repeats(tokens: list[str], n: int = 3) -> int:
    if len(tokens) < n:
        return 0
    grams = Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))
    return max(grams.values())


def evaluate_transcript(
    text: str,
    no_speech_prob: float | None = None,
    avg_logprob: float | None = None,
) -> GateResult:
    """Decide whether `text` is trustworthy enough to retrieve against.

    `no_speech_prob` and `avg_logprob` come from faster-whisper. Both are optional:
    not every ASR path reports them, and their absence is not evidence of a problem.
    """
    if not text or not text.strip():
        return GateResult(ok=False, confidence=0.0, reason="empty")

    tokens = [t.lower() for t in _WORD.findall(text)]
    if len(tokens) < thresholds.ASR_MIN_TOKENS:
        return GateResult(ok=False, confidence=0.0, reason="too_short")

    if _max_ngram_repeats(tokens) > thresholds.ASR_MAX_NGRAM_REPEATS:
        return GateResult(ok=False, confidence=0.0, reason="repetition")

    if no_speech_prob is not None and no_speech_prob > thresholds.ASR_MAX_NO_SPEECH_PROB:
        return GateResult(ok=False, confidence=0.0, reason="no_speech")

    if avg_logprob is not None and avg_logprob < thresholds.ASR_MIN_AVG_LOGPROB:
        return GateResult(ok=False, confidence=0.0, reason="low_confidence")

    speech = 1.0 - (no_speech_prob if no_speech_prob is not None else 0.0)
    # avg_logprob is <= 0; -1.0 is the rejection floor, 0.0 is perfect.
    fluency = 1.0 if avg_logprob is None else max(0.0, 1.0 + avg_logprob)
    confidence = max(0.0, min(1.0, 0.5 * speech + 0.5 * fluency))

    return GateResult(ok=True, confidence=confidence, reason=None)


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    cases = [
        ("Turant paise bhejo, kisi ko mat batana.", 0.05, -0.3),
        ("Thanks for watching. " * 6, 0.10, -0.4),
        ("Hello?", 0.05, -0.3),
        ("", 0.05, -0.3),
        ("Turant paise bhejo, kisi ko mat batana.", 0.95, -0.3),
    ]
    for text, nsp, alp in cases:
        result = evaluate_transcript(text, nsp, alp)
        flag = "pass" if result.ok else f"REJECT {result.reason}"
        print(f"  conf {result.confidence:.2f}  {flag:24} {text[:44]!r}")
