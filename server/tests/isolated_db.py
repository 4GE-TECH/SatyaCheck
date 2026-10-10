"""A throwaway SQLite database for server tests.

The older enrollment tests run against the real `data/satyacheck.db` and delete what they
added afterwards; one crashed run leaves rows behind. Tests that only need the schema
use this instead: a fresh file per test, wired into `database.SessionLocal`, which every owner-scoped
session (routers included) is opened from.

Import the fixture into a test module: `from server.tests.isolated_db import isolated_db`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def make_engine(path):
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """A sessionmaker bound to a fresh database with the current schema. Routers reach it
    through `database.owner_session`, which reads `database.SessionLocal` at call time."""
    from server import database

    engine = make_engine(tmp_path / "test.db")
    database.Base.metadata.create_all(engine)
    database.migrate(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    try:
        yield factory
    finally:
        engine.dispose()
