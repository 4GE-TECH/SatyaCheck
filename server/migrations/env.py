"""Alembic environment: migrates config.DB_SCHEMA through config.DATABASE_ADMIN_URL."""

from __future__ import annotations

from alembic import context
from sqlalchemy import text

import config
from server.database import Base, make_engine

target_metadata = Base.metadata


def run_migrations_online() -> None:
    if not config.DATABASE_ADMIN_URL:
        raise SystemExit("DATABASE_ADMIN_URL is not set (environment or .env)")
    engine = make_engine(config.DATABASE_ADMIN_URL)
    schema = config.DB_SCHEMA
    with engine.connect() as connection:
        if schema != "public":
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}", public, extensions'))
        connection.commit()
        # The models carry no schema, so pin them to this one. Without it create_all's
        # existence check counts any table *visible* on the search path: with the real
        # tables in public, a migration into another schema skipped creating its own and
        # its unqualified policy statements then landed on public's (caught only because
        # the duplicate policy aborted the transaction).
        connection = connection.execution_options(schema_translate_map={None: schema})
        context.configure(connection=connection, target_metadata=target_metadata,
                          version_table_schema=schema)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline (SQL script) mode is not supported; run against a database")
run_migrations_online()
