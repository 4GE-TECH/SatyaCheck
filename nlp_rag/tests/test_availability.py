"""The abstention sentinel B owes C.

`server/orchestrator.py` reads:

    text_available = script.details.get("available", True) is not False

and on False it drops `w_text`, renormalises the remaining weights, and forces the CM
gate's `intent` to a neutral 0.5 instead of 0.0.

The default is `True`, so **silence reads as available**. That puts the whole obligation
on this side: any path that returns `risk=0.0` without evidence must say so explicitly,
or a dead ASR branch is read as a benign call and the trust score rises.
"""

from __future__ import annotations

import pytest

from contracts import ScriptAnalysisResult, TranscriptResult
from nlp_rag import api
from nlp_rag.markers import find_markers
from nlp_rag.retrieve import RetrievalResult
from nlp_rag.score import score_script
from nlp_rag.tests.fakes import FakeEncoder

SCAM = (
    "Papa emergency ho gaya hai, police ne pakad liya hai. "
    "Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe."
)
BENIGN = "Hi Ma, I just reached the office. Will be home by 7 PM today."


@pytest.fixture(autouse=True)
def wired():
    api.configure(encoder=FakeEncoder())
    yield
    api.reset()


def transcript(text: str) -> TranscriptResult:
    return TranscriptResult(text=text, detected_language="hi", confidence=0.95)


def fusion_reads_available(result: ScriptAnalysisResult) -> bool:
    """Exactly the expression in server/orchestrator.py:154."""
    return result.details.get("available", True) is not False


# --- available: the branch produced evidence ---------------------------------

def test_scored_transcript_is_marked_available():
    assert fusion_reads_available(api.analyze_script(transcript(SCAM)))


def test_benign_transcript_is_marked_available():
    """A genuinely benign call is low risk AND available. That is the whole point of
    the flag: risk 0.05 with evidence is not the same as risk 0.0 without any."""
    result = api.analyze_script(transcript(BENIGN))
    assert result.risk <= 0.10
    assert fusion_reads_available(result)


def test_markers_only_analysis_is_still_available():
    """No encoder means no corroboration, but the markers are real evidence.

    Marking this unavailable would discard them and renormalise the branch out, which
    loses more than it protects.
    """
    api.reset()
    result = api.analyze_script(transcript(SCAM))
    assert result.incriminating_markers
    assert fusion_reads_available(result)


# --- unavailable: the branch has nothing to say ------------------------------

def test_empty_transcript_is_marked_unavailable():
    assert not fusion_reads_available(api.analyze_script(TranscriptResult.empty()))


def test_gated_transcript_is_marked_unavailable():
    looped = TranscriptResult(text="Thanks for watching. " * 6, confidence=0.4)
    assert not fusion_reads_available(api.analyze_script(looped))


def test_whitespace_transcript_is_marked_unavailable():
    assert not fusion_reads_available(api.analyze_script(transcript("   \n  ")))


@pytest.mark.parametrize("junk", [None, 42, "not a transcript", object()])
def test_garbage_input_is_marked_unavailable(junk):
    assert not fusion_reads_available(api.analyze_script(junk))


def test_unavailable_result_still_reports_zero_risk():
    """Unavailable means 'no evidence', not 'some risk'. Fusion supplies the neutral."""
    result = api.analyze_script(TranscriptResult.empty())
    assert result.risk == 0.0


# --- the sentinel is set at the scoring seam too, not only at the API --------

def test_score_script_marks_empty_text_unavailable():
    assert not fusion_reads_available(score_script("", RetrievalResult.empty(), []))


def test_score_script_marks_a_real_analysis_available():
    result = score_script(SCAM, RetrievalResult.empty(), find_markers(SCAM))
    assert fusion_reads_available(result)


# --- the two states must be distinguishable, which is the entire defect ------

def test_abstention_and_benign_are_distinguishable_despite_identical_risk():
    """Before the sentinel these were both risk 0.0 and indistinguishable."""
    abstained = api.analyze_script(TranscriptResult.empty())
    benign = api.analyze_script(transcript(BENIGN))

    assert fusion_reads_available(abstained) is False
    assert fusion_reads_available(benign) is True


def test_gate_reason_accompanies_the_sentinel_for_the_evidence_panel():
    looped = TranscriptResult(text="Thanks for watching. " * 6, confidence=0.4)
    details = api.analyze_script(looped).details
    assert details.get("available") is False
    assert details.get("gate_reason") == "repetition"
