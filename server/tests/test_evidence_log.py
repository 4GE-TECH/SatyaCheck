"""Item 17 / C5: a tamper-evident log of every guardian alert, persisted, holding no audio.

Each alert becomes a leaf in an RFC 6962-style Merkle tree (leaf = H(0x00 || data),
node = H(0x01 || left || right) — the domain separation prevents a node being passed off
as a leaf). Leaves and every historical root live in SQLite, not memory, so a restart
does not reset the chain. The root and an inclusion proof go on the PDF report: anyone
holding an old report can detect a rewritten log.

Expected values below are built by hand from the hash rules, not by calling the code
under test, and the empty-input leaf hash is the RFC 6962 constant.
"""

from __future__ import annotations

import hashlib
import json
import threading

import pytest
from sqlalchemy import create_engine, text

import config
from contracts import EvidenceAnchor, GuardianAlert, IncidentReportPacket, TrustBand
from server import evidence
from server.tests.isolated_db import isolated_db  # noqa: F401  (fixture)


def H(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def leaf(d: bytes) -> bytes:
    return H(b"\x00" + d)


def node(a: bytes, b: bytes) -> bytes:
    return H(b"\x01" + a + b)


# --- the hash rules -------------------------------------------------------------------

def test_leaf_hash_of_empty_input_is_the_rfc_6962_constant():
    assert evidence.leaf_hash(b"").hex() == (
        "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"
    )


def test_empty_tree_root_is_the_hash_of_nothing():
    assert evidence.merkle_root([]) == H(b"")


def test_roots_match_hand_built_trees():
    d = [bytes([i]) for i in range(5)]
    L = [leaf(x) for x in d]
    assert evidence.merkle_root(L[:1]) == L[0]
    assert evidence.merkle_root(L[:2]) == node(L[0], L[1])
    assert evidence.merkle_root(L[:3]) == node(node(L[0], L[1]), L[2])
    # n=5: split at the largest power of two below 5, i.e. 4 | 1. No leaf duplication.
    assert evidence.merkle_root(L[:5]) == node(node(node(L[0], L[1]), node(L[2], L[3])), L[4])


@pytest.mark.parametrize("n", range(1, 12))
def test_every_inclusion_proof_verifies(n):
    leaves = [leaf(bytes([i])) for i in range(n)]
    root = evidence.merkle_root(leaves)
    for i in range(n):
        path = evidence.audit_path(i, leaves)
        assert evidence.verify_inclusion(leaves[i], i, n, path, root)


def test_a_proof_fails_for_the_wrong_leaf_or_index():
    leaves = [leaf(bytes([i])) for i in range(6)]
    root = evidence.merkle_root(leaves)
    path = evidence.audit_path(2, leaves)
    assert not evidence.verify_inclusion(leaf(b"forged"), 2, 6, path, root)
    assert not evidence.verify_inclusion(leaves[2], 3, 6, path, root)


# --- what gets hashed ---------------------------------------------------------------------

def _alert(i: int = 0, **kw) -> GuardianAlert:
    base = dict(alert_id=f"alert_{i:04d}", session_id=f"session_{i % 3}", trust_score=21.9,
                band=TrustBand.HIGH_RISK, caller_name_or_number="+919876543210",
                summary="High risk — synthetic voice", key_reasons=["a", "b"],
                audio_sha256="ab" * 32, timestamp="2026-10-06T10:00:00+00:00")
    base.update(kw)
    return GuardianAlert(**base)


def test_canonical_form_is_deterministic_and_carries_no_caller_identity():
    a = evidence.canonical_alert(_alert())
    assert a == evidence.canonical_alert(_alert())
    body = json.loads(a)
    assert "caller_name_or_number" not in body
    assert body["audio_sha256"] == "ab" * 32
    assert list(body) == sorted(body), "keys must be sorted for a stable hash"


# --- the persisted log ------------------------------------------------------------------------

@pytest.fixture
def log(tmp_path):
    return evidence.EvidenceLog(create_engine(f"sqlite:///{tmp_path / 'ev.db'}"))


def test_appends_build_the_same_root_as_the_pure_function(log):
    anchors = [log.append(_alert(i)) for i in range(5)]
    leaves = [leaf(evidence.canonical_alert(_alert(i))) for i in range(5)]
    assert [a.leaf_index for a in anchors] == list(range(5))
    assert log.root().root_hash == evidence.merkle_root(leaves).hex()
    assert log.root().tree_size == 5


def test_the_log_survives_a_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'ev.db'}"
    first = evidence.EvidenceLog(create_engine(url))
    for i in range(3):
        first.append(_alert(i))
    again = evidence.EvidenceLog(create_engine(url))
    assert again.root() == first.root()
    assert again.proof("alert_0001").leaf_index == 1


def test_a_proof_from_the_log_verifies_against_its_root(log):
    for i in range(7):
        log.append(_alert(i))
    anchor = log.proof("alert_0004")
    assert isinstance(anchor, EvidenceAnchor)
    assert evidence.verify_inclusion(
        bytes.fromhex(anchor.leaf_hash), anchor.leaf_index, anchor.tree_size,
        [bytes.fromhex(h) for h in anchor.audit_path], bytes.fromhex(anchor.root_hash),
    )


def test_editing_a_stored_alert_is_detected(log, tmp_path):
    for i in range(4):
        log.append(_alert(i))
    assert log.verify_all()
    with log.engine.begin() as conn:
        conn.execute(text("UPDATE evidence_leaves SET canonical_json = replace(canonical_json, "
                          "'21.9', '91.9') WHERE leaf_index = 2"))
    assert not log.verify_all()


def test_rewriting_a_leaf_and_its_hash_is_still_detected_by_the_recorded_roots(log):
    for i in range(4):
        log.append(_alert(i))
    forged = evidence.canonical_alert(_alert(2, trust_score=95.0))
    with log.engine.begin() as conn:
        conn.execute(text("UPDATE evidence_leaves SET canonical_json = :j, leaf_hash = :h "
                          "WHERE leaf_index = 2"),
                     {"j": forged.decode(), "h": leaf(forged).hex()})
    assert not log.verify_all()


def test_the_same_alert_is_logged_once(log):
    first = log.append(_alert(1))
    assert log.append(_alert(1)) == first
    assert log.root().tree_size == 1


def test_concurrent_appends_leave_no_gaps(log):
    def worker(base):
        for i in range(10):
            log.append(_alert(base * 10 + i))

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert log.root().tree_size == 80
    assert log.verify_all()


def test_an_unknown_alert_has_no_proof(log):
    assert log.proof("nope") is None


# --- wiring: guardian, endpoints, report ---------------------------------------------------------

@pytest.fixture
def wired(tmp_path, monkeypatch):
    test_log = evidence.EvidenceLog(create_engine(f"sqlite:///{tmp_path / 'ev.db'}"))
    monkeypatch.setattr(evidence, "_default_log", test_log)
    return test_log


def test_the_flag_defaults_off():
    assert config.ENABLE_EVIDENCE_LOG is False


def test_published_alerts_are_logged_only_when_enabled(wired, monkeypatch):
    import asyncio

    from contracts import create_mock_fixture
    from server.guardian import publish_alert_from_response

    red = create_mock_fixture("red")
    asyncio.run(publish_alert_from_response(red))
    assert wired.root().tree_size == 0
    monkeypatch.setattr(config, "ENABLE_EVIDENCE_LOG", True)
    asyncio.run(publish_alert_from_response(red))
    assert wired.root().tree_size == 1


def test_endpoints_serve_the_root_and_a_proof(wired, isolated_db):
    """A proof is served only to the account that owns the alert's session; another
    account's alert answers exactly like a missing one."""
    from fastapi.testclient import TestClient

    from server.database import ScreeningSession
    from server.main import app

    with isolated_db() as db:
        db.add(ScreeningSession(session_id="session_2", owner_id=config.DEV_OWNER_ID, status="complete"))
        db.add(ScreeningSession(session_id="session_1", owner_id="account-b", status="complete"))
        db.commit()
    for i in range(3):
        wired.append(_alert(i))
    c = TestClient(app)
    root = c.get("/api/evidence/root").json()
    proof = c.get("/api/evidence/alert_0002/proof").json()
    assert c.get("/api/evidence/nope/proof").status_code == 404
    assert c.get("/api/evidence/alert_0001/proof").status_code == 404, "another account's proof"
    assert root["tree_size"] == 3
    assert proof["root_hash"] == root["root_hash"] and proof["leaf_index"] == 2


def test_the_report_carries_the_sessions_latest_anchor(wired):
    from contracts import create_mock_fixture
    from server.report_router import _build_report_packet

    wired.append(_alert(0, session_id="session_mock_red"))
    wired.append(_alert(3, session_id="session_mock_red"))
    packet = _build_report_packet(create_mock_fixture("red"), "RPT_X")
    assert isinstance(packet, IncidentReportPacket)
    assert packet.evidence is not None and packet.evidence.alert_id == "alert_0003"


def test_a_report_with_no_logged_alert_has_no_anchor(wired):
    from contracts import create_mock_fixture
    from server.report_router import _build_report_packet

    assert _build_report_packet(create_mock_fixture("red"), "RPT_X").evidence is None


def test_the_pdf_prints_the_root(wired, tmp_path):
    pytest.importorskip("reportlab")
    from contracts import create_mock_fixture
    from server.report_router import _build_report_packet, _generate_pdf

    wired.append(_alert(0, session_id="session_mock_red"))
    packet = _build_report_packet(create_mock_fixture("red"), "RPT_X")
    out = tmp_path / "r.pdf"
    assert _generate_pdf(packet, out)
    assert packet.evidence.root_hash[:16].encode() in b"".join(_pdf_streams(out.read_bytes()))


def _pdf_streams(raw: bytes) -> list[bytes]:
    """reportlab writes page content as ASCII85 over Flate; undo both (stdlib only)."""
    import base64
    import re
    import zlib

    out = []
    for body in re.findall(rb"(?<!end)stream\r?\n(.*?)endstream", raw, re.S):
        data = body.strip()
        if data.endswith(b"~>"):
            data = base64.a85decode(data[:-2].replace(b"\n", b"").replace(b"\r", b""))
        try:
            out.append(zlib.decompress(data))
        except zlib.error:
            out.append(data)
    return out
