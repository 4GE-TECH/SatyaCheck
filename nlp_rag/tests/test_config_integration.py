"""nlp_rag reads C's knobs rather than keeping its own copies.

`config.py`: "Nobody hardcodes magic numbers inside their module — import from config
instead." It is C's file, so `nlp_rag.thresholds` reads through to it and falls back to
the values documented in `nlp_rag/PLAN.md` when a name is absent.
"""

from __future__ import annotations

import config
from contracts import RetrievedPlaybook
from nlp_rag import thresholds
from nlp_rag.retrieve import RetrievalResult
from nlp_rag.score import score_script


def playbook(similarity: float) -> RetrievedPlaybook:
    return RetrievedPlaybook(
        playbook_id="anch-x-001",
        title="Some advisory",
        category="Extortion",
        similarity_score=similarity,
        matched_excerpt="…",
        source_url="https://cybercrime.gov.in/",
        source_agency="I4C",
    )


# --- the knobs are read, not duplicated --------------------------------------

def test_top_k_comes_from_config():
    assert thresholds.RAG_TOP_K == config.RAG_TOP_K


def test_similarity_floor_comes_from_config():
    assert thresholds.RAG_SIMILARITY_THRESHOLD == config.RAG_SIMILARITY_THRESHOLD


def test_thresholds_owned_by_b_are_not_overridden_by_config():
    """config.py defines none of these, so B's documented defaults must survive."""
    assert thresholds.SCRIPT_Z0 == 4.0
    assert thresholds.CORROBORATION_FLOOR == 0.35


# --- the playbook gate is an AND ---------------------------------------------

def test_playbook_below_the_raw_similarity_floor_is_not_cited():
    """Corroborated against the cohort, but too weak in absolute terms to show."""
    weak = config.RAG_SIMILARITY_THRESHOLD - 0.1
    retrieval = RetrievalResult(
        playbooks=[playbook(weak)],
        cohort_similarities=[0.1, 0.1, 0.1],
        top_similarity=weak,
        top_doc_id="anch-x-001",
    )
    result = score_script("Send money now urgently", retrieval, [])

    assert result.details["r_ret"] >= thresholds.CORROBORATION_FLOOR
    assert result.playbooks == []


def test_playbook_clearing_both_gates_is_cited():
    strong = config.RAG_SIMILARITY_THRESHOLD + 0.2
    retrieval = RetrievalResult(
        playbooks=[playbook(strong)],
        cohort_similarities=[0.1, 0.1, 0.1],
        top_similarity=strong,
        top_doc_id="anch-x-001",
    )
    assert score_script("Send money now urgently", retrieval, []).playbooks


def test_uncorroborated_playbook_is_not_cited_even_above_the_raw_floor():
    """The other half of the AND: a high cosine that the cohort also scores highly."""
    strong = config.RAG_SIMILARITY_THRESHOLD + 0.2
    retrieval = RetrievalResult(
        playbooks=[playbook(strong)],
        cohort_similarities=[strong, strong, strong],  # background is just as similar
        top_similarity=strong,
        top_doc_id="anch-x-001",
    )
    result = score_script("Send money now urgently", retrieval, [])

    assert result.details["r_ret"] < thresholds.CORROBORATION_FLOOR
    assert result.playbooks == []


# --- model paths resolve under config.MODELS_DIR -----------------------------

def test_whisper_model_path_is_under_the_configured_models_dir():
    from nlp_rag import asr

    assert config.MODELS_DIR in asr.MODEL_DIR.parents


def test_encoder_model_path_is_under_the_configured_models_dir():
    from nlp_rag import embed

    assert config.MODELS_DIR in embed.MODEL_DIR.parents


def test_whisper_decoding_settings_come_from_config():
    from nlp_rag import asr

    assert asr.MODEL_SIZE == config.WHISPER_MODEL_SIZE
    assert asr.COMPUTE_TYPE == config.WHISPER_COMPUTE_TYPE
