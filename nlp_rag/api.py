"""The nlp_rag public boundary.

`CLAUDE.md`: "Nothing else crosses a folder boundary. Ever."

    from nlp_rag.api import transcribe, analyze_script, build_reason_codes, challenge_question

Rule 5 governs every function here: catch internally, log, return the neutral default
from the contract. A failing branch degrades the verdict; it never fails C's request.

`analyze_script` is **stateless**. C owns the rolling session buffer and passes the
*cumulative* transcript — retrieval over a 3-second fragment is meaningless, because
"turant 50000 bhejo" spans chunks.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from contracts import (
    ChallengeQuestion,
    EnrolledPerson,
    ReasonCode,
    ScriptAnalysisResult,
    TranscriptResult,
    TrustBand,
)
from nlp_rag import index_store, thresholds
from nlp_rag.asr import transcribe_file
from nlp_rag.challenge import select_challenge
from nlp_rag.corpus_loader import load_corpus
from nlp_rag.gate import evaluate_transcript
from nlp_rag.markers import find_markers
from nlp_rag.reason_codes import build_intent_reason_codes
from nlp_rag.retrieve import Encoder, RetrievalResult, Retriever
from nlp_rag.score import abstain, score_script
from nlp_rag.warnings import warnings_by_band

__all__ = [
    "transcribe",
    "analyze_script",
    "build_reason_codes",
    "challenge_question",
    "configure",
    "reset",
]

logger = logging.getLogger(__name__)

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"

_retriever: Retriever | None = None
_person_lookup: "Callable[[str], EnrolledPerson | None] | None" = None
_configured = False


# --- composition root --------------------------------------------------------
# `configure` and `reset` are wiring, not part of C's contract. C never calls them:
# the first `analyze_script` self-configures against ./models/.

def configure(
    encoder: Encoder | None = None,
    corpus_dir: Path | None = None,
    person_lookup: "Callable[[str], EnrolledPerson | None] | None" = None,
) -> None:
    """Wire the retriever, and optionally a person lookup.

    `person_lookup` inverts a dependency B cannot otherwise satisfy: C calls
    `challenge_question(matched_person_id)`, but shared secrets live in C's database
    and `nlp_rag` may not import `server/` (CLAUDE.md rule 2). C registers a resolver
    once at startup; without one, `challenge_question` degrades to None.
    """
    global _retriever, _configured, _person_lookup
    _configured = True
    _retriever = None
    if person_lookup is not None:
        _person_lookup = person_lookup
    try:
        if encoder is None:
            from nlp_rag.embed import load_encoder

            encoder = load_encoder()
        if encoder is None:
            logger.warning("no encoder available; intent branch runs markers-only")
            return
        corpus = load_corpus(corpus_dir or CORPUS_DIR)

        # Warm start: reuse pre-encoded vectors if `python -m nlp_rag.index_store` has
        # been run. Missing, stale, corrupt or foreign artefacts fall through to
        # encoding. `expect_encoder` matters: a cache written by BGE-m3 read against the
        # 256-dim stand-in is not a degraded result, it is a matmul shape error raised
        # from inside a live request.
        cached = index_store.load(
            *index_store.default_paths(),
            expect_encoder=index_store.encoder_id(encoder),
        )
        if cached:
            logger.info("index cache hit: %d vectors", len(cached.vectors))

        _retriever = Retriever(
            encoder,
            corpus,
            vectors=cached.vectors if cached else None,
            hashes=cached.hashes if cached else None,
        )
    except Exception as exc:  # noqa: BLE001 - a broken corpus degrades, never raises
        logger.warning("retriever unavailable (%s); intent branch runs markers-only", exc)
        _retriever = None


def reset() -> None:
    """Drop the wired retriever and person lookup. Restores the un-configured state."""
    global _retriever, _configured, _person_lookup
    _retriever, _configured, _person_lookup = None, False, None


def _ensure_configured() -> None:
    if not _configured:
        configure()


# --- the four public functions ----------------------------------------------

def transcribe(
    audio_path: str | Path | Sequence[float], language: str | None = None
) -> TranscriptResult:
    """Transcribe a file path or a raw 16 kHz waveform. Never raises.

    C calls this as `transcribe(wav_path or waveform)`, so both are supported.
    """
    try:
        # Pre-transcribed demo clips short-circuit the decoder — PLAN.md §8, the latency
        # mitigation the risk register names. A miss is silent and falls straight through,
        # so this is invisible to C and to the streaming path, where the input is a raw
        # waveform that could not have been pre-transcribed anyway.
        from nlp_rag import pretranscribe

        cached = pretranscribe.lookup(audio_path, pretranscribe.DEFAULT_CACHE)
        if cached is not None:
            logger.info("pre-transcribed clip hit; skipping the decoder")
            return cached

        return transcribe_file(audio_path, language)
    except Exception as exc:  # noqa: BLE001
        logger.warning("transcribe failed (%s)", exc)
        return TranscriptResult.empty()


def analyze_script(transcript: TranscriptResult) -> ScriptAnalysisResult:
    """Score intent risk over the cumulative transcript. Stateless. Never raises."""
    try:
        text = getattr(transcript, "text", "") or ""
        language = _language_of(transcript)
        if not text.strip():
            return abstain("empty_transcript", language)

        verdict = evaluate_transcript(text)
        if not verdict.ok:
            result = abstain("asr_gate", language)
            result.details["gate_reason"] = verdict.reason
            return result

        _ensure_configured()
        retrieval = (
            _retriever.search(text, k=thresholds.RAG_TOP_K)
            if _retriever is not None
            else RetrievalResult.empty()
        )

        result = score_script(text, retrieval, find_markers(text))
        result.details["retrieval_available"] = _retriever is not None
        result.details["vernacular_warnings"] = warnings_by_band(_language_of(transcript))
        return result
    except Exception as exc:  # noqa: BLE001 - rule 5
        logger.warning("analyze_script failed (%s)", exc)
        return abstain("exception")


def build_reason_codes(script: ScriptAnalysisResult) -> list[ReasonCode]:
    """Intent-branch evidence for the script. Never raises.

    C merges these onto the codes A's `fuse` already produced, so this deliberately
    emits INTENT codes only — identity and authenticity are A's to report.
    """
    return build_intent_reason_codes(script)


def challenge_question(
    person: EnrolledPerson | str | None, band: TrustBand = TrustBand.HIGH_RISK
) -> ChallengeQuestion | None:
    """Select a stored shared secret to challenge the caller with. Never raises.

    Accepts either an `EnrolledPerson` or a `person_id`. Resolving an id needs the
    lookup registered via `configure(person_lookup=...)`, because shared secrets live
    in C's database and `nlp_rag` may not import `server/`.

    Returns None whenever a challenge is not warranted — an unenrolled caller, a person
    with no secrets, or a band where identity is not in question. Always producing one
    trains the user to ignore it.
    """
    try:
        if isinstance(person, str):
            if _person_lookup is None:
                logger.warning(
                    "challenge_question called with a person_id but no lookup is "
                    "registered; call configure(person_lookup=...) at startup"
                )
                return None
            person = _person_lookup(person)
        return select_challenge(person, band)
    except Exception as exc:  # noqa: BLE001 - rule 5
        logger.warning("challenge_question failed (%s)", exc)
        return None


# --- helpers -----------------------------------------------------------------

def _language_of(transcript: TranscriptResult) -> str:
    detected = getattr(transcript, "detected_language", "en") or "en"
    return detected.split("-")[0] if detected != "unknown" else "en"


def _provisional_band(risk: float) -> TrustBand:
    """A band derived from intent alone, used *only* to pick warning copy.

    Fusion owns the real band. This never leaves `details` and never reaches the meter.
    """
    if risk >= thresholds.SCRIPT_HIGH_RISK:
        return TrustBand.HIGH_RISK
    if risk >= thresholds.CORROBORATION_FLOOR:
        return TrustBand.SUSPICIOUS
    return TrustBand.VERIFIED  # nothing to warn about from the intent branch alone


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    from nlp_rag.tests.fakes import FakeEncoder

    configure(encoder=FakeEncoder())
    samples = [
        "Papa emergency ho gaya hai. Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe.",
        "Hi Ma, I just reached the office. Will be home by 7 PM today.",
        "Dear customer, your HDFC Bank statement for account ending 4402 is ready.",
    ]
    for sample in samples:
        result = analyze_script(TranscriptResult(text=sample, detected_language="hi"))
        print(f"\nrisk {result.risk:.3f}  {result.intent_summary}")
        for playbook in result.playbooks[:1]:
            print(f"  cites: {playbook.title} — {playbook.source_url}")
        print(f"  warning: {result.details.get('vernacular_warning') or '—'}")
