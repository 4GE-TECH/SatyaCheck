"""Upgrade plan, Phase 6: request IDs and the Prometheus scrape endpoint."""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

import config
from server.main import app
from server.observability import RequestIdFilter, new_request_id, request_id_var


def test_every_response_carries_a_request_id_and_a_good_one_is_kept():
    client = TestClient(app)
    fresh = client.get("/api/health").headers["x-request-id"]
    assert len(fresh) == 16
    assert client.get("/api/health", headers={"X-Request-ID": "proxy-abc-123"}).headers["x-request-id"] == "proxy-abc-123"


def test_a_malformed_request_id_is_replaced_never_echoed():
    assert new_request_id("bad id\r\nSet-Cookie: x") != "bad id\r\nSet-Cookie: x"
    assert new_request_id("short") != "short"
    assert new_request_id("x" * 65) != "x" * 65


def test_log_records_carry_the_request_id():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "m", None, None)
    token = request_id_var.set("abcdef0123456789")
    try:
        RequestIdFilter().filter(record)
    finally:
        request_id_var.reset(token)
    assert record.request_id == "abcdef0123456789"


def test_metrics_label_routes_by_template_and_carry_no_call_data(monkeypatch):
    monkeypatch.setattr(config, "METRICS_TOKEN", "")
    monkeypatch.setattr(config, "SATYACHECK_ENV", "dev")
    client = TestClient(app)
    client.get("/api/screen/secret-session-id-123")
    body = client.get("/metrics").text
    assert 'route="/api/screen/{session_id}"' in body
    assert "secret-session-id-123" not in body
    assert "satyacheck_live_sessions" in body


def test_metrics_need_the_token_when_set_and_always_in_production(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(config, "METRICS_TOKEN", "scrape-me")
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer scrape-me"}).status_code == 200

    monkeypatch.setattr(config, "METRICS_TOKEN", "")
    monkeypatch.setattr(config, "SATYACHECK_ENV", "production")
    assert client.get("/metrics").status_code == 404
