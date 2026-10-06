"""Item 16 / C4: voiceprints are biometric data — consent is recorded, deletion is real.

Under the DPDP Act 2023 a voiceprint is personal data processed on consent. Two gaps:

  * nothing recorded that anyone agreed to be enrolled;
  * `DELETE /api/persons/{id}` removed the SQLite rows but left `data/enrollments/<id>.npz`,
    which is the file `verify_speaker` actually reads — so a "deleted" person kept being
    matched on every call.

`REQUIRE_ENROLL_CONSENT` defaults off until the app and web send `consent`; when on, an
enrollment without it is refused before any audio is processed.
"""

from __future__ import annotations

import sqlite3

import pytest

import config

CLIPS = config.REPO_ROOT / "data" / "eval_set" / "clips"
needs_ecapa = pytest.mark.skipif(
    not (config.MODELS_DIR / "ecapa").is_dir() or not (CLIPS / "friend.wav").is_file(),
    reason="needs models/ecapa/ and data/eval_set/clips/",
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from audio_ml import enroll
    from server.main import app

    monkeypatch.setattr(enroll, "ENROLLMENTS_DIR", tmp_path / "enrollments")
    monkeypatch.setattr(config, "ENROLLMENTS_DIR", tmp_path / "enrollments")
    (tmp_path / "enrollments").mkdir()
    with TestClient(app) as c:
        c.enrollments = tmp_path / "enrollments"
        before = {p["person_id"] for p in c.get("/api/persons").json()}
        yield c
        for p in c.get("/api/persons").json():
            if p["person_id"] not in before:
                c.delete(f"/api/persons/{p['person_id']}")


def _enroll(client, consent=None, clip="friend"):
    data = {"name": "Consent test", "relation": "Friend"}
    if consent is not None:
        data["consent"] = "true" if consent else "false"
    with (CLIPS / f"{clip}.wav").open("rb") as fh:
        return client.post("/api/enroll", data=data, files={"file": (f"{clip}.wav", fh, "audio/wav")})


# --- the contract ------------------------------------------------------------------

def test_contract_fields_are_optional_and_default_to_none():
    from contracts import EnrolledPerson, EnrollmentRequest

    p = EnrolledPerson(person_id="p", name="n", relation="r")
    assert p.consent_recorded_at is None and p.consent_version is None
    assert EnrollmentRequest(name="n", relation="r").consent is False


def test_consent_is_not_required_by_default():
    assert config.REQUIRE_ENROLL_CONSENT is False
    assert config.CONSENT_TEXT_VERSION


# --- refusing without consent ----------------------------------------------------------

def test_required_consent_missing_is_refused_before_anything_is_stored(client, monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_ENROLL_CONSENT", True)
    before = client.get("/api/persons").json()
    for consent in (None, False):
        r = _enroll(client, consent=consent)
        assert r.status_code == 422, r.text
        assert "consent" in r.json()["detail"].lower()
    assert client.get("/api/persons").json() == before
    assert list(client.enrollments.glob("*.npz")) == []


@needs_ecapa
def test_given_consent_is_recorded_with_its_version(client, monkeypatch):
    monkeypatch.setattr(config, "REQUIRE_ENROLL_CONSENT", True)
    r = _enroll(client, consent=True)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["consent_recorded_at"]
    assert body["consent_version"] == config.CONSENT_TEXT_VERSION
    stored = client.get(f"/api/persons/{body['person_id']}").json()
    assert stored["consent_recorded_at"] == body["consent_recorded_at"]


@needs_ecapa
def test_enrolling_without_the_requirement_records_no_consent(client):
    r = _enroll(client)
    assert r.status_code == 201, r.text
    assert r.json()["consent_recorded_at"] is None


# --- deletion is real ---------------------------------------------------------------------

@needs_ecapa
def test_deleting_a_person_removes_the_voiceprint_verify_reads(client):
    from audio_ml.api import verify_speaker

    person_id = _enroll(client).json()["person_id"]
    probe = str(CLIPS / "friend_test.wav")
    assert verify_speaker(probe).best_match_id == person_id, "fixture: should match before delete"

    assert client.delete(f"/api/persons/{person_id}").status_code == 200
    assert not (client.enrollments / f"{person_id}.npz").exists()
    assert verify_speaker(probe).best_match_id != person_id


def test_delete_person_in_audio_ml_never_raises(tmp_path, monkeypatch):
    from audio_ml import enroll
    from audio_ml.api import delete_person

    monkeypatch.setattr(enroll, "ENROLLMENTS_DIR", tmp_path)
    (tmp_path / "p1.npz").write_bytes(b"x")
    assert delete_person("p1") is True and not (tmp_path / "p1.npz").exists()
    assert delete_person("never-enrolled") is False
    assert delete_person("../escape") is False


# --- migrating an existing database ---------------------------------------------------------

def test_an_existing_database_gains_the_consent_columns_without_losing_rows(tmp_path):
    from sqlalchemy import create_engine

    from server.database import migrate

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE persons (person_id TEXT PRIMARY KEY, name TEXT NOT NULL, "
                   "relation TEXT NOT NULL, phone_number TEXT, avatar_url TEXT, created_at DATETIME)")
        db.execute("INSERT INTO persons (person_id, name, relation) VALUES ('p1', 'Ma', 'Mother')")

    engine = create_engine(f"sqlite:///{path}")
    migrate(engine)
    migrate(engine)  # idempotent

    with sqlite3.connect(path) as db:
        cols = {row[1] for row in db.execute("PRAGMA table_info(persons)")}
        rows = db.execute("SELECT person_id, name, consent_recorded_at FROM persons").fetchall()
    assert {"consent_recorded_at", "consent_version"} <= cols
    assert rows == [("p1", "Ma", None)]
