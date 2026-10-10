"""LLM shadow log (upgrade plan, Phase 4): the table, its grants and row-level security.

Revision ID: 0002_llm_shadow
Revises: 0001_initial
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

from server.database import Base

revision = "0002_llm_shadow"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _initial():
    """Revision 0001 (a module name that starts with a digit cannot be imported normally),
    for its validated app-role name."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("_m0001", Path(__file__).with_name("0001_initial.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upgrade() -> None:
    conn = op.get_bind()
    role = _initial()._role()
    Base.metadata.tables["llm_shadow"].create(bind=conn, checkfirst=True)
    conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON llm_shadow TO {role}"))
    conn.execute(text("ALTER TABLE llm_shadow ENABLE ROW LEVEL SECURITY"))
    check = "owner_id = current_setting('app.owner_id', true)"
    conn.execute(text(f"CREATE POLICY llm_shadow_owner ON llm_shadow FOR ALL TO {role} "
                      f"USING ({check}) WITH CHECK ({check})"))
    conn.execute(text("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON llm_shadow FROM anon; END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON llm_shadow FROM authenticated; END IF;
        END $$;"""))


def downgrade() -> None:
    Base.metadata.tables["llm_shadow"].drop(bind=op.get_bind(), checkfirst=True)
