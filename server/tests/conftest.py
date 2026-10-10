"""No server test touches the real database.

Until 2026-10-10 the live-WebSocket tests wrote their sessions into data/satyacheck.db
(425 sessions had piled up there). Every test now gets a fresh SQLite file: the engine
`init_db` uses at app startup and the session factory every owner-scoped session is
opened from. Tests that want to look inside it use the `isolated_db` fixture.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker

from server.tests.isolated_db import make_engine


@pytest.fixture(autouse=True)
def _no_real_database(tmp_path, monkeypatch):
    from server import database

    engine = make_engine(tmp_path / "autouse.db")
    database.Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, autoflush=False, autocommit=False))
    yield
    engine.dispose()
