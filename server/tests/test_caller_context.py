"""Item 11 / C3: caller context is a separate output, never an input to the risk score.

Before this, `/api/screen` built a `CallerMetadata` from the form and dropped it:
`screen_audio` accepted it and never used it, `ScreeningResponse` had nowhere to put it,
and the report read `script.details["caller_metadata"]`, which nothing wrote — so every
incident report went out with an empty caller block.

CLAUDE.md: "Caller-ID metadata enriches the *explanation*, never the score — a fourth
weight means recalibrating everything." The invariance tests below are that rule.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

import config
from contracts import CallerMetadata, ScreeningResponse, create_mock_fixture
from server.audio_ingest import ingest_audio
from server.orchestrator import _compute_fusion, screen_audio
from server.report_router import _build_report_packet

CLIP = config.REPO_ROOT / "data" / "eval_set" / "clips" / "friend_test.wav"
CTX = CallerMetadata(claimed_number="+919876543210", claimed_name="HDFC Bank",
                     claimed_identity=None, channel_type="telephony")


@pytest.fixture
def mocked_branches(monkeypatch):
    for flag in ("USE_REAL_SPEAKER", "USE_REAL_SPOOF", "USE_REAL_NLP"):
        monkeypatch.setattr(config, flag, False)


def test_the_response_has_an_optional_caller_context():
    assert create_mock_fixture("red").caller_context is None


def test_a_stored_response_from_before_c3_still_loads():
    old = create_mock_fixture("red").model_dump(mode="json")
    old.pop("caller_context", None)
    assert ScreeningResponse.model_validate(old).caller_context is None


def test_telephony_is_a_channel_type():
    assert CallerMetadata(channel_type="telephony").channel_type == "telephony"


def test_fusion_takes_no_caller_input():
    params = inspect.signature(_compute_fusion).parameters
    assert not [p for p in params if "caller" in p or "metadata" in p], list(params)


@pytest.mark.skipif(not CLIP.is_file(), reason="needs data/eval_set/clips/")
def test_screen_audio_carries_the_context_through(mocked_branches):
    result = asyncio.run(screen_audio(ingest_audio(audio_path=str(CLIP)), caller_metadata=CTX))
    assert result.caller_context == CTX


@pytest.mark.skipif(not CLIP.is_file(), reason="needs data/eval_set/clips/")
def test_caller_context_never_moves_the_score(mocked_branches):
    audio = ingest_audio(audio_path=str(CLIP))
    variants = [None, CTX, CallerMetadata(claimed_number="+910000000000", channel_type="upload")]
    fused = [asyncio.run(screen_audio(audio, caller_metadata=c)).fusion for c in variants]
    for f in fused[1:]:
        assert f.risk_score == fused[0].risk_score
        assert f.band == fused[0].band
        assert f.weights_used == fused[0].weights_used


def test_the_report_uses_the_response_caller_context():
    response = create_mock_fixture("red").model_copy(update={"caller_context": CTX})
    packet = _build_report_packet(response, "RPT_TEST")
    assert packet.caller_metadata.claimed_number == "+919876543210"
    assert packet.caller_metadata.claimed_name == "HDFC Bank"


def test_a_report_without_context_gets_an_empty_caller_block():
    packet = _build_report_packet(create_mock_fixture("red"), "RPT_TEST")
    assert packet.caller_metadata.claimed_number is None


@pytest.mark.skipif(not CLIP.is_file(), reason="needs data/eval_set/clips/")
def test_the_screen_endpoint_returns_the_form_metadata(mocked_branches):
    from fastapi.testclient import TestClient

    from server.main import app

    with TestClient(app) as client, CLIP.open("rb") as fh:
        r = client.post("/api/screen", data={"claimed_number": "+911112223334", "channel_type": "upload"},
                        files={"file": ("c.wav", fh, "audio/wav")})
    assert r.status_code == 200, r.text
    assert r.json()["caller_context"]["claimed_number"] == "+911112223334"
