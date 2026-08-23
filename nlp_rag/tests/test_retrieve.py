"""Retrieval returns anchor-backed playbooks and the benign cohort scores beside them.

The cohort scores are not incidental output — scoring cannot normalise without them,
and without normalisation every transcript lands mid-range. See `nlp_rag/PLAN.md` §5.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nlp_rag.corpus_loader import load_corpus
from nlp_rag.retrieve import Retriever
from nlp_rag.tests.fakes import FakeEncoder

CORPUS_DIR = Path(__file__).parent.parent / "corpus"

SCAM_TRANSCRIPT = (
    "Papa emergency ho gaya hai, police ne pakad liya hai. "
    "Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe."
)
BENIGN_TRANSCRIPT = "Hi Ma, I just reached the office. Will be home by 7 PM today."


@pytest.fixture(scope="module")
def retriever() -> Retriever:
    return Retriever(FakeEncoder(), load_corpus(CORPUS_DIR))


# --- what comes back ---------------------------------------------------------

def test_scam_transcript_retrieves_a_playbook(retriever: Retriever):
    result = retriever.search(SCAM_TRANSCRIPT, k=3)
    assert result.playbooks


def test_retrieved_playbook_cites_an_anchor_not_the_matched_variant(retriever: Retriever):
    """The variant is what matched; the anchor is what gets cited."""
    result = retriever.search(SCAM_TRANSCRIPT, k=3)
    top = result.playbooks[0]
    assert top.playbook_id.startswith("anch-")
    assert top.source_url.startswith("https://")
    assert top.source_agency


def test_hinglish_extortion_retrieves_the_family_emergency_anchor(retriever: Retriever):
    result = retriever.search(SCAM_TRANSCRIPT, k=3)
    assert result.playbooks[0].playbook_id == "anch-family-emergency-001"


def test_results_are_ordered_by_descending_similarity(retriever: Retriever):
    result = retriever.search(SCAM_TRANSCRIPT, k=5)
    scores = [p.similarity_score for p in result.playbooks]
    assert scores == sorted(scores, reverse=True)


def test_k_limits_the_number_of_playbooks(retriever: Retriever):
    assert len(retriever.search(SCAM_TRANSCRIPT, k=2).playbooks) == 2


# --- the benign cohort -------------------------------------------------------

def test_benign_documents_are_never_returned_as_playbooks(retriever: Retriever):
    result = retriever.search(BENIGN_TRANSCRIPT, k=5)
    assert all(not p.playbook_id.startswith("benign-") for p in result.playbooks)


def test_cohort_similarities_are_reported_for_normalisation(retriever: Retriever):
    result = retriever.search(SCAM_TRANSCRIPT, k=3)
    assert len(result.cohort_similarities) == len(load_corpus(CORPUS_DIR).benign)


def test_scam_transcript_scores_higher_against_playbooks_than_the_cohort(retriever: Retriever):
    """The separation normalisation depends on. If this inverts, scoring is meaningless."""
    result = retriever.search(SCAM_TRANSCRIPT, k=3)
    assert result.top_similarity > max(result.cohort_similarities)


def test_benign_transcript_does_not_outscore_the_cohort(retriever: Retriever):
    result = retriever.search(BENIGN_TRANSCRIPT, k=3)
    assert result.top_similarity < max(result.cohort_similarities)


# --- span reporting, used by scoring to suppress double-counting -------------

def test_top_document_id_is_reported(retriever: Retriever):
    result = retriever.search(SCAM_TRANSCRIPT, k=3)
    assert result.top_doc_id == "var-family-emergency-001-hi-latn"


# --- degenerate input --------------------------------------------------------

def test_empty_query_retrieves_nothing(retriever: Retriever):
    result = retriever.search("", k=3)
    assert result.playbooks == []
    assert result.top_similarity == 0.0


def test_whitespace_query_retrieves_nothing(retriever: Retriever):
    assert retriever.search("   \n  ", k=3).playbooks == []
