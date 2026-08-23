"""SatyaCheck — Enrolled Persons CRUD Router

C owns this file.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from contracts import EnrolledPerson, SharedSecret, VoiceprintRecord, AcousticCondition
from server.database import Person, Voiceprint, SharedSecret as DBSecret, get_db

router = APIRouter(prefix="/api/persons", tags=["persons"])


def _db_person_to_contract(person: Person) -> EnrolledPerson:
    voiceprints = [
        VoiceprintRecord(
            voiceprint_id=vp.voiceprint_id,
            person_id=vp.person_id,
            condition=AcousticCondition(vp.condition),
            embedding=vp.get_embedding(),
            duration_s=vp.duration_s,
            snr_db=vp.snr_db,
            created_at=str(vp.created_at),
        )
        for vp in person.voiceprints
    ]
    secrets = [
        SharedSecret(
            secret_id=s.secret_id,
            question=s.question,
            answer_hash=s.answer_hash,
            category=s.category,
        )
        for s in person.shared_secrets
    ]
    return EnrolledPerson(
        person_id=person.person_id,
        name=person.name,
        relation=person.relation,
        phone_number=person.phone_number,
        avatar_url=person.avatar_url,
        voiceprints=voiceprints,
        shared_secrets=secrets,
        created_at=str(person.created_at),
    )


@router.get("", response_model=list[EnrolledPerson], summary="List all enrolled contacts")
async def list_persons(
    db: Session = Depends(get_db),
) -> list[EnrolledPerson]:
    persons = db.query(Person).all()
    return [_db_person_to_contract(p) for p in persons]


@router.get("/{person_id}", response_model=EnrolledPerson, summary="Get a single enrolled contact")
async def get_person(
    person_id: str,
    db: Session = Depends(get_db),
) -> EnrolledPerson:
    person = db.query(Person).filter(Person.person_id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found")
    return _db_person_to_contract(person)


@router.post("", response_model=EnrolledPerson, status_code=201, summary="Create a new contact (no audio)")
async def create_person(
    name: str = Query(..., min_length=1),
    relation: str = Query(..., min_length=1),
    phone_number: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> EnrolledPerson:
    """Create a contact record without audio. Use /api/enroll to add voiceprints."""
    person_id = f"person_{uuid.uuid4().hex[:10]}"
    person = Person(
        person_id=person_id,
        name=name,
        relation=relation,
        phone_number=phone_number,
    )
    db.add(person)
    db.commit()
    db.refresh(person)
    return _db_person_to_contract(person)


@router.delete("/{person_id}", status_code=200, summary="Delete an enrolled contact")
async def delete_person(
    person_id: str,
    db: Session = Depends(get_db),
) -> dict:
    person = db.query(Person).filter(Person.person_id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail=f"Person '{person_id}' not found")
    db.delete(person)
    db.commit()
    return {"deleted": person_id}
