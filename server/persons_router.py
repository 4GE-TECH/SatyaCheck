"""SatyaCheck — Enrolled Persons CRUD Router

Every route acts for the authenticated account (server/auth.py) and sees only that
account's contacts. Responses are `PersonSummary`: no voice embeddings and no challenge
answer hashes.

C owns this file.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from server import voiceprint_store
from server.auth import current_owner
from server.database import Person, get_owner_db
from server.person_views import PersonSummary, clean_aliases, clean_phone_numbers, person_summary

log = logging.getLogger("satyacheck.persons")
router = APIRouter(prefix="/api/persons", tags=["persons"])


def _owned(db: Session, owner_id: str, person_id: str) -> Person:
    person = (db.query(Person)
              .filter(Person.person_id == person_id, Person.owner_id == owner_id).first())
    if not person:   # another account's person is indistinguishable from none
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found")
    return person


@router.get("", response_model=list[PersonSummary], summary="List your enrolled contacts")
async def list_persons(
    owner_id: str = Depends(current_owner),
    db: Session = Depends(get_owner_db),
) -> list[PersonSummary]:
    persons = db.query(Person).filter(Person.owner_id == owner_id).all()
    return [person_summary(p) for p in persons]


@router.get("/{person_id}", response_model=PersonSummary, summary="Get one of your contacts")
async def get_person(
    person_id: str,
    owner_id: str = Depends(current_owner),
    db: Session = Depends(get_owner_db),
) -> PersonSummary:
    return person_summary(_owned(db, owner_id, person_id))


@router.post("", response_model=PersonSummary, status_code=201, summary="Create a new contact (no audio)")
async def create_person(
    name: str = Query(..., min_length=1),
    relation: str = Query(..., min_length=1),
    phone_number: Optional[str] = Query(None),
    phone_numbers: Optional[list[str]] = Query(None, description="E.164 numbers; untrusted hints"),
    aliases: Optional[list[str]] = Query(None, description="What callers call them: Papa, Dad"),
    owner_id: str = Depends(current_owner),
    db: Session = Depends(get_owner_db),
) -> PersonSummary:
    """Create a contact record without audio. Use /api/enroll to add voiceprints."""
    person = Person(
        person_id=f"person_{uuid.uuid4().hex[:10]}",
        owner_id=owner_id,
        name=name,
        relation=relation,
        phone_number=phone_number,
        phone_numbers=clean_phone_numbers(phone_numbers, phone_number),
        aliases=clean_aliases(aliases),
    )
    db.add(person)
    db.commit()
    db.refresh(person)
    return person_summary(person)


@router.delete("/{person_id}", status_code=200, summary="Delete one of your contacts")
async def delete_person(
    person_id: str,
    owner_id: str = Depends(current_owner),
    db: Session = Depends(get_owner_db),
) -> dict:
    """One transaction removes the person with their voiceprints, secrets, consents,
    guardian subscriptions and idempotency keys. Only after it commits is any legacy .npz
    removed, so a failed delete never leaves a person whose voiceprint file is gone."""
    _owned(db, owner_id, person_id)
    try:
        voiceprint_store.delete_person(db, owner_id, person_id)
        db.commit()
    except Exception as e:
        db.rollback()
        log.error(f"[{person_id}] delete failed, nothing removed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="The contact could not be deleted. Please try again.")

    from audio_ml.api import delete_person as delete_legacy_voiceprint
    legacy_removed = delete_legacy_voiceprint(person_id)
    log.info(f"[{person_id}] deleted (legacy voiceprint file removed: {legacy_removed})")
    return {"deleted": person_id, "voiceprint_deleted": True, "legacy_file_removed": legacy_removed}
