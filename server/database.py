"""SatyaCheck — SQLite Database Schema

SQLAlchemy + SQLite. All tables created idempotently via init_db().

C owns this file.
"""

from __future__ import annotations

import json
import logging
from typing import Generator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker
from sqlalchemy.sql import func

import config

log = logging.getLogger("satyacheck.db")

# ── Engine ────────────────────────────────────────────────────────────
engine = create_engine(
    f"sqlite:///{config.DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)

# Enable WAL for concurrent readers during streaming
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# ── Models ────────────────────────────────────────────────────────────

class Person(Base):
    """Enrolled contact."""
    __tablename__ = "persons"

    person_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    relation = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    consent_recorded_at = Column(String, nullable=True)   # ISO-8601 UTC, item 16
    consent_version = Column(String, nullable=True)

    voiceprints = relationship("Voiceprint", back_populates="person", cascade="all, delete-orphan")
    shared_secrets = relationship("SharedSecret", back_populates="person", cascade="all, delete-orphan")
    guardian_subs = relationship("GuardianSubscription", back_populates="person", cascade="all, delete-orphan")


class Voiceprint(Base):
    """Condition-matched speaker embedding for an enrolled person."""
    __tablename__ = "voiceprints"

    voiceprint_id = Column(String, primary_key=True)
    person_id = Column(String, ForeignKey("persons.person_id"), nullable=False)
    condition = Column(String, nullable=False)          # AcousticCondition enum value
    embedding_blob = Column(LargeBinary, nullable=False)  # JSON-serialised float list
    embedding_dim = Column(Integer, nullable=False)
    duration_s = Column(Float, nullable=False)
    snr_db = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    person = relationship("Person", back_populates="voiceprints")

    def get_embedding(self) -> list[float]:
        return json.loads(self.embedding_blob.decode())

    @staticmethod
    def encode_embedding(embedding: list[float]) -> bytes:
        return json.dumps(embedding).encode()


class SharedSecret(Base):
    """Challenge question / answer hash for an enrolled person."""
    __tablename__ = "shared_secrets"

    secret_id = Column(String, primary_key=True)
    person_id = Column(String, ForeignKey("persons.person_id"), nullable=False)
    question = Column(Text, nullable=False)
    answer_hash = Column(String, nullable=False)
    category = Column(String, default="personal")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    person = relationship("Person", back_populates="shared_secrets")


class ScreeningSession(Base):
    """Top-level session record for a screening call."""
    __tablename__ = "sessions"

    session_id = Column(String, primary_key=True)
    audio_sha256 = Column(String, nullable=True)
    status = Column(String, default="pending")        # pending | complete | failed
    channel_type = Column(String, default="upload")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    screenings = relationship("ScreeningResult", back_populates="session", cascade="all, delete-orphan")


class ScreeningResult(Base):
    """Stored full ScreeningResponse JSON for a session (one per chunk in streaming)."""
    __tablename__ = "screenings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.session_id"), nullable=False)
    chunk_index = Column(Integer, default=0)
    response_json = Column(Text, nullable=False)       # full ScreeningResponse JSON
    processing_ms = Column(Float, nullable=False)
    is_final = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ScreeningSession", back_populates="screenings")


class FlaggedVoice(Base):
    """Negative voiceprint list — previously confirmed scam callers (FR-15)."""
    __tablename__ = "flagged_voices"

    flagged_id = Column(String, primary_key=True)
    embedding_blob = Column(LargeBinary, nullable=False)
    embedding_dim = Column(Integer, nullable=False)
    incident_category = Column(String, nullable=False)
    source_case_id = Column(String, nullable=True)
    first_reported_at = Column(DateTime(timezone=True), server_default=func.now())

    def get_embedding(self) -> list[float]:
        return json.loads(self.embedding_blob.decode())


class GuardianSubscription(Base):
    """Guardian alert subscriber record."""
    __tablename__ = "guardian_subscriptions"

    sub_id = Column(String, primary_key=True)
    person_id = Column(String, ForeignKey("persons.person_id"), nullable=True)
    endpoint_label = Column(String, nullable=True)       # e.g. "Rahul's phone"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    person = relationship("Person", back_populates="guardian_subs")


class EvidenceLeaf(Base):
    """One guardian alert in the evidence log (server/evidence.py). No audio, no transcript."""
    __tablename__ = "evidence_leaves"

    leaf_index = Column(Integer, primary_key=True, autoincrement=False)
    alert_id = Column(String, nullable=False, unique=True)
    session_id = Column(String, nullable=False, index=True)
    leaf_hash = Column(String, nullable=False)
    canonical_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EvidenceRoot(Base):
    """Every root the evidence log has had, so a rewritten past alert is detectable."""
    __tablename__ = "evidence_roots"

    tree_size = Column(Integer, primary_key=True, autoincrement=False)
    root_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Lifecycle ─────────────────────────────────────────────────────────

#: Columns added after a table first shipped. `create_all` never alters an existing
#: table, so an older satyacheck.db would otherwise fail every query touching these.
_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "persons": [("consent_recorded_at", "VARCHAR"), ("consent_version", "VARCHAR")],
}


def migrate(target_engine=None) -> None:
    """Add any `_ADDED_COLUMNS` an existing database is missing. Idempotent."""
    from sqlalchemy import inspect, text

    target_engine = target_engine or engine
    inspector = inspect(target_engine)
    with target_engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, sql_type in columns:
                if name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
                    log.info(f"DB migration: added {table}.{name}")


def init_db() -> None:
    """Create all tables if they don't already exist, then add any newer columns."""
    Base.metadata.create_all(bind=engine)
    migrate()
    log.info(f"DB initialised at {config.DB_PATH}")


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a DB session, closes on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_person_by_id(person_id: str):
    """Resolve an enrolled person contract by person_id for challenge questions."""
    from contracts import AcousticCondition, EnrolledPerson, SharedSecret as ContractSecret, VoiceprintRecord
    with SessionLocal() as db:
        person = db.query(Person).filter(Person.person_id == person_id).first()
        if not person:
            return None
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
            ContractSecret(
                secret_id=s.secret_id,
                question=s.question,
                answer_hash=s.answer_hash,
                category=s.category or "personal",
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
            consent_recorded_at=person.consent_recorded_at,
            consent_version=person.consent_version,
        )


# ── Smoke test ────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print(f"[OK] DB created at {config.DB_PATH}")
    with SessionLocal() as db:
        person_count = db.query(Person).count()
        print(f"[OK] Persons table accessible — {person_count} rows")
