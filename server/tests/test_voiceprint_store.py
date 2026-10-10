"""Upgrade plan, Phase 0 step 3: the database is where verification finds voiceprints.

`server/voiceprint_store.py` is the one place vectors are written and read. It validates
every vector, keys rows by `(person_id, condition, model_version)` so re-enrollment
replaces, and hands `verify_speaker` its candidates.
"""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest

import config
from server.tests.isolated_db import isolated_db  # noqa: F401  (fixture)


def _unit(seed: int, dim: int = 192) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


OWNER = "owner-a"


def _person(db, person_id="p1", name="Papa", relation="Father", owner=OWNER):
    from server.database import Person

    db.add(Person(person_id=person_id, owner_id=owner, name=name, relation=relation))
    db.flush()


# --- validation ------------------------------------------------------------------------------

def test_validate_renormalises_a_good_vector():
    from server.voiceprint_store import validate_vector

    out = validate_vector(_unit(1) * 7.0)
    assert out is not None and len(out) == 192
    assert abs(float(np.linalg.norm(out)) - 1.0) < 1e-6


@pytest.mark.parametrize("bad", [
    None, [], np.zeros(192), np.ones(10), np.full(192, np.nan), np.full(192, np.inf), "nope",
])
def test_validate_rejects_unusable_vectors(bad):
    from server.voiceprint_store import validate_vector

    assert validate_vector(bad) is None


# --- save and read -------------------------------------------------------------------------

def test_save_then_candidates_round_trip(isolated_db):
    from server import voiceprint_store as store

    with isolated_db() as db:
        _person(db)
        saved = store.save_voiceprints(db, OWNER, "p1", {"wb": _unit(1), "nb8k_sim": _unit(2)},
                                       duration_s=20.0, snr_db=18.0)
        db.commit()
        assert sorted(saved) == ["nb8k_sim", "wb"]
        cands = store.get_candidates(db, OWNER)

    assert len(cands) == 1
    c = cands[0]
    assert (c["person_id"], c["name"], c["relationship"]) == ("p1", "Papa", "Father")
    assert set(c["centroids"]) == {"wb", "nb8k_sim"}
    assert np.allclose(c["centroids"]["wb"], _unit(1), atol=1e-6)


def test_saving_again_replaces_the_same_condition(isolated_db):
    from server import voiceprint_store as store
    from server.database import Voiceprint

    with isolated_db() as db:
        _person(db)
        store.save_voiceprints(db, OWNER, "p1", {"wb": _unit(1), "nb8k_sim": _unit(2), "nb8k_real": _unit(3)},
                               duration_s=20.0, snr_db=18.0)
        db.commit()
        store.save_voiceprints(db, OWNER, "p1", {"wb": _unit(4), "nb8k_sim": _unit(5)}, duration_s=16.0, snr_db=12.0)
        db.commit()
        rows = {v.condition: v for v in db.query(Voiceprint)}

    assert set(rows) == {"wb", "nb8k_sim", "nb8k_real"}, "a condition not re-measured must be kept"
    assert np.allclose(rows["wb"].get_embedding(), _unit(4), atol=1e-6)
    assert rows["wb"].duration_s == 16.0
    assert np.allclose(rows["nb8k_real"].get_embedding(), _unit(3), atol=1e-6)


def test_unknown_conditions_and_bad_vectors_are_not_saved(isolated_db, caplog):
    from server import voiceprint_store as store

    with isolated_db() as db:
        _person(db)
        saved = store.save_voiceprints(db, OWNER, "p1", {"wb": np.full(192, np.nan), "studio": _unit(1),
                                                  "nb8k_sim": _unit(2), "n_samples": 5},
                                       duration_s=20.0, snr_db=18.0)
        db.commit()
    assert saved == ["nb8k_sim"]
    assert any("wb" in r.getMessage() for r in caplog.records), "a dropped vector must be logged"


def test_candidates_skip_people_without_vectors_and_other_model_versions(isolated_db):
    from server import voiceprint_store as store
    from server.database import Voiceprint

    with isolated_db() as db:
        _person(db, "p1")
        _person(db, "p2", name="Ma", relation="Mother")
        _person(db, "p3", name="Old", relation="Uncle")
        store.save_voiceprints(db, OWNER, "p2", {"wb": _unit(1)}, duration_s=20.0, snr_db=18.0)
        db.add(Voiceprint(voiceprint_id="vp_old", person_id="p3", condition="wb",
                          embedding=_unit(2).tolist(),
                          embedding_dim=192, duration_s=1.0, snr_db=1.0, model_version="some-older-model"))
        db.commit()
        ids = [c["person_id"] for c in store.get_candidates(db, OWNER)]
    assert ids == ["p2"], "a vector from another embedding model is not comparable"


def test_candidates_for_one_person(isolated_db):
    from server import voiceprint_store as store

    with isolated_db() as db:
        for pid, seed in (("p1", 1), ("p2", 2)):
            _person(db, pid)
            store.save_voiceprints(db, OWNER, pid, {"wb": _unit(seed)}, duration_s=20.0, snr_db=18.0)
        db.commit()
        assert [c["person_id"] for c in store.get_candidates(db, OWNER, person_id="p2")] == ["p2"]
        assert store.get_candidates(db, OWNER, person_id="nobody") == []


def test_a_corrupt_row_is_skipped_and_logged(isolated_db, caplog):
    from server import voiceprint_store as store
    from server.database import Voiceprint

    from sqlalchemy import text

    with isolated_db() as db:
        _person(db)
        db.execute(text("INSERT INTO voiceprints (voiceprint_id, person_id, condition, embedding, embedding_dim, "
                        "duration_s, snr_db, model_version) VALUES ('vp_bad', 'p1', 'wb', :blob, 192, 1, 1, :mv)"),
                   {"blob": b"{not json", "mv": config.SPEAKER_MODEL_VERSION})
        db.commit()
        assert store.get_candidates(db, OWNER) == []
    assert any("vp_bad" in r.getMessage() for r in caplog.records)


# --- the orchestrator's speaker branch reads the store -----------------------------------

def test_speaker_branch_passes_database_candidates(isolated_db, monkeypatch):
    import audio_ml.api
    from audio_ml.signals import SpeakerSignal
    from server import orchestrator, voiceprint_store as store

    with isolated_db() as db:
        _person(db)
        store.save_voiceprints(db, OWNER, "p1", {"wb": _unit(1)}, duration_s=20.0, snr_db=18.0)
        db.commit()

    seen = {}

    def fake_verify(wav_path, candidates=None, claimed_person_id=None, flagged=None):
        seen["candidates"] = candidates
        return SpeakerSignal(verdict="match", best_match_id="p1", best_match_name="Papa", raw_cosine=0.9)

    monkeypatch.setattr(audio_ml.api, "verify_speaker", fake_verify)
    monkeypatch.setattr(config, "LEGACY_NPZ_FALLBACK", False)
    orchestrator._real_speaker_branch("x.wav", OWNER)
    assert [c["person_id"] for c in seen["candidates"]] == ["p1"]


def test_legacy_files_join_the_candidates_only_when_the_fallback_is_on(isolated_db, monkeypatch, tmp_path):
    import audio_ml.api
    from audio_ml import enroll
    from audio_ml.signals import SpeakerSignal
    from server import orchestrator, voiceprint_store as store

    monkeypatch.setattr(enroll, "ENROLLMENTS_DIR", tmp_path)
    np.savez(tmp_path / "legacy_1.npz", wb=_unit(5), nb8k=_unit(6), name="Legacy", relationship="Friend",
             n_samples=1, enrolled_at="2026-09-01")
    np.savez(tmp_path / "p1.npz", wb=_unit(7), nb8k=_unit(8), name="Stale copy", relationship="Friend",
             n_samples=1, enrolled_at="2026-09-01")
    with isolated_db() as db:
        _person(db)
        store.save_voiceprints(db, OWNER, "p1", {"wb": _unit(1)}, duration_s=20.0, snr_db=18.0)
        db.commit()

    seen = {}
    monkeypatch.setattr(audio_ml.api, "verify_speaker",
                        lambda wav_path, candidates=None, claimed_person_id=None, flagged=None:
                        seen.update(c=candidates) or SpeakerSignal())

    monkeypatch.setattr(config, "LEGACY_NPZ_FALLBACK", True)
    orchestrator._real_speaker_branch("x.wav", OWNER)
    by_id = {c["person_id"]: c for c in seen["c"]}
    assert set(by_id) == {"p1", "legacy_1"}
    assert np.allclose(by_id["p1"]["centroids"]["wb"], _unit(1), atol=1e-6), "the database wins over a file"

    monkeypatch.setattr(config, "LEGACY_NPZ_FALLBACK", False)
    orchestrator._real_speaker_branch("x.wav", OWNER)
    assert [c["person_id"] for c in seen["c"]] == ["p1"]


def test_legacy_fallback_is_forced_off_in_production(monkeypatch):
    import importlib

    monkeypatch.setenv("SATYACHECK_ENV", "production")
    monkeypatch.setenv("LEGACY_NPZ_FALLBACK", "true")
    try:
        reloaded = importlib.reload(config)
        assert reloaded.LEGACY_NPZ_FALLBACK is False
    finally:
        monkeypatch.delenv("SATYACHECK_ENV")
        monkeypatch.delenv("LEGACY_NPZ_FALLBACK")
        importlib.reload(config)


# --- migrating an existing database --------------------------------------------------------

def test_an_old_voiceprints_table_is_migrated_in_place(tmp_path):
    """Adds model_version, maps the old condition names, drops duplicates, adds the key."""
    from sqlalchemy import create_engine

    from server.database import migrate

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE voiceprints (voiceprint_id TEXT PRIMARY KEY, person_id TEXT NOT NULL, "
                   "condition TEXT NOT NULL, embedding_blob BLOB NOT NULL, embedding_dim INTEGER NOT NULL, "
                   "duration_s REAL NOT NULL, snr_db REAL NOT NULL, created_at DATETIME)")
        rows = [("v1", "p1", "wideband_16k"), ("v2", "p1", "wideband_16k"), ("v3", "p1", "narrowband_8k")]
        for vid, pid, cond in rows:
            db.execute("INSERT INTO voiceprints VALUES (?, ?, ?, ?, 192, 1.0, 1.0, NULL)", (vid, pid, cond, b"[]"))

    engine = create_engine(f"sqlite:///{path}")
    migrate(engine)
    migrate(engine)  # idempotent

    with sqlite3.connect(path) as db:
        got = sorted(db.execute("SELECT voiceprint_id, condition, model_version FROM voiceprints"))
        indexes = [r[1] for r in db.execute("PRAGMA index_list(voiceprints)") if r[2] == 1]
    assert got == [("v2", "wb", "legacy"), ("v3", "nb8k_sim", "legacy")], "newest duplicate kept"
    assert "uq_voiceprints_person_condition_model" in indexes


def test_another_owners_people_are_never_candidates(isolated_db):
    from server import voiceprint_store as store

    with isolated_db() as db:
        _person(db, "p_mine")
        _person(db, "p_theirs", owner="owner-b")
        store.save_voiceprints(db, OWNER, "p_mine", {"wb": _unit(1)}, duration_s=20.0, snr_db=18.0)
        store.save_voiceprints(db, "owner-b", "p_theirs", {"wb": _unit(2)}, duration_s=20.0, snr_db=18.0)
        db.commit()
        assert [c["person_id"] for c in store.get_candidates(db, OWNER)] == ["p_mine"]
        assert [c["person_id"] for c in store.get_candidates(db, "owner-b")] == ["p_theirs"]
        assert store.get_candidates(db, OWNER, person_id="p_theirs") == []


def test_saving_onto_another_owners_person_is_refused(isolated_db):
    from server import voiceprint_store as store

    with isolated_db() as db:
        _person(db, "p_theirs", owner="owner-b")
        with pytest.raises(store.NotOwned):
            store.save_voiceprints(db, OWNER, "p_theirs", {"wb": _unit(1)}, duration_s=20.0, snr_db=18.0)


def test_store_functions_refuse_a_missing_owner(isolated_db):
    from server import voiceprint_store as store

    with isolated_db() as db:
        for call in (lambda: store.get_candidates(db, ""), lambda: store.get_flagged(db, None),
                     lambda: store.delete_person(db, "", "p1")):
            with pytest.raises(ValueError):
                call()


def test_flagged_voices_are_per_owner(isolated_db):
    from server import voiceprint_store as store

    with isolated_db() as db:
        assert store.add_flagged_voice(db, OWNER, _unit(1), "kyc_fraud", "case-1")
        assert store.add_flagged_voice(db, OWNER, [float("nan")] * 192, "kyc_fraud") is None
        db.commit()
        assert len(store.get_flagged(db, OWNER)) == 1
        assert store.get_flagged(db, "owner-b") == []


def test_no_owner_means_no_candidates_and_a_log_line(caplog):
    from server import orchestrator

    assert orchestrator._speaker_candidates(None) == ([], [])
    assert any("no owner" in r.getMessage() for r in caplog.records)
