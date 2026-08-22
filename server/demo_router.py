"""SatyaCheck — Demo Reset Router

Provides a clean-state reset endpoint used before every demo rehearsal.
Wipes all sessions and screenings, re-seeds enrolled persons if seed data exists.

C owns this file.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from server.database import (
    GuardianSubscription,
    Person,
    ScreeningResult,
    ScreeningSession,
    get_db,
)

log = logging.getLogger("satyacheck.demo")
router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post(
    "/reset",
    summary="[DEMO] Reset all session data to clean state",
    description=(
        "Wipes all screening sessions and results. "
        "Does NOT delete enrolled persons or voiceprints. "
        "Safe to call before every demo run."
    ),
)
async def demo_reset(db: Session = Depends(get_db)) -> JSONResponse:
    # Delete results first (FK dependency)
    deleted_results = db.query(ScreeningResult).delete()
    deleted_sessions = db.query(ScreeningSession).delete()
    db.commit()

    person_count = db.query(Person).count()
    log.info(f"Demo reset: {deleted_sessions} sessions, {deleted_results} results cleared. {person_count} persons retained.")

    return JSONResponse(content={
        "status": "reset_complete",
        "sessions_cleared": deleted_sessions,
        "results_cleared": deleted_results,
        "persons_retained": person_count,
        "message": "Ready for demo. Enrolled persons and voiceprints are intact.",
    })


@router.get(
    "/status",
    summary="[DEMO] Show current demo readiness status",
)
async def demo_status(db: Session = Depends(get_db)) -> JSONResponse:
    person_count = db.query(Person).count()
    session_count = db.query(ScreeningSession).count()

    from server.database import Voiceprint, FlaggedVoice
    voiceprint_count = db.query(Voiceprint).count()

    return JSONResponse(content={
        "enrolled_persons": person_count,
        "voiceprints": voiceprint_count,
        "active_sessions": session_count,
        "ready_for_demo": person_count > 0 and voiceprint_count > 0,
        "checklist": {
            "persons_enrolled": person_count > 0,
            "voiceprints_stored": voiceprint_count > 0,
            "sessions_clean": session_count == 0,
        },
    })
