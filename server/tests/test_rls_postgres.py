"""Upgrade plan, Phase 1: Postgres row-level security is real defence in depth.

These run only when TEST_DATABASE_ADMIN_URL is set (environment or the git-ignored .env)
— e.g. a Supabase session-pooler URL for the `postgres` user. Each run:

  1. creates a throwaway schema and runs the Alembic migration into it, with a test app
     role (`satyacheck_app_test`, never the production role) and a random password;
  2. connects AS that role, exactly like the backend does, through a pool of one
     connection, so scope leaking between transactions would show;
  3. checks that queries WITHOUT any owner filter still see only their own account;
  4. drops the schema.

The application's own owner filters are tested on SQLite (test_tenancy.py). Here the
filters are deliberately left out, so only RLS stands between the accounts.
"""

from __future__ import annotations

import os
import secrets
import uuid

import numpy as np
import pytest
from sqlalchemy import create_engine, text

import config

ADMIN_URL = os.getenv("TEST_DATABASE_ADMIN_URL") or config.read_dotenv(config.REPO_ROOT / ".env").get(
    "TEST_DATABASE_ADMIN_URL", "")
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="set TEST_DATABASE_ADMIN_URL to run the Postgres RLS tests")

ROLE = "satyacheck_app_test"
A, B = "account-a", "account-b"


def _unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(192).astype(np.float32)
    return v / np.linalg.norm(v)


def _app_url(admin_url: str, password: str) -> str:
    """The admin URL with the test role's credentials. Supabase's pooler names a user
    `<role>.<project-ref>`; a direct connection just `<role>`."""
    from sqlalchemy.engine import make_url

    url = make_url(admin_url)
    user = url.username or ""
    username = f"{ROLE}.{user.split('.', 1)[1]}" if "." in user else ROLE
    return url.set(username=username, password=password).render_as_string(hide_password=False)


@pytest.fixture(scope="module")
def pg(request):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.orm import sessionmaker

    from server import database

    schema = f"satyacheck_test_{uuid.uuid4().hex[:8]}"
    password = secrets.token_urlsafe(24)
    saved = {k: getattr(config, k) for k in ("DATABASE_ADMIN_URL", "DB_SCHEMA", "DB_APP_ROLE", "DB_APP_PASSWORD")}
    config.DATABASE_ADMIN_URL, config.DB_SCHEMA = ADMIN_URL, schema
    config.DB_APP_ROLE, config.DB_APP_PASSWORD = ROLE, password
    admin = database.make_engine(ADMIN_URL)
    try:
        command.upgrade(Config(str(config.REPO_ROOT / "server" / "migrations" / "alembic.ini")), "head")
        app_engine = create_engine(database.database_url(_app_url(ADMIN_URL, password)),
                                   pool_size=1, max_overflow=0, pool_pre_ping=True)
        factory = sessionmaker(bind=app_engine, autoflush=False, autocommit=False)
        yield {"factory": factory, "admin": admin, "schema": schema}
        app_engine.dispose()
    finally:
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            conn.execute(text(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') "
                              f"THEN REVOKE ALL ON SCHEMA extensions FROM {ROLE}; DROP ROLE {ROLE}; "
                              f"END IF; END $$"))
        admin.dispose()
        for k, v in saved.items():
            setattr(config, k, v)


def _session(pg, owner):
    db = pg["factory"]()
    if owner is not None:
        db.info["owner_id"] = owner
    return db


@pytest.fixture
def seeded(pg):
    """A's person with vectors and a secret; B's person. Written through the app role."""
    from server import voiceprint_store
    from server.database import Person, SharedSecret

    suffix = uuid.uuid4().hex[:6]
    ids = {"a": f"pa_{suffix}", "b": f"pb_{suffix}"}
    for owner, pid, seed in ((A, ids["a"], 1), (B, ids["b"], 2)):
        with _session(pg, owner) as db:
            db.add(Person(person_id=pid, owner_id=owner, name="P", relation="R"))
            db.flush()
            voiceprint_store.save_voiceprints(db, owner, pid, {"wb": _unit(seed)}, duration_s=20, snr_db=20)
            db.add(SharedSecret(secret_id=f"s_{pid}", person_id=pid, question="Q", answer_hash="h"))
            db.commit()
    return ids


def test_unfiltered_queries_see_only_the_scoped_account(pg, seeded):
    from server.database import Person, SharedSecret, Voiceprint

    with _session(pg, B) as db:
        people = {p.person_id for p in db.query(Person)}          # no owner filter on purpose
        vectors = {v.person_id for v in db.query(Voiceprint)}
        secret_rows = {s.person_id for s in db.query(SharedSecret)}
    assert seeded["a"] not in people | vectors | secret_rows
    assert seeded["b"] in people and seeded["b"] in vectors


def test_no_owner_scope_sees_nothing(pg, seeded):
    from server.database import Person, Voiceprint

    with _session(pg, None) as db:
        assert db.query(Person).count() == 0
        assert db.query(Voiceprint).count() == 0


def test_scope_does_not_leak_between_transactions_on_one_pooled_connection(pg, seeded):
    from server.database import Person

    for _ in range(3):
        with _session(pg, A) as db:
            assert seeded["a"] in {p.person_id for p in db.query(Person)}
        with _session(pg, B) as db:
            assert seeded["a"] not in {p.person_id for p in db.query(Person)}


def test_writes_into_another_account_are_refused(pg, seeded):
    from sqlalchemy.exc import DBAPIError

    from server.database import Person, Voiceprint

    with _session(pg, B) as db:   # B forges a vector onto A's person
        db.add(Voiceprint(voiceprint_id=f"vp_forged_{uuid.uuid4().hex[:6]}", person_id=seeded["a"],
                          condition="nb8k_real", embedding=_unit(9).tolist(), embedding_dim=192,
                          duration_s=1, snr_db=1, model_version=config.SPEAKER_MODEL_VERSION))
        with pytest.raises(DBAPIError):
            db.commit()
    with _session(pg, B) as db:   # B claims a row for A
        db.add(Person(person_id=f"px_{uuid.uuid4().hex[:6]}", owner_id=A, name="X", relation="Y"))
        with pytest.raises(DBAPIError):
            db.commit()
    with _session(pg, B) as db:   # B edits and deletes A's person: zero rows touched
        assert db.execute(text("UPDATE persons SET name = 'pwned' WHERE person_id = :p"),
                          {"p": seeded["a"]}).rowcount == 0
        assert db.execute(text("DELETE FROM persons WHERE person_id = :p"), {"p": seeded["a"]}).rowcount == 0
        db.commit()


def test_llm_shadow_rows_are_owner_scoped(pg):
    """Migration 0002: the shadow log gets its own policy, not 0001's."""
    from sqlalchemy.exc import DBAPIError

    from server.database import LlmShadowRecord

    rid = f"llm_{uuid.uuid4().hex[:8]}"
    with _session(pg, A) as db:
        db.add(LlmShadowRecord(record_id=rid, owner_id=A, session_id="s", transcript_rev=1,
                               status="ok", record_json="{}"))
        db.commit()
    with _session(pg, B) as db:
        assert db.query(LlmShadowRecord).filter_by(record_id=rid).count() == 0
        db.add(LlmShadowRecord(record_id=f"{rid}_x", owner_id=A, session_id="s", transcript_rev=1,
                               status="ok", record_json="{}"))
        with pytest.raises(DBAPIError):
            db.commit()
    with _session(pg, A) as db:
        assert db.query(LlmShadowRecord).filter_by(record_id=rid).count() == 1


def test_pgvector_round_trips_through_the_store(pg, seeded):
    from server import voiceprint_store

    with _session(pg, A) as db:
        everyone = voiceprint_store.get_candidates(db, A)
        cands = voiceprint_store.get_candidates(db, A, person_id=seeded["a"])
    assert seeded["b"] not in {c["person_id"] for c in everyone}
    assert [c["person_id"] for c in cands] == [seeded["a"]]
    assert np.allclose(cands[0]["centroids"]["wb"], _unit(1), atol=1e-5)


def test_the_app_role_cannot_rewrite_the_evidence_log(pg):
    from sqlalchemy.exc import DBAPIError

    with _session(pg, A) as db:
        db.execute(text("INSERT INTO evidence_roots (tree_size, root_hash) VALUES (999999, 'x')"))
        db.commit()
    with _session(pg, A) as db:
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE evidence_roots SET root_hash = 'y' WHERE tree_size = 999999"))


def test_supabase_api_roles_have_no_access(pg):
    with pg["admin"].connect() as conn:
        roles = {r for (r,) in conn.execute(text(
            "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"))}
        if not roles:
            pytest.skip("not a Supabase database")
        for role in roles:
            granted = conn.execute(text(
                "SELECT count(*) FROM information_schema.role_table_grants "
                "WHERE grantee = :r AND table_schema = :s"), {"r": role, "s": pg["schema"]}).scalar()
            assert granted == 0, f"{role} still has privileges on {pg['schema']}"
