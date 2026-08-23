"""Calibration constants for the intent branch.

`config.py` is C's file and holds the project-wide thresholds. It does not exist yet, and
`CLAUDE.md` rule 2 forbids B from creating it. So each constant is read from `config` when
that module is importable and falls back to the value documented in `nlp_rag/PLAN.md`.

When C ships `config.py`, defining any of these names there overrides the default with no
change here. Nothing in `nlp_rag/` hardcodes a threshold at a call site.
"""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - depends on whether C has shipped config.py yet
    import config as _config
except ImportError:  # pragma: no cover
    _config = None


def _get(name: str, default: Any) -> Any:
    return getattr(_config, name, default) if _config is not None else default


# --- retrieval knobs owned by C ----------------------------------------------
# These exist in `config.py`; the fallbacks only apply before it is importable.

#: How many playbooks to retrieve per query.
RAG_TOP_K: int = _get("RAG_TOP_K", 3)

#: Absolute cosine floor below which a playbook is never cited, whatever the cohort
#: says. Combined with `CORROBORATION_FLOOR` as an AND: a citation must be both strong
#: in absolute terms and clearly above the benign background. Either gate tightening
#: only ever removes a citation, never adds one.
RAG_SIMILARITY_THRESHOLD: float = _get("RAG_SIMILARITY_THRESHOLD", 0.60)


# --- retrieval normalisation -------------------------------------------------

#: Centre of the logistic mapping from cohort z-score to retrieval risk: how many cohort
#: standard deviations above background a match must sit before it reads as real risk.
#:
#: Deliberately high. At z0=2.0 an ordinary call landing 1.6σ above background scored
#: 0.39, which is the over-flagging this system exists to avoid. A benign transcript
#: sitting a little above the mean is the *normal* case, not a weak signal.
#:
#: Raised 4.0 -> 5.5 when the corpus grew from 26 to 56 indexed documents.
#:
#: This is not a taste adjustment, it is arithmetic. `z` compares the best scam match
#: against the benign background: growing the scam index raises `max_scam_cos` for every
#: query, including benign ones, while `mean(benign_cos)` and `std(benign_cos)` are
#: computed over an unchanged cohort. So *every* benign z drifts upward with corpus
#: growth, and z0 has to follow it. At 4.0 the grown corpus put 14.6% of the benign
#: cohort above the amber floor; at 5.5 it is 1.2%, with every §5.1 target intact.
#:
#: **Re-run `python -m nlp_rag.eval_retrieval` after any corpus growth.** The number to
#: watch is the benign false-positive rate, and the direction it moves is predictable.
SCRIPT_Z0: float = _get("SCRIPT_Z0", 5.5)

#: Temperature of that logistic. Larger is softer.
SCRIPT_TAU: float = _get("SCRIPT_TAU", 1.0)

#: Cohort standard deviations below this are treated as this. A small or homogeneous
#: benign corpus otherwise produces enormous z-scores from trivial similarity gaps.
MIN_COHORT_STD: float = _get("MIN_COHORT_STD", 0.05)

#: Retrieval alone never asserts certainty; markers must retain headroom above it.
R_RET_CEILING: float = _get("R_RET_CEILING", 0.92)


# --- markers -----------------------------------------------------------------

#: Maximum absolute contribution of all markers combined. Applied as a tanh squash, so
#: additional markers have diminishing returns rather than hitting a wall.
MARKER_DELTA_CAP: float = _get("MARKER_DELTA_CAP", 0.35)


# --- the cap -----------------------------------------------------------------

#: Retrieval risk at or above this counts as corroboration by a cited document.
CORROBORATION_FLOOR: float = _get("CORROBORATION_FLOOR", 0.35)

#: Script risk at or above this is "red" territory. Markers alone may not reach it:
#: red with no citable document is a verdict with no evidence (PRD NG2).
SCRIPT_HIGH_RISK: float = _get("SCRIPT_HIGH_RISK", 0.75)

#: Any transcript carrying signal scores at least this, so the panel never shows a bare
#: zero for a call that was actually analysed.
RISK_FLOOR: float = _get("RISK_FLOOR", 0.01)


def _amber_floor(default: float = 0.15) -> float:
    """Lower bound of the `caution` band, read from C's `BAND_THRESHOLDS`."""
    bands = _get("BAND_THRESHOLDS", None)
    try:
        return float(bands["caution"][0])
    except (TypeError, KeyError, IndexError, ValueError):
        return default


#: Where amber begins. `BAND_THRESHOLDS` maps *fused* risk, not intent risk, but the
#: intent branch's false-positive rate is only meaningful against the boundary a user
#: would actually see, so `eval_retrieval` reads the same number rather than inventing
#: its own. Owned by C; never hardcode it at a call site.
AMBER_FLOOR: float = _amber_floor()


# --- ASR gate ----------------------------------------------------------------

#: Whisper segment-level no-speech probability above which the transcript is discarded.
ASR_MAX_NO_SPEECH_PROB: float = _get("ASR_MAX_NO_SPEECH_PROB", 0.60)

#: Average token log-probability below which the transcript is discarded.
ASR_MIN_AVG_LOGPROB: float = _get("ASR_MIN_AVG_LOGPROB", -1.0)

#: Fewer word tokens than this is not enough text to retrieve against.
ASR_MIN_TOKENS: int = _get("ASR_MIN_TOKENS", 3)

#: An n-gram repeated more than this many times marks a decoder loop.
ASR_MAX_NGRAM_REPEATS: int = _get("ASR_MAX_NGRAM_REPEATS", 3)


# --- streaming ----------------------------------------------------------------

#: Seconds of audio to accumulate before the streaming path decodes again.
#:
#: The live-call path used to transcribe each 3-second chunk on its own, and Whisper does
#: not stay silent on too-little audio — it invents fluent sentences. Measured on
#: friend_test.wav, identical audio at three window sizes:
#:
#:     3s   'alert can product us from with the minger next week'   (garbage)
#:     6s   'alert can product us from with the minger next weekend.'
#:     9s   'never send money to unknown people and always verify…'  (correct)
#:
#: The ASR gate does not catch this: it checks no_speech_prob and repetition, and a fluent
#: hallucination trips neither.
#:
#: 9s is a floor, not a cadence. faster-whisper pads everything to a 30-second mel window
#: (PLAN.md §8.1), so decode cost is ~flat from 3s to 30s — waiting for more audio costs
#: almost nothing and buys correctness.
STREAM_MIN_DECODE_S: float = _get("STREAM_MIN_DECODE_S", 9.0)

#: Language-detection confidence required before pinning a session's language.
#:
#: Below this the detection is re-run on the next window instead. Code-switched Hinglish
#: genuinely lands around p=0.54, and committing the whole call to a coin flip is worse
#: than re-detecting on more audio. Shares its value with ASR_MIN_LANGUAGE_PROB for the
#: same reason that threshold exists.
STREAM_PIN_LANGUAGE_PROB: float = _get(
    "STREAM_PIN_LANGUAGE_PROB", _get("ASR_MIN_LANGUAGE_PROB", 0.60)
)

#: Below this, Whisper's own language detection is not trusted and `config.WHISPER_LANGUAGE`
#: is reported instead — as the prior it is documented to be ("Primary language").
#:
#: Measured on real audio: clean English detects at p=1.00, while code-switched Hinglish
#: lands at p=0.54-0.57 — genuinely uncertain, and exactly the case where the deployment's
#: primary language is the better label. This affects the REPORTED label only. Decoding is
#: always auto-detected; see the note in `asr.py`.
ASR_MIN_LANGUAGE_PROB: float = _get("ASR_MIN_LANGUAGE_PROB", 0.60)
