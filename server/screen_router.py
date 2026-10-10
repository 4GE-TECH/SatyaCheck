"""SatyaCheck — Screening Router

Accepts audio uploads, runs the full orchestration pipeline,
stores results in DB, returns ScreeningResponse.

C owns this file.
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

import config
from contracts import CallerMetadata, ScreeningResponse
from server.audio_ingest import discard, ingest_audio
from server.auth import current_owner
from server.database import ScreeningSession, ScreeningResult, get_owner_db
from server.orchestrator import screen_audio

log = logging.getLogger("satyacheck.screen")
router = APIRouter(prefix="/api/screen", tags=["screen"])


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
    owner_id: str = Depends(current_owner),
    db: Session = Depends(get_owner_db),
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

    # ── Create session record ─────────────────────────────────────────
    session_id = f"session_{uuid.uuid4().hex[:12]}"
    db_session = ScreeningSession(
        session_id=session_id,
        owner_id=owner_id,
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
            owner_id=owner_id,
        )
        # Override session_id to match DB record
        response = response.model_copy(update={"session_id": session_id})
    except Exception as e:
        db_session.status = "failed"
        db.commit()
        log.error(f"Orchestration failed for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Screening failed: {str(e)}")
    finally:
        discard(ingested)

    # ── Persist result ────────────────────────────────────────────────
    db_result = ScreeningResult(
        owner_id=owner_id,
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
            await publish_alert_from_response(response, owner_id)
        except Exception as ge:
            log.warning(f"Guardian alert failed (non-fatal): {ge}")

    return response


class ScreeningListItem(BaseModel):
    """One of the account's calls, for the reports list. No transcript, no audio."""
    session_id: str
    created_at: str
    status: str
    channel_type: Optional[str] = None
    band: Optional[str] = None          # the final verdict's band; None while none is stored
    trust_score: Optional[float] = None


class ScreeningList(BaseModel):
    items: list[ScreeningListItem]
    next_cursor: Optional[str] = None


def _encode_cursor(created_at, session_id: str) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{session_id}".encode()).decode()


def _decode_cursor(cursor: str):
    from datetime import datetime

    try:
        created, _, session_id = base64.urlsafe_b64decode(cursor.encode()).decode().partition("|")
        return datetime.fromisoformat(created), session_id
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid cursor.")


@router.get("", response_model=ScreeningList, summary="List your screened calls, newest first")
async def list_screenings(
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    owner_id: str = Depends(current_owner),
    db: Session = Depends(get_owner_db),
) -> ScreeningList:
    query = db.query(ScreeningSession).filter(ScreeningSession.owner_id == owner_id)
    if cursor:
        created, session_id = _decode_cursor(cursor)
        query = query.filter(or_(ScreeningSession.created_at < created,
                                 and_(ScreeningSession.created_at == created,
                                      ScreeningSession.session_id < session_id)))
    rows = (query.order_by(ScreeningSession.created_at.desc(), ScreeningSession.session_id.desc())
            .limit(limit + 1).all())
    page, more = rows[:limit], len(rows) > limit
    finals: dict[str, ScreeningResult] = {}
    for result in (db.query(ScreeningResult)
                   .filter(ScreeningResult.owner_id == owner_id, ScreeningResult.is_final == True,
                           ScreeningResult.session_id.in_([s.session_id for s in page]))
                   .order_by(ScreeningResult.id)):
        finals[result.session_id] = result   # the newest final wins
    items = []
    for s in page:
        band = trust = None
        if s.session_id in finals:
            fusion = json.loads(finals[s.session_id].response_json).get("fusion") or {}
            band, trust = fusion.get("band"), fusion.get("trust_score")
        items.append(ScreeningListItem(session_id=s.session_id, created_at=str(s.created_at), status=s.status,
                                       channel_type=s.channel_type, band=band, trust_score=trust))
    next_cursor = _encode_cursor(page[-1].created_at, page[-1].session_id) if more and page else None
    return ScreeningList(items=items, next_cursor=next_cursor)


@router.get(
    "/{session_id}",
    response_model=ScreeningResponse,
    summary="Retrieve a stored screening result",
)
async def get_screening_result(
    session_id: str,
    owner_id: str = Depends(current_owner),
    db: Session = Depends(get_owner_db),
) -> ScreeningResponse:
    result = (
        db.query(ScreeningResult)
        .filter(ScreeningResult.session_id == session_id, ScreeningResult.owner_id == owner_id,
                ScreeningResult.is_final == True)
        .order_by(ScreeningResult.id.desc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return ScreeningResponse.model_validate_json(result.response_json)
