"""SatyaCheck — Screening Router

Accepts audio uploads, runs the full orchestration pipeline,
stores results in DB, returns ScreeningResponse.

C owns this file.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

import config
from contracts import CallerMetadata, ScreeningResponse
from server.audio_ingest import ingest_audio
from server.database import (
    Person,
    ScreeningSession,
    ScreeningResult,
    Voiceprint,
    get_db,
)
from server.orchestrator import screen_audio

log = logging.getLogger("satyacheck.screen")
router = APIRouter(prefix="/api/screen", tags=["screen"])


def _load_enrolled_embeddings(db: Session) -> dict:
    """Load all enrolled voiceprints into memory for comparison."""
    embeddings: dict = {}
    persons = db.query(Person).all()
    for person in persons:
        embeddings[person.person_id] = {
            "name": person.name,
            "relation": person.relation,
            "voiceprints": {},
        }
        for vp in person.voiceprints:
            embeddings[person.person_id]["voiceprints"][vp.condition] = {
                "voiceprint_id": vp.voiceprint_id,
                "embedding": vp.get_embedding(),
                "duration_s": vp.duration_s,
                "snr_db": vp.snr_db,
            }
    return embeddings


@router.post(
    "",
    response_model=ScreeningResponse,
    summary="Screen an uploaded audio file",
    description=(
        "Accepts a multipart audio file upload and optional caller metadata. "
        "Runs quality gate → 3 concurrent branches → fusion → returns full ScreeningResponse."
    ),
)
async def screen_audio_endpoint(
    file: UploadFile = File(..., description="Audio file to screen (WAV, MP3, OGG, M4A, etc.)"),
    claimed_number: Optional[str] = Form(None),
    claimed_name: Optional[str] = Form(None),
    claimed_identity: Optional[str] = Form(None),
    channel_type: str = Form("upload"),
    db: Session = Depends(get_db),
) -> ScreeningResponse:
    # ── Read and validate upload ──────────────────────────────────────
    audio_bytes = await file.read()
    if len(audio_bytes) > config.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {config.MAX_UPLOAD_SIZE_MB}MB.",
        )
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=422, detail="Empty audio file.")

    # ── Build caller metadata ─────────────────────────────────────────
    caller_meta = CallerMetadata(
        claimed_number=claimed_number,
        claimed_name=claimed_name,
        claimed_identity=claimed_identity,
        channel_type=channel_type,  # type: ignore
    )

    # ── Ingest ────────────────────────────────────────────────────────
    ingested = ingest_audio(audio_bytes=audio_bytes)

    # ── Load enrolled voiceprints from DB ────────────────────────────
    enrolled = _load_enrolled_embeddings(db)

    # ── Create session record ─────────────────────────────────────────
    session_id = f"session_{uuid.uuid4().hex[:12]}"
    db_session = ScreeningSession(
        session_id=session_id,
        audio_sha256=ingested.audio_sha256,
        status="pending",
        channel_type=channel_type,
    )
    db.add(db_session)
    db.commit()

    # ── Run orchestration ─────────────────────────────────────────────
    try:
        import asyncio
        response = await screen_audio(
            audio=ingested,
            caller_metadata=caller_meta,
            enrolled_embeddings=enrolled,
        )
        # Override session_id to match DB record
        response = response.model_copy(update={"session_id": session_id})
    except Exception as e:
        db_session.status = "failed"
        db.commit()
        log.error(f"Orchestration failed for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Screening failed: {str(e)}")

    # ── Persist result ────────────────────────────────────────────────
    db_result = ScreeningResult(
        session_id=session_id,
        chunk_index=0,
        response_json=response.model_dump_json(),
        processing_ms=response.processing_time_ms,
        is_final=True,
    )
    db.add(db_result)
    db_session.status = "complete"
    db.commit()

    # ── Fire guardian alert if HIGH_RISK ──────────────────────────────
    if response.fusion.band in ("high_risk", "suspicious"):
        try:
            from server.guardian import publish_alert_from_response
            await publish_alert_from_response(response)
        except Exception as ge:
            log.warning(f"Guardian alert failed (non-fatal): {ge}")

    return response


@router.get(
    "/{session_id}",
    response_model=ScreeningResponse,
    summary="Retrieve a stored screening result",
)
async def get_screening_result(
    session_id: str,
    db: Session = Depends(get_db),
) -> ScreeningResponse:
    result = (
        db.query(ScreeningResult)
        .filter(ScreeningResult.session_id == session_id, ScreeningResult.is_final == True)
        .order_by(ScreeningResult.id.desc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return ScreeningResponse.model_validate_json(result.response_json)
