"""SatyaCheck — database schema and sessions.

SQLite for dev and tests; Postgres (Supabase, pgvector, row-level security) when
config.DATABASE_URL says so. One schema, two dialects:

  * every row that belongs to someone carries `owner_id` (voiceprints and secrets through
    their person), and every repository call is scoped to one owner;
  * on Postgres each transaction also sets `app.owner_id` (SET LOCAL semantics, safe with
    transaction-mode pooling), which the RLS policies in server/migrations/ read — so a
    query that forgot its owner filter still sees nothing of anyone else's;
  * embeddings are pgvector `vector(192)` on Postgres and a JSON blob on SQLite.

The Postgres schema is created by Alembic (server/migrations/); `init_db` only creates
and patches the SQLite dev database.

C owns this file.
"""

from __future__ import annotations

import contextvars
import json
import logging
from typing import Generator, Optional

from fastapi import Depends
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator

import config
from server.auth import current_owner

log = logging.getLogger("satyacheck.db")

EMBEDDING_DIM = 192

#: The owner the current in-process lookup acts for (nlp_rag's challenge lookup has no
#: owner parameter of its own). Set around the call by server/orchestrator.py.
current_owner_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("owner_id", default=None)


# ── Engine ────────────────────────────────────────────────────────────

def database_url(url: Optional[str] = None) -> str:
    """The SQLAlchemy URL: DATABASE_URL (postgres, psycopg 3 driver) or the SQLite file."""
    url = url if url is not None else config.DATABASE_URL
    if not url:
        return f"sqlite:///{config.DB_PATH}"
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: Optional[str] = None) -> Engine:
    url = database_url(url)
    if url.startswith("sqlite"):
        eng = create_engine(url, connect_args={"check_same_thread": False}, echo=False)

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")   # concurrent readers during streaming
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return eng
    # prepare_threshold=None: psycopg 3 otherwise prepares repeated queries server-side,
    # which breaks behind Supabase's transaction pooler (port 6543), where consecutive
    # transactions may land on different server connections.
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, echo=False,
                         connect_args={"prepare_threshold": None})


engine = make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def is_postgres(bind) -> bool:
    return getattr(getattr(bind, "dialect", None), "name", "") == "postgresql"


@event.listens_for(Session, "after_begin")
def _scope_transaction(session: Session, transaction, connection) -> None:
    """Postgres only: tag the transaction with its owner (and test schema) for RLS.
    `set_config(..., true)` is transaction-local, so a pooled connection never carries
    one owner's scope into the next transaction."""
    if connection.dialect.name != "postgresql":
        return
    schema = config.DB_SCHEMA
    search_path = "public, extensions" if schema == "public" else f'"{schema}", public, extensions'
    connection.execute(
        text("SELECT set_config('app.owner_id', :owner, true), set_config('search_path', :path, true)"),
        {"owner": session.info.get("owner_id") or "", "path": search_path},
    )


def owner_session(owner_id: str) -> Session:
    """A session scoped to one owner. Every query through it must filter by owner_id too
    (SQLite has no RLS); on Postgres RLS enforces it regardless."""
    if not owner_id:
        raise ValueError("owner_session needs an owner_id")
    db = SessionLocal()
    db.info["owner_id"] = owner_id
    return db


def get_owner_db(owner_id: str = Depends(current_owner)) -> Generator[Session, None, None]:
    """FastAPI dependency: a session scoped to the authenticated owner."""
    db = owner_session(owner_id)
    try:
        yield db
    finally:
        db.close()


# ── Types ─────────────────────────────────────────────────────────────

class Embedding(TypeDecorator):
    """A speaker embedding: pgvector on Postgres, JSON bytes on SQLite. Reads back as a
    list of floats, or None when a stored value cannot be decoded (logged by the caller)."""
    impl = LargeBinary
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector
            return dialect.type_descriptor(Vector(EMBEDDING_DIM))
        return dialect.type_descriptor(LargeBinary())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        values = [float(x) for x in value]
        return values if dialect.name == "postgresql" else json.dumps(values).encode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            if dialect.name == "postgresql":
                return [float(x) for x in value]
            return [float(x) for x in json.loads(value.decode() if isinstance(value, bytes) else value)]
        except (ValueError, TypeError, UnicodeDecodeError):
            return None


#: A list of strings: text[] on Postgres, JSON on SQLite.
StringList = JSON().with_variant(ARRAY(String), "postgresql")


class Base(DeclarativeBase):
    pass


# ── Models ────────────────────────────────────────────────────────────

class Person(Base):
    """Enrolled contact, owned by one account."""
    __tablename__ = "persons"

    person_id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    relation = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    phone_numbers = Column(StringList, nullable=True)    # E.164; untrusted hints, never proof
    aliases = Column(StringList, nullable=True)          # "Papa", "Dad"; transcript claim matching
    avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    consent_recorded_at = Column(String, nullable=True)   # ISO-8601 UTC, item 16
    consent_version = Column(String, nullable=True)

    voiceprints = relationship("Voiceprint", back_populates="person", cascade="all, delete-orphan")
    shared_secrets = relationship("SharedSecret", back_populates="person", cascade="all, delete-orphan")
    guardian_subs = relationship("GuardianSubscription", back_populates="person", cascade="all, delete-orphan")
    idempotency_keys = relationship("EnrollIdempotency", cascade="all, delete-orphan")
    consents = relationship("ConsentRecord", cascade="all, delete-orphan")


class Voiceprint(Base):
    """Condition-matched speaker embedding for an enrolled person.

    One row per (person, condition, embedding model): re-enrollment replaces the vector.
    `condition` is audio_ml's key (`wb`, `nb8k_sim`, `nb8k_real`). Only
    server/voiceprint_store.py writes or reads the vectors. Owned through its person.
    """
    __tablename__ = "voiceprints"
    __table_args__ = (
        Index("uq_voiceprints_person_condition_model", "person_id", "condition", "model_version", unique=True),
    )

    voiceprint_id = Column(String, primary_key=True)
    person_id = Column(String, ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False)
    condition = Column(String, nullable=False)
    embedding = Column(Embedding, nullable=False)
    embedding_dim = Column(Integer, nullable=False)
    duration_s = Column(Float, nullable=False)
    snr_db = Column(Float, nullable=False)
    model_version = Column(String, nullable=False, default="legacy")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    person = relationship("Person", back_populates="voiceprints")

    def get_embedding(self) -> Optional[list[float]]:
        return self.embedding


class EnrollIdempotency(Base):
    """An Idempotency-Key seen on /api/enroll, so a retried upload returns the first result.
    Keyed per owner: one account's key can neither collide with nor reveal another's."""
    __tablename__ = "enroll_idempotency"

    owner_id = Column(String, primary_key=True)
    key = Column(String, primary_key=True)
    person_id = Column(String, ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False)
    fingerprint = Column(String, nullable=False)     # sha256 of the request it answered
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ConsentRecord(Base):
    """Who agreed to a voiceprint being stored, when, and to which wording (DPDP Act 2023)."""
    __tablename__ = "consents"

    consent_id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False, index=True)
    person_id = Column(String, ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False)
    consent_text_version = Column(String, nullable=False)
    recorded_by = Column(String, nullable=False)     # the account that recorded it
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())


class SharedSecret(Base):
    """Challenge question / answer hash for an enrolled person. Owned through its person."""
    __tablename__ = "shared_secrets"

    secret_id = Column(String, primary_key=True)
    person_id = Column(String, ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False)
    question = Column(Text, nullable=False)
    answer_hash = Column(String, nullable=False)
    category = Column(String, default="personal")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    person = relationship("Person", back_populates="shared_secrets")


class ScreeningSession(Base):
    """Top-level session record for a screening call."""
    __tablename__ = "sessions"

    session_id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False, index=True)
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
    owner_id = Column(String, nullable=False, index=True)
    session_id = Column(String, ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, default=0)
    response_json = Column(Text, nullable=False)       # full ScreeningResponse JSON
    processing_ms = Column(Float, nullable=False)
    is_final = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ScreeningSession", back_populates="screenings")


class FlaggedVoice(Base):
    """Negative voiceprint list — previously confirmed scam callers (FR-15), per owner."""
    __tablename__ = "flagged_voices"

    flagged_id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False, index=True)
    embedding = Column(Embedding, nullable=False)
    embedding_dim = Column(Integer, nullable=False)
    incident_category = Column(String, nullable=False)
    source_case_id = Column(String, nullable=True)
    first_reported_at = Column(DateTime(timezone=True), server_default=func.now())

    def get_embedding(self) -> Optional[list[float]]:
        return self.embedding


class GuardianSubscription(Base):
    """Guardian alert subscriber record."""
    __tablename__ = "guardian_subscriptions"

    sub_id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False, index=True)
    person_id = Column(String, ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=True)
    endpoint_label = Column(String, nullable=True)       # e.g. "Rahul's phone"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    person = relationship("Person", back_populates="guardian_subs")


class LlmShadowRecord(Base):
    """One shadow reading of a committed transcript (server/llm_shadow.py, Phase 4).
    Counts and statuses only — never transcript text. Zero influence on any verdict."""
    __tablename__ = "llm_shadow"

    record_id = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    transcript_rev = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False)          # ok | timeout | error | off
    record_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EvidenceLeaf(Base):
    """One guardian alert in the evidence log (server/evidence.py). No audio, no transcript.

    The log is one append-only tree across all accounts (its root covers every leaf), so
    these tables carry no per-owner RLS. The API serves only hashes, and a proof only to
    the owner of the session it belongs to (server/evidence_router.py).
    """
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


# ── Lifecycle (SQLite dev database) ───────────────────────────────────

#: Columns added after a table first shipped. `create_all` never alters an existing
#: table, so an older satyacheck.db would otherwise fail every query touching these.
#: Rows that predate ownership get the dev owner: on a dev machine they were the dev's.
_ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "persons": [("consent_recorded_at", "VARCHAR"), ("consent_version", "VARCHAR"),
                ("owner_id", "VARCHAR"), ("phone_numbers", "JSON"), ("aliases", "JSON")],
    "voiceprints": [("model_version", "VARCHAR NOT NULL DEFAULT 'legacy'")],
    "sessions": [("owner_id", "VARCHAR")],
    "screenings": [("owner_id", "VARCHAR")],
    "flagged_voices": [("owner_id", "VARCHAR")],
    "guardian_subscriptions": [("owner_id", "VARCHAR")],
}
_OWNED_TABLES = ("persons", "sessions", "screenings", "flagged_voices", "guardian_subscriptions", "llm_shadow")

#: Condition names stored before the voiceprint store used audio_ml's keys.
_LEGACY_CONDITIONS = {"wideband_16k": "wb", "narrowband_8k": "nb8k_sim"}


def migrate(target_engine=None) -> None:
    """Bring an existing SQLite database up to the current schema. Idempotent.
    Postgres is migrated by Alembic instead (server/migrations/)."""
    from sqlalchemy import inspect

    target_engine = target_engine or engine
    if is_postgres(target_engine):
        return
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

        for table in ("voiceprints", "flagged_voices"):
            if inspector.has_table(table):
                cols = {c["name"] for c in inspector.get_columns(table)}
                if "embedding_blob" in cols and "embedding" not in cols:
                    conn.execute(text(f"ALTER TABLE {table} RENAME COLUMN embedding_blob TO embedding"))
                    log.info(f"DB migration: {table}.embedding_blob renamed to embedding")

        for table in _OWNED_TABLES:
            if inspector.has_table(table):
                n = conn.execute(text(f"UPDATE {table} SET owner_id = :o WHERE owner_id IS NULL"),
                                 {"o": config.DEV_OWNER_ID}).rowcount
                if n:
                    log.info(f"DB migration: {n} unowned {table} row(s) assigned to {config.DEV_OWNER_ID}")

        if inspector.has_table("enroll_idempotency"):
            cols = {c["name"] for c in inspector.get_columns("enroll_idempotency")}
            if "owner_id" not in cols:   # retry keys only; recreated per owner below
                conn.execute(text("DROP TABLE enroll_idempotency"))
                log.info("DB migration: enroll_idempotency rebuilt with per-owner keys")

        if inspector.has_table("voiceprints"):
            # Re-enrollment used to append. Map the old condition names, keep the newest
            # row per key, then let the database enforce the key.
            for old, new in _LEGACY_CONDITIONS.items():
                conn.execute(text("UPDATE voiceprints SET condition = :new WHERE condition = :old"),
                             {"new": new, "old": old})
            dropped = conn.execute(text(
                "DELETE FROM voiceprints WHERE rowid NOT IN (SELECT MAX(rowid) FROM voiceprints "
                "GROUP BY person_id, condition, model_version)")).rowcount
            if dropped:
                log.info(f"DB migration: removed {dropped} superseded voiceprint row(s)")
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_voiceprints_person_condition_model "
                              "ON voiceprints (person_id, condition, model_version)"))
    Base.metadata.create_all(bind=target_engine)   # tables dropped or new above


def init_db() -> None:
    """SQLite: create missing tables and patch older ones. Postgres: only check that
    Alembic has created the schema (the app role cannot create tables)."""
    if is_postgres(engine):
        from sqlalchemy import inspect

        if not inspect(engine).has_table("persons", schema=config.DB_SCHEMA):
            log.error("DB: Postgres schema missing — run `alembic -c server/migrations/alembic.ini upgrade head` "
                      "with DATABASE_ADMIN_URL set")
        else:
            log.info(f"DB: Postgres schema '{config.DB_SCHEMA}' present")
        return
    Base.metadata.create_all(bind=engine)
    migrate()
    log.info(f"DB initialised at {config.DB_PATH}")


def get_person_by_id(person_id: str):
    """Resolve an enrolled person contract by person_id for challenge questions.

    In-process only (nlp_rag's challenge lookup), so it keeps the answer hashes. Scoped to
    `current_owner_var`: with no owner set it finds nobody. Carries no voiceprints.
    """
    from contracts import EnrolledPerson, SharedSecret as ContractSecret

    owner_id = current_owner_var.get()
    if not owner_id or not person_id:
        if person_id:
            log.warning(f"challenge lookup for {person_id} without an owner scope; refused")
        return None
    with owner_session(owner_id) as db:
        person = (db.query(Person)
                  .filter(Person.person_id == person_id, Person.owner_id == owner_id).first())
        if not person:
            return None
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
            shared_secrets=secrets,
            created_at=str(person.created_at),
            consent_recorded_at=person.consent_recorded_at,
            consent_version=person.consent_version,
        )


# ── Smoke test ────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print(f"[OK] DB at {database_url().split('@')[-1]}")
    with owner_session(config.DEV_OWNER_ID) as db:
        person_count = db.query(Person).filter(Person.owner_id == config.DEV_OWNER_ID).count()
        print(f"[OK] Persons table accessible — {person_count} rows for {config.DEV_OWNER_ID}")
