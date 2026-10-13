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

# A fresh role name each run: Supabase's pooler keeps server connections per user, and a
# role dropped and recreated under the same name made it hand out connections for the old
# role ("invalid role OID"). Never the production role.
ROLE = f"satyacheck_app_test_{uuid.uuid4().hex[:6]}"
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


def test_profiles_are_readable_by_all_and_writable_by_their_owner(pg):
    """Migration 0003: search needs every username; only the owner changes theirs."""
    from server.database import Profile

    tag = uuid.uuid4().hex[:6]
    for owner in (A, B):
        with _session(pg, owner) as db:
            db.execute(text("DELETE FROM profiles WHERE owner_id = :o"), {"o": owner})
            db.add(Profile(owner_id=owner, username=f"{owner}_{tag}"[:20], display_name=owner))
            db.commit()
    with _session(pg, B) as db:
        assert db.query(Profile).filter_by(owner_id=A).count() == 1
        assert db.execute(text("UPDATE profiles SET display_name = 'pwned' WHERE owner_id = :o"), {"o": A}).rowcount == 0
        assert db.execute(text("DELETE FROM profiles WHERE owner_id = :o"), {"o": A}).rowcount == 0
        db.commit()


def test_connections_are_private_and_only_the_addressee_accepts(pg):
    """Migration 0003: a request is filed only by its requester, as pending, and only its
    addressee can accept it. A third account sees nothing."""
    from sqlalchemy.exc import DBAPIError

    from server.database import Connection, pair_key

    cid = f"c_{uuid.uuid4().hex[:8]}"
    with _session(pg, A) as db:
        db.add(Connection(connection_id=cid, requester_id=A, addressee_id=B, pair_key=pair_key(A, B), status="pending"))
        db.commit()
    with _session(pg, "account-c") as db:
        assert db.query(Connection).filter_by(connection_id=cid).count() == 0
    with _session(pg, A) as db:   # the requester cannot accept their own request
        assert db.execute(text("UPDATE connections SET status = 'accepted' WHERE connection_id = :c"),
                          {"c": cid}).rowcount == 0
        db.commit()
    with _session(pg, B) as db:   # nor file one, already accepted, in A's name (another pair, so
        # only row-level security can be what refuses it, not the one-row-per-pair index)
        db.add(Connection(connection_id=f"{cid}_x", requester_id=A, addressee_id="account-d",
                          pair_key=pair_key(A, "account-d"), status="accepted"))
        with pytest.raises(DBAPIError):
            db.commit()
    with _session(pg, B) as db:
        assert db.execute(text("UPDATE connections SET status = 'accepted' WHERE connection_id = :c"),
                          {"c": cid}).rowcount == 1
        db.commit()


def test_one_row_per_pair_and_accepting_changes_only_the_status(pg):
    """Migration 0004: a pair of accounts has one connection row whoever asked; the addressee
    may set the status to 'accepted' and nothing else (not who asked, not the pair)."""
    from sqlalchemy.exc import DBAPIError, IntegrityError

    from server.database import Connection, pair_key

    a, b = f"pa_{uuid.uuid4().hex[:6]}", f"pb_{uuid.uuid4().hex[:6]}"
    cid = f"c_{uuid.uuid4().hex[:8]}"
    with _session(pg, a) as db:
        db.add(Connection(connection_id=cid, requester_id=a, addressee_id=b, pair_key=pair_key(a, b), status="pending"))
        db.commit()
    with _session(pg, b) as db:   # b asks a at the same instant: the database keeps one row
        db.add(Connection(connection_id=f"{cid}_back", requester_id=b, addressee_id=a, pair_key=pair_key(b, a),
                          status="pending"))
        with pytest.raises(IntegrityError):
            db.commit()
    with _session(pg, b) as db:   # the addressee cannot rewrite who asked
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE connections SET requester_id = 'someone-else' WHERE connection_id = :c"), {"c": cid})
    with _session(pg, b) as db:   # nor set any status but 'accepted'
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE connections SET status = 'blocked' WHERE connection_id = :c"), {"c": cid})
    with _session(pg, b) as db:
        assert db.execute(text("UPDATE connections SET status = 'accepted', responded_at = now() "
                               "WHERE connection_id = :c"), {"c": cid}).rowcount == 1
        db.commit()


def test_migration_0004_keeps_the_accepted_row_of_a_duplicated_pair():
    """The upgrade path the live database takes: from 0003 with two rows for one pair."""
    from alembic import command
    from alembic.config import Config

    from server import database

    schema, role = f"satyacheck_m4_{uuid.uuid4().hex[:8]}", f"satyacheck_app_m4_{uuid.uuid4().hex[:6]}"   # own role: the
    saved = {k: getattr(config, k) for k in ("DATABASE_ADMIN_URL", "DB_SCHEMA", "DB_APP_ROLE", "DB_APP_PASSWORD")}
    config.DATABASE_ADMIN_URL, config.DB_SCHEMA = ADMIN_URL, schema   # module fixture still uses ROLE
    config.DB_APP_ROLE, config.DB_APP_PASSWORD = role, secrets.token_urlsafe(24)
    admin = database.make_engine(ADMIN_URL)
    cfg = Config(str(config.REPO_ROOT / "server" / "migrations" / "alembic.ini"))
    try:
        command.upgrade(cfg, "0003_contacts")
        with admin.begin() as conn:
            conn.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            cols = {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = :s AND table_name = 'connections'"),
                {"s": schema})}
            if "pair_key" in cols:   # 0003 builds from today's models; recreate the 0003 shape
                conn.execute(text("DROP INDEX IF EXISTS uq_connections_pair_key"))
                conn.execute(text("ALTER TABLE connections DROP COLUMN pair_key"))
            conn.execute(text("INSERT INTO connections (connection_id, requester_id, addressee_id, status, created_at) VALUES "
                              "('old', 'u-a', 'u-b', 'pending', now() - interval '2 days'), "
                              "('acc', 'u-b', 'u-a', 'accepted', now() - interval '1 day'), "
                              "('other', 'u-a', 'u-c', 'pending', now())"))
        command.upgrade(cfg, "head")
        with admin.connect() as conn:
            rows = dict(conn.execute(text(f'SELECT connection_id, pair_key FROM "{schema}".connections')).fetchall())
        assert rows == {"acc": "u-a|u-b", "other": "u-a|u-c"}
    finally:
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            conn.execute(text(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "
                              f"THEN REVOKE ALL ON SCHEMA extensions FROM {role}; DROP ROLE {role}; "
                              f"END IF; END $$"))
        admin.dispose()
        for k, v in saved.items():
            setattr(config, k, v)


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


def test_the_admin_console_reads_every_account_but_cannot_write(pg, seeded):
    """database.admin_session: the owner connection, in a transaction Postgres makes
    read-only. It sees both accounts (no RLS scope) and any write is refused."""
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.orm import sessionmaker

    from server.database import Person

    db = sessionmaker(bind=pg["admin"])()
    db.info["admin_read"] = True
    try:
        seen = {p.person_id for p in db.query(Person)}
        assert {seeded["a"], seeded["b"]} <= seen
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE persons SET name = 'changed by admin' WHERE person_id = :p"),
                       {"p": seeded["a"]})
    finally:
        db.rollback()
        db.close()


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
