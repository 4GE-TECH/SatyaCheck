"""Import the legacy data/enrollments/*.npz voiceprints into the database.

Upgrade plan, Phase 0 step 4. The database is the one voiceprint store; files written
before that change are only visible to screening while LEGACY_NPZ_FALLBACK is on (dev
only). This moves them across, safely:

  * resumable and idempotent: each person is one transaction, and a person who already
    has vectors in the database is skipped (the database wins over a file);
  * every vector validated: 192 finite values, renormalised to unit length;
  * keys mapped exactly as audio_ml.enroll.load_voiceprint does (nb8k -> nb8k_sim);
  * ownership explicit: --owner is required to import;
  * a reconciliation report (people in files vs in the database) is written to
    data/migrations/ on every run;
  * files are archived (--archive) only when reconciliation passes, and --rollback
    <report> puts the files back and removes exactly the rows that run created.

Usage
-----
    python -m scripts.import_npz_voiceprints --dry-run
    python -m scripts.import_npz_voiceprints --owner <account-id> [--archive]
    python -m scripts.import_npz_voiceprints --reconcile
    python -m scripts.import_npz_voiceprints --rollback data/migrations/npz_import_<ts>.json

Exit status: 0 when reconciliation passes (or a rollback completes), 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import config

CONDITIONS = ("wb", "nb8k_sim", "nb8k_real")
SAME_VECTOR_COSINE = 0.9999


def _enrollments_dir() -> Path:
    from audio_ml import enroll

    return Path(enroll.ENROLLMENTS_DIR)


def _read_files() -> tuple[dict[str, dict], dict[str, str]]:
    """{person_id: {"name", "relationship", "n_samples", "vectors": {condition: list}}} for
    every usable file, and {person_id: reason} for every file that is not."""
    from audio_ml import enroll
    from server.voiceprint_store import validate_vector

    usable, errors = {}, {}
    for path in sorted(_enrollments_dir().glob("*.npz")):
        person_id = path.stem
        vp = enroll.load_voiceprint(person_id)
        if vp is None:
            errors[person_id] = "unreadable or missing required keys"
            continue
        vectors, rejected = {}, []
        for condition in CONDITIONS:
            if vp.get(condition) is None:
                continue
            valid = validate_vector(vp[condition])
            if valid is None:
                rejected.append(condition)
            else:
                vectors[condition] = valid
        if not vectors:
            errors[person_id] = f"no valid vector (rejected: {rejected})"
            continue
        usable[person_id] = {"name": vp["name"], "relationship": vp["relationship"],
                             "n_samples": vp["n_samples"], "vectors": vectors, "rejected": rejected}
    return usable, errors


def _db_vectors(db, owner: str) -> tuple[dict[str, dict[str, list]], list[str]]:
    """{person_id: {condition: vector}} of this owner's people for the current model, and
    their people with no vector."""
    from server import voiceprint_store
    from server.database import Person

    by_person = {c["person_id"]: {k: v.tolist() for k, v in c["centroids"].items()}
                 for c in voiceprint_store.get_candidates(db, owner)}
    without = sorted(p.person_id for p in db.query(Person).filter(Person.owner_id == owner)
                     if p.person_id not in by_person)
    return by_person, without


def _reconcile(files: dict, errors: dict, db_vectors: dict, db_without: list) -> dict:
    file_only = sorted(pid for pid in files if pid not in db_vectors)
    mismatched = []
    for pid, f in files.items():
        if pid not in db_vectors:
            continue
        for condition, vec in f["vectors"].items():
            stored = db_vectors[pid].get(condition)
            if stored is None or float(np.dot(vec, stored)) < SAME_VECTOR_COSINE:
                mismatched.append(pid)
                break
    return {
        "files": len(files) + len(errors),
        "file_only": file_only,
        "db_only": sorted(pid for pid in db_vectors if pid not in files),
        "db_without_vectors": db_without,
        "mismatched": sorted(mismatched),
        "errors": sorted(errors),
        # Mismatches are reported, not fatal: the database is the source of truth.
        "passed": not file_only and not errors,
    }


def _write_report(report: dict) -> Path:
    out_dir = config.DATA_DIR / "migrations"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"npz_import_{report['started_at'].replace(':', '').replace('-', '')}"
    path, n = out_dir / f"{base}.json", 1
    while path.exists():
        n += 1
        path = out_dir / f"{base}_{n}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def _import(db_factory, files: dict, owner: str, report: dict) -> None:
    from server import voiceprint_store
    from server.database import Person, Voiceprint

    for person_id, f in files.items():
        with db_factory() as db:
            db.info["owner_id"] = owner
            if voiceprint_store.get_candidates(db, owner, person_id=person_id):
                report["skipped"].append(person_id)
                continue
            try:
                created = db.query(Person).filter(Person.person_id == person_id).first() is None
                if created:
                    db.add(Person(person_id=person_id, name=f["name"], relation=f["relationship"],
                                  owner_id=owner))
                    db.flush()
                saved = voiceprint_store.save_voiceprints(
                    db, owner, person_id, f["vectors"],
                    duration_s=f["n_samples"] / config.TARGET_SAMPLE_RATE,
                    snr_db=0.0,  # not recorded in legacy files
                )
                ids = [v.voiceprint_id for v in db.query(Voiceprint).filter(
                    Voiceprint.person_id == person_id, Voiceprint.condition.in_(saved))]
                db.commit()
                if created:
                    report["created_persons"].append(person_id)
                report["created_voiceprints"].extend(ids)
                report["imported"].append(person_id)
            except Exception as e:
                db.rollback()
                report["errors"][person_id] = f"import failed: {type(e).__name__}: {e}"


def _archive(report: dict) -> None:
    src = _enrollments_dir()
    dest = src / "_archived" / report["started_at"].replace(":", "").replace("-", "")
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for path in sorted(src.glob("*.npz")):
        shutil.move(str(path), str(dest / path.name))
        moved.append(path.name)
    report["archived_to"] = str(dest)
    report["archived_files"] = moved


def _rollback(db_factory, report_path: Path) -> int:
    from server.database import Person, Voiceprint

    report = json.loads(report_path.read_text(encoding="utf-8"))
    archived_to = report.get("archived_to")
    restored = 0
    if archived_to:
        for name in report.get("archived_files", []):
            src = Path(archived_to) / name
            if src.is_file():
                shutil.move(str(src), str(_enrollments_dir() / name))
                restored += 1
    with db_factory() as db:
        db.info["owner_id"] = report.get("owner") or ""
        created = set(report.get("created_persons", []))
        for vid in report.get("created_voiceprints", []):
            row = db.query(Voiceprint).filter(Voiceprint.voiceprint_id == vid).first()
            if row is not None and row.person_id not in created:
                db.delete(row)
        for pid in created:
            person = db.query(Person).filter(Person.person_id == pid).first()
            if person is not None:
                db.delete(person)
        db.commit()
    print(f"rollback: restored {restored} file(s), removed {len(report.get('created_voiceprints', []))} "
          f"voiceprint row(s) and {len(report.get('created_persons', []))} person(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="show what would be imported; write nothing")
    mode.add_argument("--reconcile", action="store_true", help="report files vs database; write nothing")
    mode.add_argument("--rollback", metavar="REPORT", help="undo the run that wrote REPORT")
    ap.add_argument("--owner", help="account id that owns the imported contacts (required to import)")
    ap.add_argument("--archive", action="store_true", help="move the files aside if reconciliation passes")
    args = ap.parse_args(argv)

    from server import database

    bind = database.SessionLocal.kw["bind"]
    if not database.is_postgres(bind):   # Postgres is migrated by Alembic
        database.Base.metadata.create_all(bind=bind)
        database.migrate(bind)
    db_factory = database.SessionLocal

    if args.rollback:
        return _rollback(db_factory, Path(args.rollback))

    importing = not (args.dry_run or args.reconcile)
    if not args.owner:
        ap.error("--owner is required (whose contacts are these?)")

    files, errors = _read_files()
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "import" if importing else ("dry-run" if args.dry_run else "reconcile"),
        "owner": args.owner, "model_version": config.SPEAKER_MODEL_VERSION,
        "imported": [], "skipped": [], "errors": dict(errors),
        "created_persons": [], "created_voiceprints": [], "archived_to": None,
        "rejected_vectors": {pid: f["rejected"] for pid, f in files.items() if f["rejected"]},
    }

    if args.dry_run:
        with db_factory() as db:
            db.info["owner_id"] = args.owner
            db_vectors, _ = _db_vectors(db, args.owner)
        todo = sorted(pid for pid in files if pid not in db_vectors)
        print(f"dry run: would import {len(todo)} person(s): {', '.join(todo) or '-'}")
        print(f"  already in the database: {sorted(pid for pid in files if pid in db_vectors) or '-'}")
        print(f"  unusable files: {errors or '-'}")
        return 0

    if importing:
        _import(db_factory, files, args.owner, report)

    with db_factory() as db:
        db.info["owner_id"] = args.owner
        db_vectors, db_without = _db_vectors(db, args.owner)
    report["reconciliation"] = _reconcile(files, report["errors"], db_vectors, db_without)
    passed = report["reconciliation"]["passed"]

    if args.archive and importing:
        if passed:
            _archive(report)
        else:
            print("reconciliation failed: files NOT archived", file=sys.stderr)

    path = _write_report(report)
    rec = report["reconciliation"]
    print(f"{report['mode']}: imported {len(report['imported'])}, skipped {len(report['skipped'])}, "
          f"errors {len(report['errors'])}")
    print(f"  file only: {rec['file_only'] or '-'} | mismatched: {rec['mismatched'] or '-'} | "
          f"db without vectors: {rec['db_without_vectors'] or '-'}")
    print(f"  reconciliation {'PASSED' if passed else 'FAILED'}; report: {path}")
    if report["archived_to"]:
        print(f"  files archived to {report['archived_to']} (undo: --rollback {path})")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
