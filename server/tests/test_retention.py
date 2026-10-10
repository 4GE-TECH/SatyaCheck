"""Upgrade plan, Phase 1: retention and deletion cover everything.

  * the retention sweep removes call audio after RETENTION_AUDIO_DAYS and derived results
    (sessions, screenings with their transcripts, PDF reports) after RETENTION_RESULTS_DAYS;
    voiceprints stay until their person or account is deleted;
  * deleting an account removes every row and file of that account, and nothing of anyone
    else's;
  * production refuses the dev-only local copy of call audio.
"""

from __future__ import annotations

import importlib
import os
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from fastapi.testclient import TestClient

import config
from contracts import create_mock_fixture
from server.tests.auth_helpers import signed_in  # noqa: F401  (fixture)
from server.tests.isolated_db import isolated_db  # noqa: F401  (fixture)

A, B = "account-a", "account-b"
NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def _unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(192).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "reports")
    (tmp_path / "reports").mkdir()
    (tmp_path / "sessions").mkdir()
    return tmp_path


def _age(path, days: float) -> None:
    t = (NOW - timedelta(days=days)).timestamp()
    os.utime(path, (t, t))


def _call(db_factory, files, owner, session_id, age_days):
    """One stored call: session + result rows, retained audio, a PDF report."""
    from server.database import ScreeningResult, ScreeningSession

    created = NOW - timedelta(days=age_days)
    with db_factory() as db:
        db.add(ScreeningSession(session_id=session_id, owner_id=owner, status="complete", created_at=created))
        db.add(ScreeningResult(owner_id=owner, session_id=session_id, processing_ms=1.0, is_final=True,
                               response_json=create_mock_fixture("red").model_dump_json(), created_at=created))
        db.commit()
    audio = files / "sessions" / session_id
    audio.mkdir()
    (audio / "chunk_0000.wav").write_bytes(b"RIFF")
    _age(audio / "chunk_0000.wav", age_days)
    _age(audio, age_days)
    pdf = files / "reports" / f"RPT_{session_id[:12].upper()}.pdf"
    pdf.write_bytes(b"%PDF")
    _age(pdf, age_days)


def _person(db_factory, owner, person_id):
    from server import voiceprint_store
    from server.database import Person

    with db_factory() as db:
        db.add(Person(person_id=person_id, owner_id=owner, name="P", relation="R",
                      created_at=NOW - timedelta(days=400)))
        db.flush()
        voiceprint_store.save_voiceprints(db, owner, person_id, {"wb": _unit(1)}, duration_s=20, snr_db=20)
        voiceprint_store.add_flagged_voice(db, owner, _unit(2), "kyc")
        db.commit()


def _sessions(db_factory):
    from server.database import ScreeningResult, ScreeningSession

    with db_factory() as db:
        return (sorted(s.session_id for s in db.query(ScreeningSession)),
                sorted(r.session_id for r in db.query(ScreeningResult)))


# --- the sweep ---------------------------------------------------------------------------------

def test_the_sweep_ages_out_audio_then_results_and_keeps_voiceprints(isolated_db, files):
    from server import retention, voiceprint_store

    _person(isolated_db, A, "pa")
    _call(isolated_db, files, A, "fresh", age_days=1)
    _call(isolated_db, files, A, "month", age_days=45)     # audio expired, results kept
    _call(isolated_db, files, B, "old", age_days=120)      # everything expired

    counts = retention.sweep(isolated_db, now=NOW)

    assert _sessions(isolated_db) == (["fresh", "month"], ["fresh", "month"])
    assert (files / "sessions" / "fresh").is_dir()
    assert not (files / "sessions" / "month").exists() and not (files / "sessions" / "old").exists()
    assert (files / "reports" / "RPT_MONTH.pdf").is_file()
    assert not (files / "reports" / "RPT_OLD.pdf").exists()
    with isolated_db() as db:
        assert len(voiceprint_store.get_candidates(db, A)) == 1, "voiceprints are not on a timer"
        assert len(voiceprint_store.get_flagged(db, A)) == 1
    assert counts == {"sessions": 1, "screenings": 1, "llm_shadow": 0, "audio_dirs": 2, "reports": 1}


def test_the_sweep_is_idempotent(isolated_db, files):
    from server import retention

    _call(isolated_db, files, A, "old", age_days=120)
    retention.sweep(isolated_db, now=NOW)
    assert retention.sweep(isolated_db, now=NOW) == {"sessions": 0, "screenings": 0, "llm_shadow": 0,
                                                      "audio_dirs": 0, "reports": 0}


# --- deleting an account --------------------------------------------------------------------

def test_deleting_an_account_removes_everything_of_it_and_nothing_else(isolated_db, files, signed_in, monkeypatch):
    from server.database import (ConsentRecord, FlaggedVoice, GuardianSubscription, Person, ScreeningResult,
                                 ScreeningSession, Voiceprint)
    from server.main import app

    for owner, person, session in ((A, "pa", "call-a"), (B, "pb", "call-b")):
        _person(isolated_db, owner, person)
        _call(isolated_db, files, owner, session, age_days=1)
        with isolated_db() as db:
            db.add(ConsentRecord(consent_id=f"c-{owner}", owner_id=owner, person_id=person,
                                 consent_text_version="v", recorded_by=owner))
            db.add(GuardianSubscription(sub_id=f"g-{owner}", owner_id=owner, person_id=person))
            db.commit()

    client = TestClient(app)
    assert client.delete("/api/account", headers=signed_in.headers(A)).status_code == 400, "needs confirm"
    r = client.delete("/api/account", params={"confirm": "DELETE"}, headers=signed_in.headers(A))
    assert r.status_code == 200, r.text

    with isolated_db() as db:
        for model in (Person, ScreeningSession, ScreeningResult, FlaggedVoice, ConsentRecord, GuardianSubscription):
            owners = {row.owner_id for row in db.query(model)}
            assert owners == {B}, f"{model.__tablename__}: {owners}"
        assert {v.person_id for v in db.query(Voiceprint)} == {"pb"}
    assert not (files / "sessions" / "call-a").exists() and (files / "sessions" / "call-b").is_dir()
    assert not (files / "reports" / "RPT_CALL-A.pdf").exists() and (files / "reports" / "RPT_CALL-B.pdf").is_file()


def test_account_deletion_requires_sign_in(isolated_db, signed_in):
    from server.main import app

    assert TestClient(app).delete("/api/account", params={"confirm": "DELETE"}).status_code == 401


# --- production refuses the local audio copy -------------------------------------------------

def test_production_never_retains_session_audio(monkeypatch):
    monkeypatch.setenv("SATYACHECK_ENV", "production")
    monkeypatch.setenv("RETAIN_SESSION_AUDIO", "true")
    try:
        assert importlib.reload(config).RETAIN_SESSION_AUDIO is False
    finally:
        monkeypatch.delenv("SATYACHECK_ENV")
        monkeypatch.delenv("RETAIN_SESSION_AUDIO")
        importlib.reload(config)
