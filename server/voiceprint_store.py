"""SatyaCheck — the voiceprint store.

The database is the one place voiceprints live (upgrade plan, Phase 0). Enrollment writes
here and verification reads here, so the UI's list of people and the people the
verifier compares against can no longer disagree.

Every function takes a REQUIRED owner_id (Phase 1): one account's verifier never sees
another account's voices. On Postgres, row-level security enforces the same rule again.

Vectors are validated on the way in (192 finite values, renormalised to unit length)
and on the way out. Rows are keyed by (person_id, condition, model_version), so
re-enrollment replaces a vector rather than appending one, and a vector from a
different embedding model is never compared.

Functions here never commit; the caller owns the transaction.

C owns this file.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

import config
from server.database import FlaggedVoice, Person, Voiceprint

log = logging.getLogger("satyacheck.voiceprints")

EMBEDDING_DIM = 192
#: audio_ml's condition keys, in the order verify_speaker scores them.
CONDITIONS = ("wb", "nb8k_real", "nb8k_sim")


class NotOwned(LookupError):
    """The person does not exist for this owner (whether or not it exists for another)."""


def _require_owner(owner_id: str) -> str:
    if not owner_id:
        raise ValueError("an owner_id is required")
    return owner_id


def validate_vector(vector) -> Optional[list[float]]:
    """A unit-length list of 192 finite floats, or None if `vector` is not usable."""
    try:
        if vector is None or isinstance(vector, (str, bytes)):
            return None
        v = np.asarray(vector, dtype=np.float64).reshape(-1)
        if v.shape[0] != EMBEDDING_DIM or not np.all(np.isfinite(v)):
            return None
        norm = float(np.linalg.norm(v))
        if not norm > 1e-9:
            return None
        return (v / norm).tolist()
    except (TypeError, ValueError):
        return None


def save_voiceprints(
    db: Session,
    owner_id: str,
    person_id: str,
    vectors: dict,
    duration_s: float,
    snr_db: float,
    model_version: Optional[str] = None,
) -> list[str]:
    """Insert or replace one row per condition in `vectors`. Returns the conditions saved.

    Raises NotOwned if `person_id` is not this owner's. Keys that are not conditions
    (e.g. "n_samples") are ignored; an unusable vector is dropped and logged. Conditions
    not in `vectors` keep their existing row.
    """
    _require_owner(owner_id)
    if db.query(Person.person_id).filter(Person.person_id == person_id,
                                          Person.owner_id == owner_id).first() is None:
        raise NotOwned(person_id)
    model_version = model_version or config.SPEAKER_MODEL_VERSION
    saved: list[str] = []
    for condition in CONDITIONS:
        if condition not in vectors:
            continue
        embedding = validate_vector(vectors[condition])
        if embedding is None:
            log.warning(f"[{person_id}] {condition} voiceprint dropped: not {EMBEDDING_DIM} finite values")
            continue
        row = (db.query(Voiceprint)
               .filter(Voiceprint.person_id == person_id, Voiceprint.condition == condition,
                       Voiceprint.model_version == model_version)
               .first())
        if row is None:
            row = Voiceprint(voiceprint_id=f"vp_{uuid.uuid4().hex[:10]}", person_id=person_id,
                             condition=condition, model_version=model_version)
            db.add(row)
        row.embedding = embedding
        row.embedding_dim = EMBEDDING_DIM
        row.duration_s = float(duration_s)
        row.snr_db = float(snr_db)
        saved.append(condition)
    ignored = sorted(k for k in vectors if k not in CONDITIONS and k != "n_samples")
    if ignored:
        log.warning(f"[{person_id}] ignored unknown voiceprint condition(s): {ignored}")
    db.flush()
    return saved


def get_candidates(
    db: Session,
    owner_id: str,
    person_id: Optional[str] = None,
    model_version: Optional[str] = None,
) -> list[dict]:
    """This owner's enrolled people with at least one usable vector, in the shape
    verify_speaker takes: {"person_id", "name", "relationship", "centroids": {condition: array}}."""
    _require_owner(owner_id)
    model_version = model_version or config.SPEAKER_MODEL_VERSION
    query = (db.query(Voiceprint, Person)
             .join(Person, Person.person_id == Voiceprint.person_id)
             .filter(Person.owner_id == owner_id, Voiceprint.model_version == model_version))
    if person_id is not None:
        query = query.filter(Voiceprint.person_id == person_id)

    by_person: dict[str, dict] = {}
    for vp, person in query.order_by(Voiceprint.person_id):
        if vp.condition not in CONDITIONS:
            log.warning(f"voiceprint {vp.voiceprint_id}: unknown condition {vp.condition!r}, skipped")
            continue
        embedding = validate_vector(vp.get_embedding())
        if embedding is None:
            log.error(f"voiceprint {vp.voiceprint_id}: unreadable or invalid vector, skipped")
            continue
        entry = by_person.setdefault(person.person_id, {
            "person_id": person.person_id,
            "name": person.name,
            "relationship": person.relation,
            "centroids": {},
        })
        entry["centroids"][vp.condition] = np.asarray(embedding, dtype=np.float32)
    return list(by_person.values())


def delete_person(db: Session, owner_id: str, person_id: str) -> bool:
    """Delete one of this owner's people with everything hanging off them (voiceprints,
    secrets, consents, guardian subscriptions, idempotency keys). False if not theirs."""
    _require_owner(owner_id)
    person = db.query(Person).filter(Person.person_id == person_id, Person.owner_id == owner_id).first()
    if person is None:
        return False
    db.delete(person)
    db.flush()
    return True


def add_flagged_voice(db: Session, owner_id: str, vector, incident_category: str,
                      source_case_id: Optional[str] = None) -> Optional[str]:
    """Add a confirmed scam caller's voice to this owner's flagged list. Returns its id,
    or None (logged) if the vector is unusable."""
    _require_owner(owner_id)
    embedding = validate_vector(vector)
    if embedding is None:
        log.warning(f"flagged voice for {source_case_id or 'unknown case'} dropped: invalid vector")
        return None
    flagged_id = f"flag_{uuid.uuid4().hex[:10]}"
    db.add(FlaggedVoice(flagged_id=flagged_id, owner_id=owner_id, embedding=embedding,
                        embedding_dim=EMBEDDING_DIM, incident_category=incident_category,
                        source_case_id=source_case_id))
    db.flush()
    return flagged_id


def get_flagged(db: Session, owner_id: str) -> list[np.ndarray]:
    """This owner's flagged voices, as unit vectors, for verify_speaker's `flagged=`."""
    _require_owner(owner_id)
    out = []
    for row in db.query(FlaggedVoice).filter(FlaggedVoice.owner_id == owner_id):
        embedding = validate_vector(row.get_embedding())
        if embedding is None:
            log.error(f"flagged voice {row.flagged_id}: unreadable or invalid vector, skipped")
            continue
        out.append(np.asarray(embedding, dtype=np.float32))
    return out


if __name__ == "__main__":
    # Smoke test: round-trip one person through an in-memory database.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from server.database import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    vector = np.random.default_rng(0).standard_normal(EMBEDDING_DIM)
    with sessionmaker(bind=engine)() as db:
        db.add(Person(person_id="p_smoke", owner_id="o1", name="Smoke", relation="Test"))
        db.flush()
        saved = save_voiceprints(db, "o1", "p_smoke", {"wb": vector, "nb8k_sim": vector * 2},
                                 duration_s=20, snr_db=20)
        db.commit()
        cands = get_candidates(db, "o1")
        assert get_candidates(db, "o2") == [], "another owner sees nobody"
    assert saved == ["wb", "nb8k_sim"] and cands[0]["person_id"] == "p_smoke"
    assert validate_vector([float("nan")] * EMBEDDING_DIM) is None
    print(f"[OK] voiceprint_store: saved {saved}, {len(cands)} candidate(s) for o1, 0 for o2")
