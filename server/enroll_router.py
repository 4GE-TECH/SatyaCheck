"""SatyaCheck — Enrollment Router

Accepts multipart audio upload + person metadata, runs ingestion,
calls audio_ml.api.enroll_person(), stores condition-matched voiceprints.

C owns this file.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

import config
from contracts import EnrolledPerson, AcousticCondition
from server.audio_ingest import ingest_audio
from server.database import Person, Voiceprint, SharedSecret as DBSecret, get_db

log = logging.getLogger("satyacheck.enroll")
router = APIRouter(prefix="/api/enroll", tags=["enroll"])


@router.post("", response_model=EnrolledPerson, status_code=201, summary="Enroll a person from audio")
async def enroll_person_endpoint(
    name: str = Form(..., description="Contact full name"),
    relation: str = Form(..., description="Relationship (Son, Mother, Doctor, etc.)"),
    phone_number: Optional[str] = Form(None),
    person_id: Optional[str] = Form(None, description="Reuse existing person_id to update voiceprints"),
    shared_secrets: Optional[str] = Form(None, description='JSON array of {"question": ..., "answer": ...}'),
    file: UploadFile = File(..., description="Enrollment audio (min 30s of clear speech)"),
    db: Session = Depends(get_db),
) -> EnrolledPerson:
    # ── Validate upload size ──────────────────────────────────────────
    audio_bytes = await file.read()
    if len(audio_bytes) > config.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {config.MAX_UPLOAD_SIZE_MB}MB."
        )

    # ── Ingest audio ──────────────────────────────────────────────────
    ingested = ingest_audio(audio_bytes=audio_bytes)
    if not ingested.quality.passed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Audio quality insufficient for enrollment: {ingested.quality.reason}. "
                f"Please provide at least {config.ENROLL_MIN_SPEECH_S}s of clear speech."
            ),
        )
    if ingested.quality.speech_duration_s < config.ENROLL_MIN_SPEECH_S:
        raise HTTPException(
            status_code=422,
            detail=f"Need at least {config.ENROLL_MIN_SPEECH_S}s of speech. Got {ingested.quality.speech_duration_s:.1f}s.",
        )

    # ── Get or create person ──────────────────────────────────────────
    if person_id:
        db_person = db.query(Person).filter(Person.person_id == person_id).first()
        if not db_person:
            raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found.")
        db_person.name = name
        db_person.relation = relation
        db_person.phone_number = phone_number
    else:
        person_id = f"person_{uuid.uuid4().hex[:10]}"
        db_person = Person(
            person_id=person_id,
            name=name,
            relation=relation,
            phone_number=phone_number,
        )
        db.add(db_person)
        db.flush()

    # ── Call audio_ml.api.enroll_person ──────────────────────────────
    wideband_embedding: list[float] = []
    narrowband_embedding: list[float] = []

    try:
        from audio_ml.api import enroll_person as ml_enroll
        result = ml_enroll(
            person_id=person_id,
            name=name,
            relationship=relation,
            wav_paths=[ingested.normalized_wav_path]
        )
    except ImportError:
        log.error("audio_ml.api not available — cannot enrol")
        raise HTTPException(
            status_code=503,
            detail="Voice enrollment is unavailable on the server (audio_ml not importable).",
        )
    except Exception as e:
        log.error(f"enroll_person ML call failed: {e}")
        raise HTTPException(status_code=500, detail=f"Enrollment ML step failed: {str(e)}")

    # `audio_ml.api.enroll_person` never raises (CLAUDE.md rule 5) — it returns None. So a
    # failure arrives here looking exactly like success, and the endpoint used to fall
    # through, zero-fill the embedding and return 201 Created.
    #
    # That is the worst possible outcome: SQLite gets a person with an all-zero voiceprint
    # and no .npz is written, so `verify_speaker` globs the directory, does not find them,
    # and returns `unknown` forever. `unknown` is a legitimate verdict, so nothing errors —
    # the user simply sees "unverified" for someone they enrolled seconds earlier, and
    # there is no way to tell that from the app working correctly.
    if not result:
        log.error(f"enroll_person returned None for {person_id}; refusing to store a stub")
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not build a voiceprint from that recording. Record again with "
                "more clear speech, closer to the microphone."
            ),
        )

    wideband_embedding = result.get("wb") or []
    narrowband_embedding = result.get("nb8k_sim") or []

    # The .npz on disk is what verify_speaker actually reads; the DB copy is for the UI.
    # If the file is missing the enrollment did not happen, whatever the dict says.
    voiceprint_file = config.ENROLLMENTS_DIR / f"{person_id}.npz"
    if not voiceprint_file.is_file():
        log.error(f"no voiceprint written at {voiceprint_file}")
        raise HTTPException(
            status_code=500,
            detail="The voiceprint could not be saved. Please try again.",
        )


    # ── Store voiceprints (wideband + narrowband) ─────────────────────
    for condition, embedding in [
        (AcousticCondition.WIDEBAND_16K, wideband_embedding),
        (AcousticCondition.NARROWBAND_8K, narrowband_embedding),
    ]:
        if not embedding:
            continue
        vp = Voiceprint(
            voiceprint_id=f"vp_{uuid.uuid4().hex[:10]}",
            person_id=person_id,
            condition=condition.value,
            embedding_blob=Voiceprint.encode_embedding(embedding),
            embedding_dim=len(embedding),
            duration_s=ingested.quality.speech_duration_s,
            snr_db=ingested.quality.snr_db,
        )
        db.add(vp)

    # ── Shared secrets ────────────────────────────────────────────────
    if shared_secrets:
        try:
            secrets_data = json.loads(shared_secrets)
            for item in secrets_data:
                question = item.get("question", "")
                answer = item.get("answer", "")
                if question and answer:
                    answer_hash = hashlib.sha256(answer.lower().strip().encode()).hexdigest()
                    db_secret = DBSecret(
                        secret_id=f"secret_{uuid.uuid4().hex[:8]}",
                        person_id=person_id,
                        question=question,
                        answer_hash=answer_hash,
                        category=item.get("category", "personal"),
                    )
                    db.add(db_secret)
        except json.JSONDecodeError:
            log.warning("Invalid shared_secrets JSON, skipping")

    db.commit()
    db.refresh(db_person)

    from server.persons_router import _db_person_to_contract
    enrolled = _db_person_to_contract(db_person)
    log.info(f"Enrolled person: {person_id} ({name}) — {len(enrolled.voiceprints)} voiceprints")
    return enrolled
