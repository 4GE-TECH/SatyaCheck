"""SatyaCheck — Enrollment Router

Accepts multipart audio upload + person metadata, runs ingestion, computes the
condition-matched voiceprint in memory (audio_ml.api.compute_voiceprint), then writes
the person, the vectors and any challenge secrets in ONE transaction. Either all of it
is stored or none of it is.

Re-enrolling an existing person replaces their vectors (one row per condition and
embedding model). An `Idempotency-Key` header makes a retried upload return the first
result instead of enrolling twice.

Responses are `PersonSummary`: no vectors, no answer hashes.

C owns this file.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import config
from server import voiceprint_store
from server.audio_ingest import discard, ingest_audio
from server.auth import current_owner
from server.database import ConsentRecord, EnrollIdempotency, Person, SharedSecret as DBSecret, get_owner_db
from server.person_views import PersonSummary, clean_aliases, clean_phone_numbers, person_summary

log = logging.getLogger("satyacheck.enroll")
router = APIRouter(prefix="/api/enroll", tags=["enroll"])


def _fingerprint(audio_bytes: bytes, **fields) -> str:
    """The request an Idempotency-Key answered: the audio and every form field."""
    h = hashlib.sha256(hashlib.sha256(audio_bytes).digest())
    h.update(json.dumps(fields, sort_keys=True, default=str).encode())
    return h.hexdigest()


def _replay(db: Session, owner_id: str, key: str, fingerprint: str) -> Optional[PersonSummary]:
    """The stored result for `key`, None if the key is new; 409 if it answered another request."""
    seen = (db.query(EnrollIdempotency)
            .filter(EnrollIdempotency.owner_id == owner_id, EnrollIdempotency.key == key).first())
    if seen is None:
        return None
    if seen.fingerprint != fingerprint:
        raise HTTPException(status_code=409, detail="This Idempotency-Key was already used for a different enrollment.")
    person = (db.query(Person)
              .filter(Person.person_id == seen.person_id, Person.owner_id == owner_id).first())
    if person is None:   # cascades make this unreachable; refuse rather than re-enroll silently
        raise HTTPException(status_code=409, detail="This Idempotency-Key belongs to a deleted contact.")
    log.info(f"[{seen.person_id}] enrollment replayed for Idempotency-Key (no recomputation)")
    return person_summary(person)


def _add_secrets(db: Session, person_id: str, shared_secrets: Optional[str]) -> None:
    if not shared_secrets:
        return
    try:
        secrets_data = json.loads(shared_secrets)
    except json.JSONDecodeError:
        log.warning(f"[{person_id}] invalid shared_secrets JSON, skipping")
        return
    for item in secrets_data if isinstance(secrets_data, list) else []:
        question = (item or {}).get("question", "")
        answer = (item or {}).get("answer", "")
        if question and answer:
            db.add(DBSecret(
                secret_id=f"secret_{uuid.uuid4().hex[:8]}",
                person_id=person_id,
                question=question,
                answer_hash=hashlib.sha256(answer.lower().strip().encode()).hexdigest(),
                category=item.get("category", "personal"),
            ))


@router.post("", response_model=PersonSummary, status_code=201, summary="Enroll a person from audio")
async def enroll_person_endpoint(
    name: str = Form(..., description="Contact full name"),
    relation: str = Form(..., description="Relationship (Son, Mother, Doctor, etc.)"),
    phone_number: Optional[str] = Form(None),
    person_id: Optional[str] = Form(None, description="Reuse existing person_id to replace voiceprints"),
    shared_secrets: Optional[str] = Form(None, description='JSON array of {"question": ..., "answer": ...}'),
    file: UploadFile = File(..., description="Enrollment audio (at least ENROLL_MIN_SPEECH_S of clear speech)"),
    consent: bool = Form(False, description="The person being enrolled consents to voiceprint storage"),
    phone_numbers: Optional[list[str]] = Form(None, description="E.164 numbers; untrusted hints"),
    aliases: Optional[list[str]] = Form(None, description="What callers call them: Papa, Dad"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    owner_id: str = Depends(current_owner),
    db: Session = Depends(get_owner_db),
) -> PersonSummary:
    # -- Consent, before any audio is read (DPDP Act 2023, item 16) --
    if config.REQUIRE_ENROLL_CONSENT and not consent:
        raise HTTPException(
            status_code=422,
            detail="Consent is required: a voiceprint is biometric data. Send consent=true "
                   "only after the person being enrolled has agreed.",
        )
    audio_bytes = await file.read()
    if len(audio_bytes) > config.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Max {config.MAX_UPLOAD_SIZE_MB}MB.")

    fingerprint = None
    if idempotency_key:
        fingerprint = _fingerprint(audio_bytes, name=name, relation=relation, phone_number=phone_number,
                                   person_id=person_id, shared_secrets=shared_secrets, consent=consent,
                                   phone_numbers=phone_numbers, aliases=aliases)
        replayed = _replay(db, owner_id, idempotency_key, fingerprint)
        if replayed is not None:
            return replayed

    if person_id and not (db.query(Person)
                          .filter(Person.person_id == person_id, Person.owner_id == owner_id).first()):
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found.")

    ingested = ingest_audio(audio_bytes=audio_bytes)
    try:
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

        # -- Compute the voiceprint (seconds of CPU: off the event loop) --
        try:
            from audio_ml.api import compute_voiceprint
        except ImportError:
            log.error("audio_ml.api not available — cannot enrol")
            raise HTTPException(status_code=503, detail="Voice enrollment is unavailable on the server.")
        vectors = await asyncio.to_thread(compute_voiceprint, [ingested.normalized_wav_path])
        # compute_voiceprint never raises (CLAUDE.md rule 5): a failure arrives as None, which
        # must become a refusal here, never a 201 for a person nobody can be matched against.
        label = person_id or "new person"
        if not vectors:
            log.error(f"[{label}] compute_voiceprint produced no voiceprint "
                      f"({ingested.quality.speech_duration_s:.1f}s speech); refusing to store a stub")
            raise HTTPException(
                status_code=422,
                detail="Could not build a voiceprint from that recording. Record again with "
                       "more clear speech, closer to the microphone.",
            )

        # -- One transaction: person, vectors, secrets, idempotency key --
        now = datetime.now(timezone.utc).isoformat()
        try:
            if person_id:
                db_person = (db.query(Person)
                             .filter(Person.person_id == person_id, Person.owner_id == owner_id).first())
                db_person.name = name
                db_person.relation = relation
                db_person.phone_number = phone_number
            else:
                person_id = f"person_{uuid.uuid4().hex[:10]}"
                db_person = Person(person_id=person_id, owner_id=owner_id, name=name, relation=relation,
                                   phone_number=phone_number)
                db.add(db_person)
                db.flush()
            if phone_numbers is not None or phone_number:
                db_person.phone_numbers = clean_phone_numbers(phone_numbers, phone_number)
            if aliases is not None:
                db_person.aliases = clean_aliases(aliases)
            if consent:
                db_person.consent_recorded_at = now
                db_person.consent_version = config.CONSENT_TEXT_VERSION
                db.add(ConsentRecord(consent_id=f"consent_{uuid.uuid4().hex[:10]}", owner_id=owner_id,
                                     person_id=person_id, consent_text_version=config.CONSENT_TEXT_VERSION,
                                     recorded_by=owner_id))

            saved = voiceprint_store.save_voiceprints(
                db, owner_id, person_id, vectors,
                duration_s=ingested.quality.speech_duration_s, snr_db=ingested.quality.snr_db,
            )
            if not saved:
                db.rollback()
                log.error(f"[{person_id}] compute_voiceprint returned no usable vector; nothing stored")
                raise HTTPException(
                    status_code=422,
                    detail="Could not build a usable voiceprint from that recording. Please record again.",
                )
            _add_secrets(db, person_id, shared_secrets)
            if idempotency_key:
                db.add(EnrollIdempotency(owner_id=owner_id, key=idempotency_key, person_id=person_id,
                                         fingerprint=fingerprint))
            db.commit()
        except HTTPException:
            raise
        except IntegrityError as e:
            db.rollback()
            if idempotency_key:   # a concurrent retry with the same key won the race
                replayed = _replay(db, owner_id, idempotency_key, fingerprint)
                if replayed is not None:
                    return replayed
            log.error(f"[{person_id}] enrollment write failed, rolled back: {e}")
            raise HTTPException(status_code=500, detail="The voiceprint could not be saved. Please try again.")
        except Exception as e:
            db.rollback()
            log.error(f"[{person_id}] enrollment write failed, rolled back: {type(e).__name__}: {e}")
            raise HTTPException(status_code=500, detail="The voiceprint could not be saved. Please try again.")

        db.refresh(db_person)
        log.info(f"Enrolled person: {person_id} ({name}) — voiceprints {saved}")
        return person_summary(db_person)
    finally:
        # Every exit — success, 422, 500 — or the temp WAV outlives the request.
        discard(ingested)
