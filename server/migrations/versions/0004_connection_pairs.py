"""One connection row per pair of accounts, and a tighter accept rule.

1. `connections.pair_key`: the two account ids in byte order (`database.pair_key`, matched
   here with COLLATE "C"), unique. Two people requesting each other at the same instant can
   no longer leave two rows. Existing duplicates keep the accepted row, else the oldest.
2. The app role may UPDATE only `status` and `responded_at` (column privileges), and the
   accept policy requires the new status to be 'accepted'. Before this, RLS checked only
   that the updater was the addressee, so at the database level the addressee could also
   have rewritten who the requester was. The app never did; now Postgres refuses it.

Revision ID: 0004_connection_pairs
Revises: 0003_contacts
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "0004_connection_pairs"
down_revision = "0003_contacts"
branch_labels = None
depends_on = None

_KEY = ("LEAST(requester_id COLLATE \"C\", addressee_id COLLATE \"C\") || '|' || "
        "GREATEST(requester_id COLLATE \"C\", addressee_id COLLATE \"C\")")


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

    conn.execute(text("ALTER TABLE connections ADD COLUMN IF NOT EXISTS pair_key VARCHAR"))
    # Keep one row per pair: the accepted one if any, else the oldest.
    conn.execute(text(f"""
        DELETE FROM connections c USING (
            SELECT connection_id, ROW_NUMBER() OVER (
                PARTITION BY {_KEY}
                ORDER BY (status = 'accepted') DESC, created_at ASC NULLS LAST, connection_id) AS n
            FROM connections) ranked
        WHERE c.connection_id = ranked.connection_id AND ranked.n > 1"""))
    conn.execute(text(f"UPDATE connections SET pair_key = {_KEY} WHERE pair_key IS NULL"))
    conn.execute(text("ALTER TABLE connections ALTER COLUMN pair_key SET NOT NULL"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_connections_pair_key ON connections (pair_key)"))

    # Accepting changes the status and when, nothing else.
    conn.execute(text(f"REVOKE UPDATE ON connections FROM {role}"))
    conn.execute(text(f"GRANT UPDATE (status, responded_at) ON connections TO {role}"))
    conn.execute(text("DROP POLICY IF EXISTS connections_answer ON connections"))
    conn.execute(text(f"CREATE POLICY connections_answer ON connections FOR UPDATE TO {role} "
                      f"USING (addressee_id = {me}) WITH CHECK (addressee_id = {me} AND status = 'accepted')"))


def downgrade() -> None:
    conn = op.get_bind()
    role = _initial()._role()
    me = "current_setting('app.owner_id', true)"
    conn.execute(text("DROP POLICY IF EXISTS connections_answer ON connections"))
    conn.execute(text(f"CREATE POLICY connections_answer ON connections FOR UPDATE TO {role} "
                      f"USING (addressee_id = {me}) WITH CHECK (addressee_id = {me})"))
    conn.execute(text(f"REVOKE UPDATE (status, responded_at) ON connections FROM {role}"))
    conn.execute(text(f"GRANT UPDATE ON connections TO {role}"))
    conn.execute(text("DROP INDEX IF EXISTS uq_connections_pair_key"))
    conn.execute(text("ALTER TABLE connections DROP COLUMN IF EXISTS pair_key"))
