"""Upgrade plan, Phase 0 step 4: move the legacy .npz voiceprints into the database.

`scripts/import_npz_voiceprints.py` must be safe to run twice, validate every vector,
map keys exactly as `load_voiceprint` does (nb8k -> nb8k_sim), assign an owner
explicitly, report how files and database reconcile, archive files only when they do,
and undo itself with --rollback.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

import config
from server.tests.isolated_db import isolated_db  # noqa: F401  (fixture)


def _unit(seed: int, dim: int = 192) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def _npz(folder, person_id, name, seed, **extra):
    data = dict(wb=_unit(seed) * 4.0, nb8k=_unit(seed + 100), name=name, relationship="Family",
                n_samples=16000 * 20, enrolled_at="2026-09-01T00:00:00+00:00")
    data.update(extra)
    np.savez(folder / f"{person_id}.npz", **data)


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    from audio_ml import enroll

    folder = tmp_path / "enrollments"
    folder.mkdir()
    monkeypatch.setattr(enroll, "ENROLLMENTS_DIR", folder)
    monkeypatch.setattr(config, "ENROLLMENTS_DIR", folder)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    _npz(folder, "alice", "Alice", 1)
    _npz(folder, "friend", "Friend", 2, nb8k_real=_unit(3))
    _npz(folder, "me", "Me", 4)
    return folder


def _run(*args):
    from scripts import import_npz_voiceprints

    return import_npz_voiceprints.main(list(args))


def _db(isolated_db):
    from server.database import Person, Voiceprint

    with isolated_db() as db:
        people = {p.person_id: (p.name, p.owner_id) for p in db.query(Person)}
        rows = {(v.person_id, v.condition): v.get_embedding() for v in db.query(Voiceprint)}
    return people, rows


def _latest_report(tmp_path):
    reports = sorted((tmp_path / "migrations").glob("npz_import_*.json"))
    return json.loads(reports[-1].read_text()), reports[-1]


def test_dry_run_reports_and_writes_nothing(isolated_db, legacy, capsys):
    assert _run("--dry-run", "--owner", "o") == 0
    assert _db(isolated_db) == ({}, {})
    out = capsys.readouterr().out
    assert "3" in out and "would import" in out.lower()


def test_import_requires_an_explicit_owner(isolated_db, legacy):
    with pytest.raises(SystemExit):
        _run()
    assert _db(isolated_db) == ({}, {})


def test_import_maps_keys_validates_and_assigns_the_owner(isolated_db, legacy):
    assert _run("--owner", "family-account-1") == 0
    people, rows = _db(isolated_db)
    assert people == {"alice": ("Alice", "family-account-1"), "friend": ("Friend", "family-account-1"),
                      "me": ("Me", "family-account-1")}
    assert set(rows) == {("alice", "wb"), ("alice", "nb8k_sim"), ("friend", "wb"), ("friend", "nb8k_sim"),
                         ("friend", "nb8k_real"), ("me", "wb"), ("me", "nb8k_sim")}
    assert abs(np.linalg.norm(rows[("alice", "wb")]) - 1.0) < 1e-6, "renormalised to unit length"
    assert np.allclose(rows[("alice", "nb8k_sim")], _unit(101), atol=1e-6), "nb8k maps to nb8k_sim"

    report, _ = _latest_report(legacy.parent)
    assert report["reconciliation"]["passed"] is True
    assert sorted(report["imported"]) == ["alice", "friend", "me"]


def test_running_twice_imports_nothing_new(isolated_db, legacy):
    assert _run("--owner", "o") == 0
    first = _db(isolated_db)
    assert _run("--owner", "o") == 0
    assert _db(isolated_db) == first
    report, _ = _latest_report(legacy.parent)
    assert report["imported"] == [] and sorted(report["skipped"]) == ["alice", "friend", "me"]


def test_bad_files_are_reported_not_imported_and_block_archiving(isolated_db, legacy):
    _npz(legacy, "broken", "Broken", 9, wb=np.full(192, np.nan), nb8k=np.ones(5))
    (legacy / "garbage.npz").write_bytes(b"not a zip")
    assert _run("--owner", "o", "--archive") == 1
    people, _ = _db(isolated_db)
    assert "broken" not in people and "garbage" not in people
    report, _ = _latest_report(legacy.parent)
    assert {"broken", "garbage"} <= set(report["errors"])
    assert report["reconciliation"]["passed"] is False
    assert report.get("archived_to") is None
    assert (legacy / "alice.npz").is_file(), "nothing may be archived while reconciliation fails"


def test_a_person_already_in_the_database_keeps_their_vectors(isolated_db, legacy):
    from server import voiceprint_store
    from server.database import Person

    with isolated_db() as db:
        db.add(Person(person_id="alice", owner_id="o", name="Alice (app)", relation="Sister"))
        db.flush()
        voiceprint_store.save_voiceprints(db, "o", "alice", {"wb": _unit(50)}, duration_s=20.0, snr_db=20.0)
        db.commit()
    assert _run("--owner", "o") == 0
    people, rows = _db(isolated_db)
    assert people["alice"] == ("Alice (app)", "o")
    assert np.allclose(rows[("alice", "wb")], _unit(50), atol=1e-6), "the database wins over a file"
    report, _ = _latest_report(legacy.parent)
    assert "alice" in report["reconciliation"]["mismatched"]


def test_archive_then_rollback_restores_files_and_removes_imported_rows(isolated_db, legacy):
    from server.database import Person

    with isolated_db() as db:
        db.add(Person(person_id="kept", owner_id="o", name="Kept", relation="Friend"))
        db.commit()

    assert _run("--owner", "o", "--archive") == 0
    report, report_path = _latest_report(legacy.parent)
    assert report["archived_to"]
    assert list(legacy.glob("*.npz")) == []

    assert _run("--rollback", str(report_path)) == 0
    assert sorted(p.stem for p in legacy.glob("*.npz")) == ["alice", "friend", "me"]
    people, rows = _db(isolated_db)
    assert people == {"kept": ("Kept", "o")} and rows == {}


def test_reconcile_lists_orphans_in_both_directions(isolated_db, legacy, capsys):
    from server.database import Person

    with isolated_db() as db:
        db.add(Person(person_id="no_vectors", owner_id="o", name="Ghost", relation="Friend"))
        db.commit()
    assert _run("--reconcile", "--owner", "o") == 1
    report, _ = _latest_report(legacy.parent)
    rec = report["reconciliation"]
    assert sorted(rec["file_only"]) == ["alice", "friend", "me"]
    assert rec["db_without_vectors"] == ["no_vectors"]
    assert _db(isolated_db)[1] == {}, "--reconcile writes nothing"
