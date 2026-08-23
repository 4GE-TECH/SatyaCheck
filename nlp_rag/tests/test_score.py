"""Scoring turns a similarity and some markers into a calibrated risk.

The §5.1 targets are the acceptance criteria: the benign cohort lands at or below 0.10,
a full playbook-plus-markers hit lands at or above 0.90. These are asserted against the
real seed corpus so a corpus edit that collapses the separation fails here rather than
on stage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from contracts import MarkerType
from nlp_rag import thresholds
from nlp_rag.corpus_loader import load_corpus
from nlp_rag.markers import find_markers
from nlp_rag.retrieve import RetrievalResult, Retriever
from contracts import RetrievedPlaybook
from nlp_rag.score import score_script


def playbook(similarity: float) -> RetrievedPlaybook:
    return RetrievedPlaybook(
        playbook_id="anch-x",
        title="Advisory",
        category="Extortion",
        similarity_score=similarity,
        matched_excerpt="...",
        source_url="https://cybercrime.gov.in/x",
        source_agency="I4C",
    )
from nlp_rag.tests.fakes import FakeEncoder

CORPUS_DIR = Path(__file__).parent.parent / "corpus"

CLONE_EXTORTION = (
    "Papa emergency ho gaya hai, police ne pakad liya hai. "
    "Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe."
)
FAMILY_CHECKIN = "Hi Ma, I just reached the office. Will be home by 7 PM today."
BANK_IVR = (
    "Dear customer, your HDFC Bank statement for account ending 4402 is ready. "
    "Press 1 to receive on WhatsApp."
)
GENUINE_UNUSUAL = (
    "Papa, my wallet was stolen at the station and my cards are gone. "
    "Can you send me two thousand so I can get home? "
    "Call me back on this number to check it's me, or call Rohit, he is here with me."
)


@pytest.fixture(scope="module")
def retriever() -> Retriever:
    return Retriever(FakeEncoder(), load_corpus(CORPUS_DIR))


def analyse(retriever: Retriever, text: str):
    return score_script(text, retriever.search(text, k=3), find_markers(text))


# --- §5.1 calibration targets ------------------------------------------------

def test_clone_extortion_scores_at_or_above_the_high_hit_target(retriever: Retriever):
    assert analyse(retriever, CLONE_EXTORTION).risk >= 0.90


def test_benign_family_checkin_scores_at_or_below_the_benign_target(retriever: Retriever):
    assert analyse(retriever, FAMILY_CHECKIN).risk <= 0.10


def test_legitimate_bank_ivr_scores_at_or_below_the_benign_target(retriever: Retriever):
    """False-positive guard one. If this rises, the product loses its first demo."""
    assert analyse(retriever, BANK_IVR).risk <= 0.10


def test_genuine_unusual_request_stays_below_high_risk(retriever: Retriever):
    """False-positive guard two. A real emergency that invites verification is not red."""
    assert analyse(retriever, GENUINE_UNUSUAL).risk < thresholds.SCRIPT_HIGH_RISK


# --- the same scam must score the same in whichever script Whisper emits ------
# `z = (max_scam_cos - mean(benign_cos)) / std(benign_cos)`. The benign cohort is
# thoroughly multilingual; the scam corpus was not (20 en / 4 hi_latn / 2 devanagari).
# A Devanagari call therefore met a well-populated background and a nearly empty
# foreground -- a starved numerator against a healthy denominator -- and under-scored
# purely for being in Hindi. None of the three targets above catch it: all are Latin.
#
# The guard is deliberately NOT here. `FakeEncoder` is a lexical hasher and `fakes.py`
# says plainly that no test should assert on its absolute scores; a paraphrased
# Devanagari probe shares few exact tokens with any document, so an absolute threshold
# measures the stand-in rather than the corpus. The defect was corpus *coverage*, so it
# is asserted as coverage:
#
#   tests/test_corpus_integrity.py::test_every_indexed_anchor_covers_all_three_scripts
#
# and the resulting score is checked under the real encoder, where it is meaningful:
#
#   eval_retrieval.CALIBRATION_CASES -> kyc_deva, parcel_deva


# --- the cap: no citation, no red -------------------------------------------

def test_markers_alone_cannot_reach_high_risk():
    """Red with no retrieved document is a verdict with no evidence (PRD NG2)."""
    text = "Don't tell anyone. Share the OTP now. You will be arrested otherwise."
    uncorroborated = RetrievalResult(
        playbooks=[], cohort_similarities=[0.1, 0.12, 0.09], top_similarity=0.11
    )
    result = score_script(text, uncorroborated, find_markers(text))

    assert result.incriminating_markers, "precondition: markers must have fired"
    assert result.risk < thresholds.SCRIPT_HIGH_RISK


def test_markers_alone_still_raise_risk_above_the_floor():
    """Capped, not ignored. An uncorroborated isolation demand is still worth amber."""
    text = "Don't tell anyone. Share the OTP now."
    uncorroborated = RetrievalResult(
        playbooks=[], cohort_similarities=[0.1, 0.12, 0.09], top_similarity=0.11
    )
    assert score_script(text, uncorroborated, find_markers(text)).risk > 0.10


# --- markers move risk in both directions ------------------------------------

def test_exculpatory_markers_lower_risk_relative_to_the_same_text_without_them():
    retrieval = RetrievalResult(
        playbooks=[], cohort_similarities=[0.1, 0.12, 0.09], top_similarity=0.30
    )
    incriminating_only = "Send fifty thousand immediately by UPI."
    with_exculpatory = incriminating_only + " Call Papa and ask him yourself."

    bare = score_script(incriminating_only, retrieval, find_markers(incriminating_only))
    softened = score_script(with_exculpatory, retrieval, find_markers(with_exculpatory))

    assert softened.risk < bare.risk


def test_both_marker_directions_are_reported_separately():
    text = "Don't tell anyone. Actually, call Papa and ask him yourself."
    result = score_script(text, RetrievalResult.empty(), find_markers(text))

    assert [m.marker_type for m in result.incriminating_markers] == [MarkerType.INCRIMINATING]
    assert [m.marker_type for m in result.exculpatory_markers] == [MarkerType.EXCULPATORY]


# --- double counting ---------------------------------------------------------

def test_marker_already_exemplified_by_the_top_playbook_is_not_counted_twice():
    """'kisi ko mat dena' is both a marker and why the isolation playbook retrieved.

    The retrieval must actually be corroborated for this to hold. Suppression assumes
    the retrieval score already reflects the marker, and an uncorroborated hit
    contributes nothing to reflect it with -- see
    test_markers_are_not_suppressed_when_retrieval_is_uncorroborated.
    """
    text = "Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe."
    markers = find_markers(text)
    cohort = [0.1, 0.12, 0.09]

    counted_twice = RetrievalResult(
        playbooks=[playbook(0.72)],
        cohort_similarities=cohort,
        top_similarity=0.72,
        top_doc_id="d1",
        top_doc_markers=[],
    )
    suppressed = RetrievalResult(
        playbooks=[playbook(0.72)],
        cohort_similarities=cohort,
        top_similarity=0.72,
        top_doc_id="d1",
        top_doc_markers=["MK_ISOLATION_DEMAND", "MK_URGENT_FINANCIAL_UPI"],
    )

    assert score_script(text, suppressed, markers).risk < score_script(
        text, counted_twice, markers
    ).risk


def test_exculpatory_markers_are_never_suppressed():
    """Suppression is one-directional by design: risk-lowering evidence always counts."""
    text = "Call Papa and ask him yourself. Will be home by 7 PM."
    markers = find_markers(text)
    retrieval = RetrievalResult(
        cohort_similarities=[0.1, 0.12, 0.09],
        top_similarity=0.72,
        top_doc_id="d1",
        top_doc_markers=["MK_EXCULPATORY_VERIFICATION_INVITE", "MK_EXCULPATORY_ROUTINE"],
    )
    result = score_script(text, retrieval, markers)
    assert len(result.exculpatory_markers) == 2


# --- shape and degenerate input ----------------------------------------------

def test_result_carries_the_retrieved_playbooks(retriever: Retriever):
    result = analyse(retriever, CLONE_EXTORTION)
    assert result.playbooks
    assert result.playbooks[0].source_url.startswith("https://")


def test_uncorroborated_retrieval_reports_no_playbooks(retriever: Retriever):
    """A citation on screen reads as evidence.

    Top-k always returns *something* — that is what top-k does. Passing a 0.2-similarity
    "KYC harvesting" hit through to the panel next to a benign call renders an accusation
    the score does not support.
    """
    result = analyse(retriever, FAMILY_CHECKIN)
    assert result.risk <= 0.10
    assert result.playbooks == []


def test_corroborated_retrieval_still_reports_its_playbooks(retriever: Retriever):
    assert analyse(retriever, CLONE_EXTORTION).playbooks


def test_intent_summary_is_populated(retriever: Retriever):
    assert analyse(retriever, CLONE_EXTORTION).intent_summary


def test_empty_transcript_scores_zero():
    result = score_script("", RetrievalResult.empty(), [])
    assert result.risk == 0.0


def test_missing_cohort_does_not_divide_by_zero():
    """An unbuilt or empty benign corpus must degrade, not explode."""
    result = score_script(
        "Send money now", RetrievalResult(top_similarity=0.8, cohort_similarities=[]), []
    )
    assert 0.0 <= result.risk <= 1.0


def test_degenerate_cohort_with_zero_variance_does_not_divide_by_zero():
    result = score_script(
        "Send money now",
        RetrievalResult(top_similarity=0.8, cohort_similarities=[0.4, 0.4, 0.4]),
        [],
    )
    assert 0.0 <= result.risk <= 1.0


def test_risk_stays_within_the_contract_bounds(retriever: Retriever):
    for text in (CLONE_EXTORTION, FAMILY_CHECKIN, BANK_IVR, GENUINE_UNUSUAL):
        assert 0.0 <= analyse(retriever, text).risk <= 1.0


def test_normalisation_details_are_reported_for_debugging(retriever: Retriever):
    details = analyse(retriever, CLONE_EXTORTION).details
    assert "z" in details and "r_ret" in details and "marker_delta" in details


# --- suppression must not discard evidence we never counted ------------------

def test_markers_are_not_suppressed_when_retrieval_is_uncorroborated():
    """Suppression assumes the retrieval score already reflects the marker.

    When the hit is too weak to cite, nothing is counting the marker, so dropping it
    throws away the only evidence there is.
    """
    retrieval = RetrievalResult(
        playbooks=[],
        cohort_similarities=[0.55] * 20,   # background just as similar -> low z
        top_similarity=0.58,
        top_doc_id="anch-x",
        top_doc_markers=["MK_URGENT_FINANCIAL_UPI"],
    )
    markers = find_markers("I need 20000 urgently for a deposit")
    result = score_script("I need 20000 urgently for a deposit", retrieval, markers)

    assert result.details["corroborated"] is False, "precondition"
    assert result.details["suppressed_markers"] == []
    assert result.details["marker_net_weight"] > 0


def test_markers_are_still_suppressed_when_retrieval_is_corroborated():
    """The original rule holds where its premise holds."""
    retrieval = RetrievalResult(
        playbooks=[playbook(0.95)],
        cohort_similarities=[0.1] * 20,    # background far away -> high z
        top_similarity=0.95,
        top_doc_id="anch-x",
        top_doc_markers=["MK_URGENT_FINANCIAL_UPI"],
    )
    markers = find_markers("I need 20000 urgently for a deposit")
    result = score_script("I need 20000 urgently for a deposit", retrieval, markers)

    assert result.details["corroborated"] is True, "precondition"
    assert result.details["suppressed_markers"] == ["MK_URGENT_FINANCIAL_UPI"]
