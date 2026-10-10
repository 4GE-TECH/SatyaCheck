"""SatyaCheck — retention and erasure (upgrade plan, Phase 1).

What we keep, and for how long:

  call audio (data/sessions/<id>/)     RETENTION_AUDIO_DAYS   (dev-only copy; off in production)
  sessions, screenings (transcripts),  RETENTION_RESULTS_DAYS
  PDF reports (data/reports/)
  voiceprints, secrets, consents,      until the person or the account is deleted
  flagged voices

`sweep` enforces the clocks across all accounts, so on Postgres it must run with the
admin connection (the table owner, which RLS does not filter; the app role cannot see
other accounts). `delete_account` erases one account through its own scoped session.

The evidence log (server/evidence.py) is append-only and is NOT erased here: its leaves
hold no audio or transcript, and removing one would break every later proof. See
AGENTS.md (open items) for the redaction plan.

C owns this file.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import config
from server.database import (
    ConsentRecord,
    FlaggedVoice,
    GuardianSubscription,
    LlmShadowRecord,
    Person,
    ScreeningResult,
    ScreeningSession,
    owner_session,
)

log = logging.getLogger("satyacheck.retention")


def _audio_dir(session_id: str) -> Optional[Path]:
    from server.ws_router import _session_audio_dir

    return _session_audio_dir(session_id)


def _report_path(session_id: str) -> Path:
    return config.REPORTS_DIR / f"RPT_{session_id[:12].upper()}.pdf"


def _older_than(path: Path, cutoff: datetime) -> bool:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc) < cutoff
    except OSError:
        return False


def sweep(db_factory: Callable, now: Optional[datetime] = None) -> dict:
    """Delete everything past its retention clock, for every account. Returns counts.
    Idempotent; safe to run daily."""
    now = now or datetime.now(timezone.utc)
    audio_cutoff = now - timedelta(days=config.RETENTION_AUDIO_DAYS)
    results_cutoff = now - timedelta(days=config.RETENTION_RESULTS_DAYS)
    counts = {"sessions": 0, "screenings": 0, "llm_shadow": 0, "audio_dirs": 0, "reports": 0}

    with db_factory() as db:
        expired = [sid for (sid,) in db.query(ScreeningSession.session_id)
                   .filter(ScreeningSession.created_at < results_cutoff)]
        counts["screenings"] = (db.query(ScreeningResult)
                                .filter(ScreeningResult.created_at < results_cutoff)
                                .delete(synchronize_session=False))
        counts["llm_shadow"] = (db.query(LlmShadowRecord)
                                .filter(LlmShadowRecord.created_at < results_cutoff)
                                .delete(synchronize_session=False))
        if expired:
            counts["screenings"] += (db.query(ScreeningResult)
                                     .filter(ScreeningResult.session_id.in_(expired))
                                     .delete(synchronize_session=False))
            counts["sessions"] = (db.query(ScreeningSession)
                                  .filter(ScreeningSession.session_id.in_(expired))
                                  .delete(synchronize_session=False))
        db.commit()

    sessions_root = config.DATA_DIR / "sessions"
    if sessions_root.is_dir():
        for d in sessions_root.iterdir():
            if not d.is_dir():
                continue
            # A call still being recorded has fresh files: age by the newest one.
            if all(_older_than(f, audio_cutoff) for f in [d, *d.rglob("*")]):
                shutil.rmtree(d, ignore_errors=True)
                counts["audio_dirs"] += 1
    if config.REPORTS_DIR.is_dir():
        for pdf in config.REPORTS_DIR.glob("*.pdf"):
            if _older_than(pdf, results_cutoff):
                pdf.unlink(missing_ok=True)
                counts["reports"] += 1

    log.info(f"retention sweep: {counts} (audio > {config.RETENTION_AUDIO_DAYS}d, "
             f"results > {config.RETENTION_RESULTS_DAYS}d)")
    return counts


def delete_account(owner_id: str) -> dict:
    """Erase one account: contacts with their voiceprints, secrets, consents and
    subscriptions; sessions with their results; flagged voices; call audio and reports.
    Rows go in one transaction; files only after it commits."""
    if not owner_id:
        raise ValueError("an owner_id is required")
    with owner_session(owner_id) as db:
        session_ids = [sid for (sid,) in db.query(ScreeningSession.session_id)
                       .filter(ScreeningSession.owner_id == owner_id)]
        person_ids = [pid for (pid,) in db.query(Person.person_id).filter(Person.owner_id == owner_id)]
        counts = {
            "screenings": db.query(ScreeningResult).filter(ScreeningResult.owner_id == owner_id)
                            .delete(synchronize_session=False),
            "sessions": db.query(ScreeningSession).filter(ScreeningSession.owner_id == owner_id)
                          .delete(synchronize_session=False),
            "flagged_voices": db.query(FlaggedVoice).filter(FlaggedVoice.owner_id == owner_id)
                                .delete(synchronize_session=False),
            "guardian_subscriptions": db.query(GuardianSubscription)
                                        .filter(GuardianSubscription.owner_id == owner_id)
                                        .delete(synchronize_session=False),
            "consents": db.query(ConsentRecord).filter(ConsentRecord.owner_id == owner_id)
                          .delete(synchronize_session=False),
            "llm_shadow": db.query(LlmShadowRecord).filter(LlmShadowRecord.owner_id == owner_id)
                            .delete(synchronize_session=False),
        }
        persons = db.query(Person).filter(Person.owner_id == owner_id).all()
        for person in persons:   # ORM cascade: voiceprints, secrets, idempotency keys
            db.delete(person)
        counts["persons"] = len(persons)
        db.commit()

    files = 0
    for sid in session_ids:
        d = _audio_dir(sid)
        if d is not None and d.exists():
            shutil.rmtree(d, ignore_errors=True)
            files += 1
        if _report_path(sid).exists():
            _report_path(sid).unlink(missing_ok=True)
            files += 1
    from audio_ml.api import delete_person as delete_legacy_voiceprint
    for pid in person_ids:
        files += int(delete_legacy_voiceprint(pid))
    counts["files"] = files
    log.info(f"account {owner_id} erased: {counts}")
    return counts


if __name__ == "__main__":
    # Daily job: python -m server.retention
    # On Postgres this needs DATABASE_ADMIN_URL: the app role sees one account at a time.
    import json

    from sqlalchemy.orm import sessionmaker

    from server import database

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if config.DATABASE_URL and not config.DATABASE_ADMIN_URL:
        raise SystemExit("DATABASE_ADMIN_URL is required to sweep a Postgres database")
    engine = database.make_engine(config.DATABASE_ADMIN_URL or None)
    if not database.is_postgres(engine):
        database.init_db()
    print(json.dumps(sweep(sessionmaker(bind=engine)), indent=2))
