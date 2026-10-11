"""Usernames and connections for app-to-app calls (server/contacts.py).

Row-level security, unlike the owned tables:
  * profiles: readable by every account (searching usernames is the point), and an
    account may insert or change only its own row;
  * connections: visible only to the two accounts in it, and either may delete it
    (decline, cancel, disconnect). Only the requester creates it, as pending; only the
    addressee changes it (accept).

Revision ID: 0003_contacts
Revises: 0002_llm_shadow
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

from server.database import Base

revision = "0003_contacts"
down_revision = "0002_llm_shadow"
branch_labels = None
depends_on = None

TABLES = ("profiles", "connections")


def _initial():
    """Revision 0001, for its validated app-role name (see 0002_llm_shadow)."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("_m0001", Path(__file__).with_name("0001_initial.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade() -> None:
    conn = op.get_bind()
    role = _initial()._role()
    me = "current_setting('app.owner_id', true)"
    for table in TABLES:
        Base.metadata.tables[table].create(bind=conn, checkfirst=True)
        conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {role}"))
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))

    conn.execute(text(f"CREATE POLICY profiles_read ON profiles FOR SELECT TO {role} USING (true)"))
    conn.execute(text(f"CREATE POLICY profiles_insert ON profiles FOR INSERT TO {role} WITH CHECK (owner_id = {me})"))
    conn.execute(text(f"CREATE POLICY profiles_update ON profiles FOR UPDATE TO {role} "
                      f"USING (owner_id = {me}) WITH CHECK (owner_id = {me})"))
    conn.execute(text(f"CREATE POLICY profiles_delete ON profiles FOR DELETE TO {role} USING (owner_id = {me})"))

    # A request is created only by its requester, as pending; only its addressee can change
    # it (accept). So nobody can accept their own request, or file one in another's name.
    party = f"(requester_id = {me} OR addressee_id = {me})"
    conn.execute(text(f"CREATE POLICY connections_read ON connections FOR SELECT TO {role} USING {party}"))
    conn.execute(text(f"CREATE POLICY connections_request ON connections FOR INSERT TO {role} "
                      f"WITH CHECK (requester_id = {me} AND status = 'pending')"))
    conn.execute(text(f"CREATE POLICY connections_answer ON connections FOR UPDATE TO {role} "
                      f"USING (addressee_id = {me}) WITH CHECK (addressee_id = {me})"))
    conn.execute(text(f"CREATE POLICY connections_remove ON connections FOR DELETE TO {role} USING {party}"))

    conn.execute(text("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON profiles, connections FROM anon; END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON profiles, connections FROM authenticated; END IF;
        END $$;"""))


def downgrade() -> None:
    for table in reversed(TABLES):
        Base.metadata.tables[table].drop(bind=op.get_bind(), checkfirst=True)
