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
#: RECALIBRATE WHEN BGE-M3 LANDS. These values were fitted against a lexical stand-in
#: encoder, not the real embedding space. `nlp_rag/tests/test_score.py` asserts the
#: §5.1 targets, so recalibration is verified rather than guessed.
SCRIPT_Z0: float = _get("SCRIPT_Z0", 4.0)

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


# --- ASR gate ----------------------------------------------------------------

#: Whisper segment-level no-speech probability above which the transcript is discarded.
ASR_MAX_NO_SPEECH_PROB: float = _get("ASR_MAX_NO_SPEECH_PROB", 0.60)

#: Average token log-probability below which the transcript is discarded.
ASR_MIN_AVG_LOGPROB: float = _get("ASR_MIN_AVG_LOGPROB", -1.0)

#: Fewer word tokens than this is not enough text to retrieve against.
ASR_MIN_TOKENS: int = _get("ASR_MIN_TOKENS", 3)

#: An n-gram repeated more than this many times marks a decoder loop.
ASR_MAX_NGRAM_REPEATS: int = _get("ASR_MAX_NGRAM_REPEATS", 3)
