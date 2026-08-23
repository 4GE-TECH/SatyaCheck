"""Enrollment must reach the identity branch, not just the database.

The failure this pins is silent in the worst way. `/api/enroll` can return 201 with
a row in SQLite and a voiceprint record in the response while `audio_ml` has nothing
on disk — and then `verify_speaker` globs an empty directory, finds no enrolled
person, and returns `unknown`. `unknown` is a legitimate verdict meaning "no
enrolled person is close", so the UI shows *unverified* for someone enrolled thirty
seconds earlier and nothing anywhere reports a problem.

So: assert the `.npz` exists and assert the verdict for that speaker afterwards.
Asserting HTTP 201 passes while the feature is broken.
"""

from __future__ import annotations

import pytest

import config

CLIPS = config.REPO_ROOT / "data" / "eval_set" / "clips"
ECAPA = config.REPO_ROOT / "models" / "ecapa" / "hyperparams.yaml"

pytestmark = pytest.mark.skipif(
    not ECAPA.is_file() or not (CLIPS / "friend.wav").is_file(),
    reason="needs models/ecapa/ and data/eval_set/clips/",
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient with isolated voiceprint and database storage."""
    from fastapi.testclient import TestClient

    from audio_ml import enroll

    monkeypatch.setattr(enroll, "ENROLLMENTS_DIR", tmp_path / "enrollments")
    monkeypatch.setattr(config, "ENROLLMENTS_DIR", tmp_path / "enrollments")
    (tmp_path / "enrollments").mkdir()

    from server.main import app

    with TestClient(app) as c:
        c.enrollments = tmp_path / "enrollments"
        yield c


def _enroll(client, name: str, clip: str):
    with (CLIPS / f"{clip}.wav").open("rb") as fh:
        return client.post(
            "/api/enroll",
            data={"name": name, "relation": "Friend"},
            files={"file": (f"{clip}.wav", fh, "audio/wav")},
        )


def test_the_recorded_clips_can_actually_be_enrolled(client):
    """ENROLL_MIN_SPEECH_S has to be reachable by the audio that exists.

    Every recorded clip tops out at 23.1s of detected speech. With the floor at
    30s, `/api/enroll` rejected all of them — so nobody could enrol through the UI
    at all, and the identity branch had nothing to compare against no matter how
    correct the rest of the pipeline was.
    """
    response = _enroll(client, "Friend", "friend")

    assert response.status_code == 201, (
        f"enrollment rejected: {response.status_code} {response.text[:200]}"
    )


def test_enrollment_writes_the_voiceprint_audio_ml_reads(client):
    """The `.npz` on disk IS the integration point between C's API and A's verifier."""
    response = _enroll(client, "Friend", "friend")
    assert response.status_code == 201

    person_id = response.json()["person_id"]
    assert (client.enrollments / f"{person_id}.npz").is_file(), (
        "the API reported success but audio_ml has no voiceprint on disk — "
        "verify_speaker will return 'unknown' for this person forever"
    )


def test_an_enrolled_person_screens_as_a_match(client):
    """The behavioural round trip: enrol, then screen a different recording.

    This is the assertion that would have caught the demo-day failure. It is also
    the only one here that exercises enrollment and verification together.
    """
    assert _enroll(client, "Friend", "friend").status_code == 201

    with (CLIPS / "friend_test.wav").open("rb") as fh:
        screened = client.post(
            "/api/screen", files={"file": ("friend_test.wav", fh, "audio/wav")}
        )
    assert screened.status_code == 200, screened.text[:300]

    speaker = screened.json()["speaker"]
    assert speaker["verdict"] != "unknown", (
        f"a person enrolled seconds ago screened as 'unknown' "
        f"(cosine {speaker['raw_score']:.4f}) — enrollment never reached the "
        "identity branch"
    )
    assert speaker["verdict"] == "match"
    assert speaker["matched_person_name"] == "Friend"


def test_a_cloned_voice_does_not_screen_as_the_enrolled_person(client):
    """The product's core claim, through the real API."""
    assert _enroll(client, "Friend", "friend").status_code == 201

    with (CLIPS / "cloned_scam.wav").open("rb") as fh:
        screened = client.post(
            "/api/screen", files={"file": ("cloned_scam.wav", fh, "audio/wav")}
        )
    assert screened.status_code == 200

    body = screened.json()
    assert body["speaker"]["verdict"] != "match", (
        "the API verified a synthesised voice as an enrolled contact"
    )
    # And the call as a whole must be flagged, not merely un-verified.
    assert body["fusion"]["band"] in ("suspicious", "high_risk"), (
        f"a cloned-voice extortion script scored "
        f"{body['fusion']['band']} at trust {body['fusion']['trust_score']}"
    )
