"""Upgrade plan, Phase 0 steps 1–2: safe responses and atomic database enrollment.

What was wrong (verified in code before this change):

  * `/api/enroll` read `result.get("wb")` from `enroll_person`, which returns metadata
    only, so it stored **zero** voiceprint rows and still answered 201.
  * every persons response carried raw 192-d embeddings and challenge answer hashes —
    biometric data and guessable secrets handed to any caller.

Now enrollment computes vectors in memory and writes the person, the vectors and the
secrets in one transaction; responses are summaries with no vectors and no hashes.

Ingestion and the model are stubbed: these tests pin the server's data flow and run
without `models/`.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

import config
from contracts import QualityGateResult
from server.tests.isolated_db import isolated_db  # noqa: F401  (fixture)


def _unit(seed: int) -> np.ndarray:
    v = np.random.default_rng(seed).standard_normal(192).astype(np.float32)
    return v / np.linalg.norm(v)


class _FakeIngested:
    def __init__(self, speech_s: float, passed: bool = True):
        self.audio_sha256 = f"sha-{speech_s}"
        self.normalized_wav_path = "fake.wav"
        self.quality = QualityGateResult(passed=passed, speech_duration_s=speech_s, snr_db=21.5,
                                         reason=None if passed else "too noisy")


@pytest.fixture
def ml(monkeypatch, tmp_path):
    """Stub ingestion and voiceprint computation. `ml.vectors` is what the next
    computation returns; `ml.calls` counts computations; `ml.speech_s` the speech found."""
    import audio_ml.api
    from audio_ml import enroll
    from server import enroll_router

    state = type("ML", (), {})()
    state.calls = 0
    state.speech_s = 20.0
    state.vectors = {"wb": _unit(1), "nb8k_sim": _unit(2), "n_samples": 320000}

    def compute(wav_paths, nb8k_real_paths=None):
        state.calls += 1
        return None if state.vectors is None else dict(state.vectors)

    monkeypatch.setattr(audio_ml.api, "compute_voiceprint", compute, raising=False)
    monkeypatch.setattr(enroll_router, "ingest_audio", lambda audio_bytes: _FakeIngested(state.speech_s))
    monkeypatch.setattr(enroll_router, "discard", lambda ingested: None)
    monkeypatch.setattr(enroll, "ENROLLMENTS_DIR", tmp_path / "enrollments")
    monkeypatch.setattr(config, "ENROLLMENTS_DIR", tmp_path / "enrollments")
    state.enrollments = tmp_path / "enrollments"
    return state


@pytest.fixture
def client(isolated_db, ml):
    from server.main import app

    c = TestClient(app)   # no lifespan: the isolated DB already has the schema
    c.db = isolated_db
    return c


def _enroll(client, headers=None, **form):
    data = {"name": "Papa", "relation": "Father", **form}
    return client.post("/api/enroll", data=data, headers=headers or {},
                       files={"file": ("a.wav", b"RIFF-not-really", "audio/wav")})


def _rows(client):
    from server.database import Voiceprint

    with client.db() as db:
        return [(v.person_id, v.condition, v.model_version, v.get_embedding())
                for v in db.query(Voiceprint).order_by(Voiceprint.condition)]


def _no_biometrics(payload) -> None:
    text = json.dumps(payload)
    assert '"embedding"' not in text, "a response carried a raw voice embedding"
    assert '"answer_hash"' not in text, "a response carried a challenge answer hash"
    assert '"embedding_blob"' not in text


# --- step 2: enrollment persists ---------------------------------------------------------

def test_enrollment_stores_two_voiceprint_rows_and_no_file(client, ml):
    r = _enroll(client)
    assert r.status_code == 201, r.text
    body = r.json()
    _no_biometrics(body)

    rows = _rows(client)
    assert [(c, mv) for _, c, mv, _ in rows] == [
        ("nb8k_sim", config.SPEAKER_MODEL_VERSION), ("wb", config.SPEAKER_MODEL_VERSION)]
    assert all(pid == body["person_id"] for pid, *_ in rows)
    assert np.allclose(rows[1][3], ml.vectors["wb"], atol=1e-6)

    assert sorted(v["condition"] for v in body["voiceprints"]) == ["nb8k_sim", "wb"]
    for v in body["voiceprints"]:
        assert v["model_version"] == config.SPEAKER_MODEL_VERSION
        assert v["duration_s"] == 20.0 and v["snr_db"] == 21.5
        assert v["voiceprint_id"] and v["created_at"]
    assert not ml.enrollments.exists() or not any(ml.enrollments.iterdir()), "no new .npz may be written"


def test_re_enrollment_replaces_vectors_instead_of_appending(client, ml):
    person_id = _enroll(client).json()["person_id"]
    ml.vectors = {"wb": _unit(11), "nb8k_sim": _unit(12), "n_samples": 1}
    r = _enroll(client, person_id=person_id, name="Papa ji")
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "Papa ji"

    rows = _rows(client)
    assert len(rows) == 2, f"re-enrollment appended: {[(c, mv) for _, c, mv, _ in rows]}"
    assert np.allclose(rows[1][3], _unit(11), atol=1e-6)


def test_no_voiceprint_is_422_with_a_reason_and_stores_nothing(client, ml, caplog):
    ml.vectors = None
    r = _enroll(client)
    assert r.status_code == 422
    assert "voiceprint" in r.json()["detail"].lower()
    assert client.get("/api/persons").json() == []
    assert _rows(client) == []
    assert any("compute_voiceprint" in rec.getMessage() for rec in caplog.records), "degrade must be logged"


def test_too_little_speech_is_422(client, ml):
    ml.speech_s = 5.0
    r = _enroll(client)
    assert r.status_code == 422 and "speech" in r.json()["detail"].lower()
    assert ml.calls == 0
    assert client.get("/api/persons").json() == []


def test_a_failure_while_writing_rolls_back_the_person_too(client, ml, monkeypatch):
    from server import voiceprint_store

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(voiceprint_store, "save_voiceprints", boom)
    r = _enroll(client)
    assert r.status_code == 500
    assert client.get("/api/persons").json() == [], "a person without vectors was left behind"


def test_vectors_are_validated_before_storage(client, ml):
    ml.vectors = {"wb": np.full(192, np.nan, dtype=np.float32), "nb8k_sim": _unit(2), "n_samples": 1}
    r = _enroll(client)
    assert r.status_code == 201
    assert [c for _, c, _, _ in _rows(client)] == ["nb8k_sim"], "a non-finite vector was stored"


def test_unknown_person_id_is_404(client, ml):
    assert _enroll(client, person_id="person_missing").status_code == 404
    assert ml.calls == 0


# --- idempotency ----------------------------------------------------------------------------

def test_an_idempotency_key_makes_a_retry_return_the_same_person(client, ml):
    first = _enroll(client, headers={"Idempotency-Key": "k-123"})
    again = _enroll(client, headers={"Idempotency-Key": "k-123"})
    assert first.status_code == again.status_code == 201
    assert first.json()["person_id"] == again.json()["person_id"]
    assert len(client.get("/api/persons").json()) == 1
    assert ml.calls == 1, "the retry recomputed the voiceprint"


def test_reusing_an_idempotency_key_for_a_different_request_is_409(client, ml):
    assert _enroll(client, headers={"Idempotency-Key": "k-9"}).status_code == 201
    r = _enroll(client, headers={"Idempotency-Key": "k-9"}, name="Someone else")
    assert r.status_code == 409


# --- step 1: no biometrics in any persons response ------------------------------------------

def test_persons_responses_carry_no_vectors_and_no_answer_hashes(client, ml):
    secrets = json.dumps([{"question": "First pet?", "answer": "Moti", "category": "pet"}])
    person_id = _enroll(client, shared_secrets=secrets).json()["person_id"]

    listing = client.get("/api/persons").json()
    single = client.get(f"/api/persons/{person_id}").json()
    for payload in (listing, single):
        _no_biometrics(payload)
    assert single["shared_secrets"] == [
        {"secret_id": single["shared_secrets"][0]["secret_id"], "question": "First pet?", "category": "pet"}]
    assert len(single["voiceprints"]) == 2

    created = client.post("/api/persons", params={"name": "Ma", "relation": "Mother"})
    assert created.status_code == 201
    _no_biometrics(created.json())


def test_the_challenge_lookup_still_sees_the_answer_hash(client, ml):
    """Hiding hashes from HTTP must not break the in-process challenge check."""
    from server.database import current_owner_var, get_person_by_id

    secrets = json.dumps([{"question": "First pet?", "answer": "Moti"}])
    person_id = _enroll(client, shared_secrets=secrets).json()["person_id"]
    assert get_person_by_id(person_id) is None, "no owner scope: nobody"
    token = current_owner_var.set(config.DEV_OWNER_ID)
    try:
        person = get_person_by_id(person_id)
        assert person is not None and person.shared_secrets[0].answer_hash
    finally:
        current_owner_var.reset(token)
    token = current_owner_var.set("owner-b")
    try:
        assert get_person_by_id(person_id) is None, "another account cannot read the secret"
    finally:
        current_owner_var.reset(token)
