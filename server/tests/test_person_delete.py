"""Upgrade plan, Phase 0 step 5: deleting a person removes everything about them.

One transaction cascades to voiceprints, challenge secrets, guardian subscriptions and
idempotency keys. The legacy .npz goes only after that commits, so a failed delete never
leaves a person whose voiceprint file is already gone.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

import config
from server.tests.isolated_db import isolated_db  # noqa: F401  (fixture)


OWNER = config.DEV_OWNER_ID   # TestClient requests carry no token: dev mode


def _unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(192).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def person(isolated_db, tmp_path, monkeypatch):
    from audio_ml import enroll
    from server import voiceprint_store
    from server.database import EnrollIdempotency, GuardianSubscription, Person, SharedSecret

    monkeypatch.setattr(enroll, "ENROLLMENTS_DIR", tmp_path)
    np.savez(tmp_path / "p1.npz", wb=_unit(1), nb8k=_unit(2), name="Papa", relationship="Father",
             n_samples=1, enrolled_at="2026-09-01")
    with isolated_db() as db:
        db.add(Person(person_id="p1", owner_id=OWNER, name="Papa", relation="Father"))
        db.add(Person(person_id="p2", owner_id=OWNER, name="Ma", relation="Mother"))
        db.flush()
        voiceprint_store.save_voiceprints(db, OWNER, "p1", {"wb": _unit(1), "nb8k_sim": _unit(2)},
                                          duration_s=20, snr_db=20)
        voiceprint_store.save_voiceprints(db, OWNER, "p2", {"wb": _unit(3)}, duration_s=20, snr_db=20)
        db.add(SharedSecret(secret_id="s1", person_id="p1", question="Pet?", answer_hash="h"))
        db.add(GuardianSubscription(sub_id="g1", owner_id=OWNER, person_id="p1", endpoint_label="Rahul's phone"))
        db.add(EnrollIdempotency(owner_id=OWNER, key="k1", person_id="p1", fingerprint="f"))
        db.commit()
    return tmp_path


def _counts(isolated_db, person_id):
    from server.database import EnrollIdempotency, GuardianSubscription, Person, SharedSecret, Voiceprint

    with isolated_db() as db:
        return {
            model.__tablename__: db.query(model).filter(model.person_id == person_id).count()
            for model in (Person, Voiceprint, SharedSecret, GuardianSubscription, EnrollIdempotency)
        }


def test_delete_removes_every_row_and_the_legacy_file(isolated_db, person):
    from server.main import app

    r = TestClient(app).delete("/api/persons/p1")
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": "p1", "voiceprint_deleted": True, "legacy_file_removed": True}
    assert set(_counts(isolated_db, "p1").values()) == {0}
    assert not (person / "p1.npz").exists()
    assert _counts(isolated_db, "p2")["voiceprints"] == 1, "another person was touched"


def test_a_deleted_person_is_no_longer_a_candidate(isolated_db, person, monkeypatch):
    from server.main import app
    from server.orchestrator import _speaker_candidates

    monkeypatch.setattr(config, "LEGACY_NPZ_FALLBACK", True)
    assert "p1" in {c["person_id"] for c in _speaker_candidates(OWNER)[0]}
    TestClient(app).delete("/api/persons/p1")
    assert "p1" not in {c["person_id"] for c in _speaker_candidates(OWNER)[0]}


def test_a_failed_delete_keeps_everything(isolated_db, person, monkeypatch):
    from sqlalchemy.orm import Session

    from server.main import app

    def failing_commit(self):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(Session, "commit", failing_commit)
    r = TestClient(app).delete("/api/persons/p1")
    monkeypatch.undo()
    assert r.status_code == 500
    assert _counts(isolated_db, "p1")["voiceprints"] == 2
    assert (person / "p1.npz").is_file(), "the file went although the rows stayed"


def test_deleting_someone_unknown_is_404(isolated_db, person):
    from server.main import app

    assert TestClient(app).delete("/api/persons/nobody").status_code == 404


def test_another_owners_person_cannot_be_deleted(isolated_db, person):
    from server.database import Person
    from server.main import app

    with isolated_db() as db:
        db.add(Person(person_id="p_theirs", owner_id="owner-b", name="X", relation="Y"))
        db.commit()
    assert TestClient(app).delete("/api/persons/p_theirs").status_code == 404
    assert _counts(isolated_db, "p_theirs")["persons"] == 1
