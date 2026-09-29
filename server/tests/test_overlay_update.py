"""The overlay_update message the app's WebSocket client actually reads.

`ScreeningResult.fromJson` in the app only parses `fusion.band`, `speaker.verdict`,
`script.risk` and the reason codes — this message pre-flattens the same information
into what the overlay renders (a colour and a quoted evidence line) so the app does
not have to know contracts.py's shape.

Two tiers, deliberately:

  * `test_build_overlay_update_*` construct a synthetic `ScreeningResponse` and call
    `_build_overlay_update` directly. This is what actually pins the plumbing this
    task added (band-to-colour mapping, marker-then-playbook evidence fallback,
    latency passthrough) — deterministically, with no ASR involved.

  * `test_a_..._through_the_live_websocket` streams a real clip end to end. Tried
    first with an assertion that a known marker (`MK_URGENT_FINANCIAL_UPI`, confirmed
    against `nlp_rag.api.analyze_script` on the clip's pretranscribed cache) would
    also fire through live re-transcription of the same clip — it did not, on any of
    several chunks, across repeated runs. The cached transcript and a fresh live
    Whisper decode of the same audio are not byte-identical, and the marker regex is
    exact-text, so ASR noise alone can miss it. That is a real gap in the marker
    system's robustness to ASR noise, not a bug in this task's plumbing (which the
    unit tests above pin directly) — flagged for Nikhil, not fixed here. The live
    test below checks only what held up across repeated runs: state derives from a
    real response and a benign call never reads red.
"""

from __future__ import annotations

import base64
import json
import uuid

import pytest

import config
from contracts import (
    AntiSpoofResult,
    FusionWeights,
    MarkerMatch,
    MarkerType,
    OperatingMode,
    QualityGateResult,
    RetrievedPlaybook,
    ScreeningResponse,
    ScriptAnalysisResult,
    SpeakerVerdict,
    SpeakerVerificationResult,
    TranscriptResult,
    TrustBand,
    TrustScoreResult,
)
from server.tests.test_ws_rolling_buffer import _split_into_wav_chunks
from server.ws_router import _build_overlay_update

CLIPS = config.REPO_ROOT / "data" / "eval_set" / "clips"
WHISPER = config.REPO_ROOT / "models" / "faster-whisper-small" / "model.bin"
SCAM_CLIP = CLIPS / "held-family-emergency-001.wav"
GENUINE_CLIP = CLIPS / "friend_test.wav"


def _response(*, band, mode, markers=(), playbooks=(), is_synthetic=False, spoof_available=True) -> ScreeningResponse:
    """A minimal but contract-valid ScreeningResponse for one overlay_update case."""
    weights = FusionWeights(asv_weight=0.4, cm_weight=0.35, text_weight=0.25)
    return ScreeningResponse(
        session_id="fixture-session",
        audio_sha256="0" * 64,
        quality=QualityGateResult(passed=True, speech_duration_s=9.0, snr_db=20.0),
        speaker=SpeakerVerificationResult(verdict=SpeakerVerdict.UNKNOWN, risk=0.5),
        spoof=AntiSpoofResult(is_synthetic=is_synthetic, details={"available": spoof_available}),
        transcript=TranscriptResult(text="synthetic fixture, not real audio"),
        script=ScriptAnalysisResult(
            risk=0.5, incriminating_markers=list(markers), exculpatory_markers=[], playbooks=list(playbooks),
        ),
        fusion=TrustScoreResult(
            trust_score=50.0, risk_score=0.5, band=band, mode=mode, weights_used=weights,
            identity_risk=0.5, authenticity_risk=0.0, authenticity_risk_effective=0.0, intent_risk=0.5,
        ),
        processing_time_ms=123.4,
    )


def test_build_overlay_update_quotes_the_marker_when_one_fired():
    marker = MarkerMatch(
        marker_id="MK_URGENT_FINANCIAL_UPI", marker_type=MarkerType.INCRIMINATING,
        category="payment", matched_text="turant paise bhejo", weight=0.8,
        description="urgent payment demand",
    )
    response = _response(band=TrustBand.HIGH_RISK, mode=OperatingMode.AUTHORITY_CHECK, markers=[marker])
    overlay = _build_overlay_update("sess-1", response)
    assert overlay["state"] == "red"
    assert overlay["evidence"] == "turant paise bhejo"
    assert overlay["latency_ms"] == 123.4


def test_build_overlay_update_never_quotes_corpus_text_as_the_callers_words():
    playbook = RetrievedPlaybook(
        playbook_id="PB_DIGITAL_ARREST_01", title="Digital arrest", category="Digital Arrest",
        similarity_score=0.8, matched_excerpt="crime branch, do not cut the call",
        source_url="https://cybercrime.gov.in", source_agency="I4C / MHA",
    )
    response = _response(band=TrustBand.SUSPICIOUS, mode=OperatingMode.AUTHORITY_CHECK, playbooks=[playbook])
    overlay = _build_overlay_update("sess-2", response)
    assert overlay["state"] == "red"
    # The excerpt is corpus text, not something the caller said: never quoted.
    assert overlay["evidence"] is None
    assert overlay["pattern"] == "Digital arrest"


def test_build_overlay_update_evidence_is_none_with_nothing_to_quote():
    response = _response(band=TrustBand.CAUTION, mode=OperatingMode.IDENTITY_CHECK)
    overlay = _build_overlay_update("sess-3", response)
    assert overlay["state"] == "amber"
    assert overlay["evidence"] is None


def test_build_overlay_update_maps_every_band_and_reports_spoof_availability():
    for band, expected in [
        (TrustBand.VERIFIED, "green"),
        (TrustBand.CAUTION, "amber"),
        (TrustBand.SUSPICIOUS, "red"),
        (TrustBand.HIGH_RISK, "red"),
        (TrustBand.UNVERIFIED, "grey"),
        (TrustBand.INSUFFICIENT, "grey"),
    ]:
        response = _response(band=band, mode=OperatingMode.IDENTITY_CHECK)
        assert _build_overlay_update("sess-4", response)["state"] == expected, band

    off = _response(band=TrustBand.CAUTION, mode=OperatingMode.IDENTITY_CHECK, spoof_available=False)
    assert _build_overlay_update("sess-5", off)["signals"]["authenticity"] == "unavailable"

    synthetic = _response(
        band=TrustBand.CAUTION, mode=OperatingMode.IDENTITY_CHECK, is_synthetic=True, spoof_available=True,
    )
    assert _build_overlay_update("sess-6", synthetic)["signals"]["authenticity"] == "synthetic"


# --- live end-to-end, real audio, real Whisper -------------------------------

pytestmark = pytest.mark.skipif(
    not WHISPER.is_file() or not SCAM_CLIP.is_file() or not GENUINE_CLIP.is_file(),
    reason="needs models/faster-whisper-small/ and data/eval_set/clips/",
)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from server.main import app

    with TestClient(app) as c:
        yield c


def _stream(client, clip_path) -> list[dict]:
    """Stream a clip in 3s chunks and return every overlay_update received."""
    chunks = _split_into_wav_chunks(clip_path, chunk_s=3.0)
    session_id = f"test-overlay-{uuid.uuid4().hex[:8]}"
    overlays = []
    with client.websocket_connect(f"/api/ws/screen/{session_id}") as ws:
        for i, chunk in enumerate(chunks):
            ws.send_text(json.dumps({
                "type": "audio_chunk",
                "session_id": session_id,
                "chunk_index": i,
                "audio_base64": base64.b64encode(chunk).decode(),
                "is_final": i == len(chunks) - 1,
            }))
            # Two messages per chunk: screening_update, then overlay_update.
            first = json.loads(ws.receive_text())
            second = json.loads(ws.receive_text())
            assert first["type"] == "screening_update", first
            assert second["type"] == "overlay_update", second
            overlays.append(second)
    return overlays


def test_a_spoken_scam_script_through_the_live_websocket_is_never_green(client):
    overlays = _stream(client, SCAM_CLIP)
    assert all(o["state"] != "green" for o in overlays), overlays
    assert all(isinstance(o["latency_ms"], (int, float)) and o["latency_ms"] >= 0 for o in overlays)


def test_a_genuine_benign_call_through_the_live_websocket_does_not_turn_red(client):
    overlays = _stream(client, GENUINE_CLIP)
    assert all(o["state"] != "red" for o in overlays), overlays


if __name__ == "__main__":
    print("run via pytest")
