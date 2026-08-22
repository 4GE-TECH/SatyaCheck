"""The measurement instrument, tested for arithmetic rather than for numbers.

`eval_retrieval` is what decides whether a corpus change helped. If the metric itself is
wrong, growth looks like progress in exactly the cases where it is regression — so what
is asserted here is the *computation*: precision counts what it claims to count, and the
benign cohort is scored leave-one-out.

Nothing here asserts a model-dependent score. Those move with the corpus by design, which
is the whole reason the baseline file exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nlp_rag import eval_retrieval, thresholds
from nlp_rag.corpus_loader import load_corpus
from nlp_rag.retrieve import Retriever
from nlp_rag.tests.fakes import FakeEncoder

CORPUS_DIR = Path(__file__).parent.parent / "corpus"


@pytest.fixture(scope="module")
def corpus():
    return load_corpus(CORPUS_DIR)


@pytest.fixture(scope="module")
def report(corpus):
    return eval_retrieval.evaluate(Retriever(FakeEncoder(), corpus), corpus)


# --- precision arithmetic ----------------------------------------------------

def test_a_hit_at_rank_one_counts():
    assert eval_retrieval.rank_of("b", ["b", "c", "d"]) == 1


def test_a_hit_at_rank_three_counts():
    assert eval_retrieval.rank_of("d", ["b", "c", "d"]) == 3


def test_a_hit_outside_the_cutoff_does_not_count():
    assert eval_retrieval.rank_of("z", ["b", "c", "d"]) is None


def test_precision_is_the_fraction_of_queries_with_a_hit():
    assert eval_retrieval.mean([True, True, False, False]) == 0.5


def test_precision_of_nothing_is_zero_not_a_division_error():
    assert eval_retrieval.mean([]) == 0.0


# --- the held-out pass -------------------------------------------------------

def test_every_heldout_document_is_evaluated(report, corpus):
    assert len(report.heldout) == len(corpus.heldout)


def test_retrieved_ids_are_resolved_to_anchors(report, corpus):
    """A variant hit counts for the anchor it inherits from.

    `expected_anchor` is an anchor id, so comparing it against raw retrieved ids would
    score every variant hit as a miss — and variants are most of what retrieves.
    """
    anchor_ids = {a.id for a in corpus.anchors}
    for outcome in report.heldout:
        assert set(outcome.retrieved) <= anchor_ids, outcome.retrieved


def test_a_strict_hit_is_also_a_family_hit(report):
    """Strict implies family. If it does not, one of the two is mislabelled."""
    for outcome in report.heldout:
        if outcome.strict_hit:
            assert outcome.family_hit, outcome.doc_id


def test_heldout_text_is_never_retrieved_as_its_own_answer(report, corpus):
    heldout_ids = {d.id for d in corpus.heldout}
    for outcome in report.heldout:
        assert not (set(outcome.retrieved) & heldout_ids)


# --- the benign pass, leave-one-out ------------------------------------------

def test_every_benign_document_is_scored(report, corpus):
    assert len(report.benign) == len(corpus.benign)


def test_a_benign_document_is_excluded_from_its_own_cohort(corpus):
    """Its own ~1.0 self-similarity would otherwise sit in the background it is
    normalised against, inflating the mean and understating its own risk."""
    retriever = Retriever(FakeEncoder(), corpus)
    doc = corpus.benign[0]
    retrieval = retriever.search(doc.text, k=3)

    held_out = eval_retrieval.without_self(retrieval, doc.id)

    assert doc.id in retrieval.cohort_ids, "precondition: it is in its own cohort"
    assert doc.id not in held_out.cohort_ids
    assert len(held_out.cohort_similarities) == len(retrieval.cohort_similarities) - 1


def test_leaving_one_out_keeps_similarities_aligned_with_ids(corpus):
    retriever = Retriever(FakeEncoder(), corpus)
    doc = corpus.benign[0]
    retrieval = retriever.search(doc.text, k=3)
    dropped_at = retrieval.cohort_ids.index(doc.id)
    expected = [
        s for i, s in enumerate(retrieval.cohort_similarities) if i != dropped_at
    ]

    assert eval_retrieval.without_self(retrieval, doc.id).cohort_similarities == expected


def test_leaving_out_an_absent_id_changes_nothing(corpus):
    retriever = Retriever(FakeEncoder(), corpus)
    retrieval = retriever.search("some query", k=3)
    assert eval_retrieval.without_self(retrieval, "not-a-doc") == retrieval


def test_a_false_positive_is_a_benign_document_at_or_above_the_amber_floor(report):
    for outcome in report.benign:
        assert outcome.flagged == (outcome.risk >= thresholds.AMBER_FLOOR), outcome.doc_id


def test_the_false_positive_rate_matches_the_flagged_documents(report):
    flagged = sum(1 for o in report.benign if o.flagged)
    assert report.benign_false_positive_rate == pytest.approx(flagged / len(report.benign))


# --- the report itself -------------------------------------------------------

def test_the_report_serialises_to_json(report):
    import json

    assert json.loads(json.dumps(report.to_dict()))["p_at_k_strict"] is not None


def test_the_report_records_which_encoder_produced_it(report):
    """A baseline captured under the fake encoder must never be compared against one
    captured under BGE-m3. The numbers are not on the same scale."""
    assert "Fake" in report.encoder


def test_the_report_names_its_cutoff(report):
    assert report.k == thresholds.RAG_TOP_K


def test_calibration_rows_cover_the_documented_targets(report):
    assert {row.name for row in report.calibration} >= {
        "clone_extortion",
        "family_checkin",
        "bank_ivr",
    }


# --- recall: the axis the harness was missing --------------------------------
# P@k says the right advisory was retrieved. It says nothing about the number the user
# sees, and a system can retrieve perfectly while scoring every call green. The harness
# reported a clean run at 100% P@3 while 36% of known scams scored below caution.

def test_every_heldout_document_is_scored(report, corpus):
    assert all(o.risk > 0.0 for o in report.heldout)


def test_amber_recall_counts_heldout_docs_at_or_above_the_floor(report):
    expected = sum(1 for o in report.heldout if o.risk >= thresholds.AMBER_FLOOR)
    assert report.scam_recall_amber == pytest.approx(expected / len(report.heldout))


def test_high_risk_recall_uses_the_high_risk_threshold(report):
    expected = sum(1 for o in report.heldout if o.risk >= thresholds.SCRIPT_HIGH_RISK)
    assert report.scam_recall_high_risk == pytest.approx(
        expected / len(report.heldout)
    )


def test_silent_scams_are_exactly_those_below_the_amber_floor(report):
    assert set(report.silent_scams) == {
        o.doc_id for o in report.heldout if o.risk < thresholds.AMBER_FLOOR
    }


def test_recall_by_language_partitions_the_heldout_set(report):
    assert sum(n for n, _ in report.recall_by_lang.values()) == len(report.heldout)


def test_recall_by_language_covers_every_language_present(report, corpus):
    assert set(report.recall_by_lang) == {d.lang for d in corpus.heldout}


# --- the regression gate ------------------------------------------------------

def test_a_material_recall_drop_is_a_regression(report):
    baseline = report.to_dict() | {"scam_recall_amber": report.scam_recall_amber + 0.2}
    assert any("scam_recall_amber" in f for f in eval_retrieval.regressions(report, baseline))


def test_a_material_false_positive_rise_is_a_regression(report):
    baseline = report.to_dict() | {
        "benign_false_positive_rate": report.benign_false_positive_rate - 0.2
    }
    assert any(
        "benign_false_positive" in f for f in eval_retrieval.regressions(report, baseline)
    )


def test_noise_within_tolerance_is_not_a_regression(report):
    nudge = eval_retrieval.REGRESSION_TOLERANCE / 2
    baseline = report.to_dict() | {"scam_recall_amber": report.scam_recall_amber + nudge}
    assert eval_retrieval.regressions(report, baseline) == []


def test_an_improvement_is_never_a_regression(report):
    baseline = report.to_dict() | {"scam_recall_amber": 0.0, "p_at_k_strict": 0.0}
    assert eval_retrieval.regressions(report, baseline) == []


def test_no_baseline_means_nothing_to_regress_against(report):
    assert eval_retrieval.regressions(report, None) == []


def test_a_baseline_from_a_different_test_set_is_not_compared(report):
    """Growing the held-out set 16 -> 50 moved P@3 from 100% to 94%. That is a harder
    test, not a regression, and comparing across the two reported failures that had not
    happened."""
    baseline = report.to_dict()
    baseline["corpus_counts"] = dict(baseline["corpus_counts"], heldout=16)
    baseline["scam_recall_amber"] = 1.0
    assert eval_retrieval.regressions(report, baseline) == []


def test_a_baseline_from_a_different_benign_cohort_is_not_compared(report):
    baseline = report.to_dict()
    baseline["corpus_counts"] = dict(baseline["corpus_counts"], benign=82)
    baseline["benign_false_positive_rate"] = 0.0
    assert eval_retrieval.regressions(report, baseline) == []
