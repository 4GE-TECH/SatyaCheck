"""SatyaCheck — what the API says about an enrolled person.

Server view models, not contracts. They deliberately omit the voice embedding (biometric
data) and the challenge answer hash (an unsalted SHA-256 of a short answer is
guessable), which `contracts.EnrolledPerson` carries for in-process use.

C owns this file.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from pydantic import BaseModel, Field

from server.database import Person


class VoiceprintSummary(BaseModel):
    """A stored voiceprint, described without its vector."""
    voiceprint_id: str
    condition: str = Field(..., description="wb (wideband) · nb8k_sim (phone, simulated) · nb8k_real (phone, recorded)")
    duration_s: float
    snr_db: float
    model_version: str
    created_at: str


class SecretSummary(BaseModel):
    """A challenge question, without its answer hash."""
    secret_id: str
    question: str
    category: str = "personal"


class PersonSummary(BaseModel):
    person_id: str
    name: str
    relation: str
    phone_number: Optional[str] = None
    phone_numbers: list[str] = Field(default_factory=list, description="E.164; untrusted hints, never proof")
    aliases: list[str] = Field(default_factory=list)
    avatar_url: Optional[str] = None
    voiceprints: list[VoiceprintSummary] = Field(default_factory=list)
    shared_secrets: list[SecretSummary] = Field(default_factory=list)
    created_at: str
    consent_recorded_at: Optional[str] = None
    consent_version: Optional[str] = None


_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def clean_phone_numbers(numbers: Optional[Iterable[str]], single: Optional[str] = None) -> list[str]:
    """Distinct E.164 numbers (spaces and dashes removed); anything else is dropped."""
    out: list[str] = []
    for raw in list(numbers or []) + ([single] if single else []):
        n = re.sub(r"[\s\-()]", "", str(raw or ""))
        if _E164.match(n) and n not in out:
            out.append(n)
    return out


def clean_aliases(aliases: Optional[Iterable[str]]) -> list[str]:
    """Distinct non-empty aliases, trimmed, at most 40 characters each."""
    out: list[str] = []
    for raw in aliases or []:
        a = " ".join(str(raw or "").split())[:40]
        if a and a.lower() not in {x.lower() for x in out}:
            out.append(a)
    return out


def person_summary(person: Person) -> PersonSummary:
    return PersonSummary(
        person_id=person.person_id,
        name=person.name,
        relation=person.relation,
        phone_number=person.phone_number,
        phone_numbers=list(person.phone_numbers or []),
        aliases=list(person.aliases or []),
        avatar_url=person.avatar_url,
        voiceprints=[
            VoiceprintSummary(
                voiceprint_id=vp.voiceprint_id,
                condition=vp.condition,
                duration_s=vp.duration_s,
                snr_db=vp.snr_db,
                model_version=vp.model_version,
                created_at=str(vp.created_at),
            )
            for vp in sorted(person.voiceprints, key=lambda v: v.condition)
        ],
        shared_secrets=[
            SecretSummary(secret_id=s.secret_id, question=s.question, category=s.category or "personal")
            for s in person.shared_secrets
        ],
        created_at=str(person.created_at),
        consent_recorded_at=person.consent_recorded_at,
        consent_version=person.consent_version,
    )


if __name__ == "__main__":
    import json

    from server.database import SharedSecret, Voiceprint

    person = Person(person_id="p", name="Ma", relation="Mother", created_at="2026-10-10")
    person.voiceprints = [Voiceprint(voiceprint_id="vp", condition="wb", embedding=[0.1], embedding_dim=1,
                                     duration_s=20.0, snr_db=18.0, model_version="m", created_at="2026-10-10")]
    person.shared_secrets = [SharedSecret(secret_id="s", question="Pet?", answer_hash="h")]
    text = json.dumps(person_summary(person).model_dump())
    assert "embedding" not in text and "answer_hash" not in text
    print(f"[OK] person_views: {text}")
