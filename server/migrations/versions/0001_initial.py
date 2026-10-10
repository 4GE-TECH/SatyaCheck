"""Initial Postgres schema: tables, pgvector, the app role, grants and row-level security.

Tables come from server/database.py's models (one definition for SQLite and Postgres).
Then:

  * `config.DB_APP_ROLE` (default satyacheck_app): the role the backend connects as. It
    is not the tables' owner and has no BYPASSRLS, so every query it runs is filtered by
    the policies below. RLS is ENABLED, not FORCED: the owner (the admin connection,
    used for migrations and the cross-account retention sweep) is not filtered.
  * Owned tables: a row is visible and writable only when its owner_id equals the
    transaction's `app.owner_id` (set per transaction by server/database.py).
  * voiceprints and shared_secrets: through their person's ownership.
  * Evidence log: one append-only tree across accounts. The app role may read and
    append, never update or delete.
  * Every table has RLS enabled, and anon/authenticated lose all privileges: Supabase's
    REST API exposes the public schema to those roles, and a table without RLS would be
    readable by anyone holding the project's anon key.

Revision ID: 0001_initial
"""

from __future__ import annotations

import re

from alembic import op
from sqlalchemy import text

import config
from server.database import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

OWNED = ("persons", "consents", "enroll_idempotency", "sessions", "screenings",
         "flagged_voices", "guardian_subscriptions")
THROUGH_PERSON = ("voiceprints", "shared_secrets")
EVIDENCE = ("evidence_leaves", "evidence_roots")
TABLES = OWNED + THROUGH_PERSON + EVIDENCE
_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _role() -> str:
    role = config.DB_APP_ROLE
    if not _IDENT.match(role):
        raise ValueError(f"DB_APP_ROLE {role!r} is not a plain lower-case identifier")
    return role


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    conn = op.get_bind()
    role = _role()
    schema = config.DB_SCHEMA
    owner_check = "owner_id = current_setting('app.owner_id', true)"

    conn.execute(text("CREATE SCHEMA IF NOT EXISTS extensions"))
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions"))

    # Exactly the tables this revision shipped; later revisions add their own.
    Base.metadata.create_all(bind=conn, tables=[Base.metadata.tables[t] for t in TABLES])
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_flagged_voices_embedding_hnsw "
                      "ON flagged_voices USING hnsw (embedding vector_cosine_ops)"))

    password = config.DB_APP_PASSWORD
    login = f"LOGIN PASSWORD {_literal(password)}" if password else "NOLOGIN"
    conn.execute(text(f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            CREATE ROLE {role} {login} NOINHERIT NOBYPASSRLS;
          ELSIF {_literal(password)} <> '' THEN
            ALTER ROLE {role} WITH {login};
          END IF;
        END $$;"""))

    conn.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO {role}'))
    conn.execute(text(f"GRANT USAGE ON SCHEMA extensions TO {role}"))
    conn.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{schema}" TO {role}'))
    conn.execute(text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "{schema}" TO {role}'))
    conn.execute(text(f"REVOKE UPDATE, DELETE ON {', '.join(EVIDENCE)} FROM {role}"))
    conn.execute(text(f"""
        DO $$ BEGIN
          IF to_regclass('alembic_version') IS NOT NULL THEN
            REVOKE ALL ON alembic_version FROM {role};
            ALTER TABLE alembic_version ENABLE ROW LEVEL SECURITY;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON ALL TABLES IN SCHEMA "{schema}" FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON ALL TABLES IN SCHEMA "{schema}" FROM authenticated;
          END IF;
        END $$;"""))

    for table in OWNED:
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(f"CREATE POLICY {table}_owner ON {table} FOR ALL TO {role} "
                          f"USING ({owner_check}) WITH CHECK ({owner_check})"))
    for table in THROUGH_PERSON:
        through = (f"EXISTS (SELECT 1 FROM persons p WHERE p.person_id = {table}.person_id "
                   f"AND p.owner_id = current_setting('app.owner_id', true))")
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(f"CREATE POLICY {table}_owner ON {table} FOR ALL TO {role} "
                          f"USING ({through}) WITH CHECK ({through})"))
    for table in EVIDENCE:
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(f"CREATE POLICY {table}_read ON {table} FOR SELECT TO {role} USING (true)"))
        conn.execute(text(f"CREATE POLICY {table}_append ON {table} FOR INSERT TO {role} WITH CHECK (true)"))


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=[Base.metadata.tables[t] for t in TABLES])
