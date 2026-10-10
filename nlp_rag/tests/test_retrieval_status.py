"""`retrieval_status()` — the intent branch must be able to say it is running markers-only.

Before this existed, a BGE-m3 load failure left exactly one trace: a WARNING at startup,
then `details["retrieval_available"] = False` buried in every ScriptAnalysisResult. The
branch still returned a valid, lower-recall result, so nothing downstream could tell a
degraded intent branch from a healthy one (CLAUDE.md, "Silent failure is the recurring
bug in this codebase"). See `test_import_order.py` for the failure this guards.
"""

from __future__ import annotations

import pytest

from nlp_rag import api, embed
from nlp_rag.tests.fakes import FakeEncoder


@pytest.fixture(autouse=True)
def restore_api_state():
    """Put back whatever the root conftest preloaded, rather than resetting it."""
    saved = (api._retriever, api._configured, api._person_lookup, api._retrieval_error)
    yield
    api._retriever, api._configured, api._person_lookup, api._retrieval_error = saved


def test_unconfigured_branch_reports_not_configured():
    api.reset()
    status = api.retrieval_status()
    assert status["configured"] is False
    assert status["available"] is False


def test_a_wired_retriever_reports_available():
    api.configure(encoder=FakeEncoder())
    status = api.retrieval_status()
    assert status == {"configured": True, "available": True, "reason": None}


def test_an_encoder_that_fails_to_load_reports_why(monkeypatch):
    monkeypatch.setattr(embed, "load_encoder", lambda: None)
    monkeypatch.setattr(embed, "LAST_LOAD_ERROR", "RuntimeError: Lazy import failed")
    api.configure()
    status = api.retrieval_status()
    assert status["configured"] is True
    assert status["available"] is False
    assert "Lazy import failed" in status["reason"]


def test_a_broken_corpus_reports_why(monkeypatch):
    def broken(_path):
        raise ValueError("corpus is malformed")

    monkeypatch.setattr(api, "load_corpus", broken)
    api.configure(encoder=FakeEncoder())
    status = api.retrieval_status()
    assert status["available"] is False
    assert "corpus is malformed" in status["reason"]


def test_reconfiguring_successfully_clears_the_old_reason(monkeypatch):
    monkeypatch.setattr(embed, "load_encoder", lambda: None)
    api.configure()
    assert api.retrieval_status()["reason"]
    api.configure(encoder=FakeEncoder())
    assert api.retrieval_status()["reason"] is None


def test_load_encoder_records_the_exception(monkeypatch, tmp_path):
    class Boom:
        def __init__(self, *_a, **_k):
            raise RuntimeError("Lazy import of LazyModule failed")

    monkeypatch.setattr(embed, "BGEM3Encoder", Boom)
    assert embed.load_encoder(tmp_path) is None
    assert "Lazy import of LazyModule failed" in embed.LAST_LOAD_ERROR
