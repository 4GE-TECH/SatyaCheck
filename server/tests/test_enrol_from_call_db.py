"""`scripts/enrol_from_call.py` stores into the voiceprint database, like /api/enroll.

It used to write a `.npz` plus a person row with no voiceprint rows: visible in the app,
matched only through the legacy file. Now person and vectors go in one transaction.
"""

from __future__ import annotations

import wave

import numpy as np
import pytest

import config
from server.tests.isolated_db import isolated_db  # noqa: F401  (fixture)


def _unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(192).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def call_session(tmp_path, monkeypatch):
    from audio_ml import enroll

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(enroll, "ENROLLMENTS_DIR", tmp_path / "enrollments")
    monkeypatch.setattr(config, "ENROLLMENTS_DIR", tmp_path / "enrollments")
    session = tmp_path / "sessions" / "call-1"
    session.mkdir(parents=True)
    for i in range(4):
        with wave.open(str(session / f"chunk_{i:04d}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x01" * 16000)
    return tmp_path


def test_enrol_stores_person_and_vectors_and_no_file(isolated_db, call_session, monkeypatch):
    import audio_ml.api
    from scripts import enrol_from_call
    from server.database import Person, Voiceprint

    seen = {}

    def compute(wav_paths, nb8k_real_paths=None):
        seen["paths"] = wav_paths
        return {"wb": _unit(1), "nb8k_sim": _unit(2), "n_samples": 64000}

    monkeypatch.setattr(audio_ml.api, "compute_voiceprint", compute)
    assert enrol_from_call.enrol("call-1", "Papa (call)", "Father") == 0

    with isolated_db() as db:
        people = db.query(Person).all()
        conditions = sorted(v.condition for v in db.query(Voiceprint))
    assert [(p.name, p.relation) for p in people] == [("Papa (call)", "Father")]
    assert conditions == ["nb8k_sim", "wb"]
    assert len(seen["paths"]) == 2, "every other overlapping chunk"
    assert not (call_session / "enrollments").exists() or not any((call_session / "enrollments").iterdir())


def test_enrol_with_no_voiceprint_stores_nothing(isolated_db, call_session, monkeypatch, capsys):
    import audio_ml.api
    from scripts import enrol_from_call
    from server.database import Person

    monkeypatch.setattr(audio_ml.api, "compute_voiceprint", lambda wav_paths, nb8k_real_paths=None: None)
    assert enrol_from_call.enrol("call-1", "Papa (call)", "Father") == 1
    with isolated_db() as db:
        assert db.query(Person).count() == 0
    assert "voiceprint" in capsys.readouterr().err.lower()
