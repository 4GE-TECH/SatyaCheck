"""A server whose intent branch came up markers-only must say so, loudly.

`nlp_rag.api.configure()` is called once in `lifespan()`. If BGE-m3 fails to load there
(see nlp_rag/tests/test_import_order.py), every later request is scored without
retrieval and nothing errors. These tests pin the two places that failure must surface:
an ERROR in the startup log, and a field on /api/health that the demo checklist reads.
"""

from __future__ import annotations

import logging

import pytest


@pytest.fixture
def boot(monkeypatch):
    """Start the app with nlp_rag wiring stubbed, so no model is loaded."""
    from fastapi.testclient import TestClient

    import nlp_rag.api as nlp_api
    from server.main import app

    def start(status: dict):
        monkeypatch.setattr(nlp_api, "configure", lambda **_kw: None)
        monkeypatch.setattr(nlp_api, "retrieval_status", lambda: status)
        return TestClient(app)

    return start


DOWN = {"configured": True, "available": False, "reason": "RuntimeError: Lazy import failed"}
UP = {"configured": True, "available": True, "reason": None}


def test_health_reports_retrieval_unavailable(boot):
    with boot(DOWN) as client:
        body = client.get("/api/health").json()
    assert body["nlp_retrieval_available"] is False
    assert "Lazy import failed" in body["nlp_retrieval_reason"]


def test_health_reports_retrieval_available(boot):
    with boot(UP) as client:
        body = client.get("/api/health").json()
    assert body["nlp_retrieval_available"] is True
    assert body["nlp_retrieval_reason"] is None


def test_startup_logs_an_error_when_retrieval_is_down(boot, caplog):
    with caplog.at_level(logging.ERROR, logger="satyacheck.server"):
        with boot(DOWN):
            pass
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("markers-only" in r.getMessage() for r in errors), [r.getMessage() for r in errors]


def test_startup_is_quiet_when_retrieval_is_up(boot, caplog):
    with caplog.at_level(logging.ERROR, logger="satyacheck.server"):
        with boot(UP):
            pass
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
