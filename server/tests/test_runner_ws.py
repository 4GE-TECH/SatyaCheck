"""The WebSocket route on the runner path, with fake models: protocol, retention, cleanup.

`config.USE_PIPELINE_RUNNER` switches `/api/ws/screen/{id}` from the per-chunk
`screen_audio` loop to `SessionRunner`. Decoding is real (acquisition.app_ws; ffmpeg for non-16 kHz chunks);
speaker, anti-spoof and the transcriber are fakes, so this pins what the route does
with frames and files — not what the models say. Real models: test_runner_real_ws.py.
"""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path

import pytest

import config
from contracts import (
    AntiSpoofResult,
    ScriptAnalysisResult,
    SpeakerVerificationResult,
    TranscriptResult,
    create_mock_fixture,
)
from server.tests.test_ws_rolling_buffer import _split_into_wav_chunks

CLIP = config.REPO_ROOT / "data" / "eval_set" / "clips" / "friend_test.wav"  # 10.36 s

pytestmark = pytest.mark.skipif(not CLIP.is_file(), reason="needs data/eval_set/clips/")


class _Echo:
    def push(self, chunk, sample_rate=16000):
        return TranscriptResult(text="hello there", detected_language="en", confidence=0.9)

    def flush(self):
        return TranscriptResult(text="hello there, final", detected_language="en", confidence=0.9)


@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import server.orchestrator as orch
    import server.pipeline.transcript_worker as tw
    import server.ws_router
    from server.main import app

    monkeypatch.setattr(config, "USE_PIPELINE_RUNNER", True)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "USE_REAL_SPEAKER", True)
    monkeypatch.setattr(config, "USE_REAL_SPOOF", True)
    monkeypatch.setattr(orch, "_real_speaker_branch", lambda p: SpeakerVerificationResult.neutral())
    monkeypatch.setattr(orch, "_real_spoof_branch",
                        lambda p: AntiSpoofResult(risk=0.0, details={"available": True}))
    monkeypatch.setattr(tw, "_default_transcriber", _Echo)
    monkeypatch.setattr(tw, "_default_analyze",
                        lambda t: ScriptAnalysisResult(risk=0.0, details={"available": True}))

    async def old_path_must_not_run(*a, **kw):
        raise AssertionError("the per-chunk screen_audio path ran with the runner on")

    monkeypatch.setattr(server.ws_router, "screen_audio", old_path_must_not_run)
    with TestClient(app) as c:
        yield c


def _stream(client, chunk_s=3.0) -> tuple[str, list[dict]]:
    return _stream_file(client, CLIP, chunk_s)


def _stream_file(client, path, chunk_s=3.0) -> tuple[str, list[dict]]:
    from starlette.websockets import WebSocketDisconnect

    chunks = _split_into_wav_chunks(path, chunk_s=chunk_s)
    session_id = f"test-runner-ws-{uuid.uuid4().hex[:8]}"
    messages = []
    with client.websocket_connect(f"/api/ws/screen/{session_id}") as ws:
        for i, chunk in enumerate(chunks):
            ws.send_text(json.dumps({
                "type": "audio_chunk", "session_id": session_id, "chunk_index": i,
                "audio_base64": base64.b64encode(chunk).decode(),
                "is_final": i == len(chunks) - 1,
            }))
        try:
            while True:
                messages.append(json.loads(ws.receive_text()))
        except WebSocketDisconnect:
            pass
    return session_id, messages


def test_one_message_pair_per_window_and_the_session_ends_final(client):
    from server.database import ScreeningResult, ScreeningSession, SessionLocal

    session_id, messages = _stream(client)
    # 10.36 s: windows ending at 2, 4, 6, 8, 10 s, then the 10.36 s tail.
    assert [m["type"] for m in messages] == ["screening_update", "overlay_update"] * 6
    updates = [m for m in messages if m["type"] == "screening_update"]
    assert [u["chunk_index"] for u in updates] == [0, 1, 2, 3, 4, 5]
    assert all(u["session_id"] == session_id and u["response"]["session_id"] == session_id
               for u in updates)
    assert updates[-1]["response"]["transcript"]["text"] == "hello there, final"

    with SessionLocal() as db:
        rows = (db.query(ScreeningResult).filter_by(session_id=session_id)
                .order_by(ScreeningResult.id).all())
        session = db.get(ScreeningSession, session_id)
        assert [r.is_final for r in rows] == [False] * 5 + [True]
        assert session.status == "complete" and session.channel_type == "app_ws"


def test_retention_on_keeps_every_chunk(client):
    session_id, _ = _stream(client)
    kept = sorted(p.name for p in (config.DATA_DIR / "sessions" / session_id).iterdir())
    assert kept == [f"chunk_{i:04d}.wav" for i in range(4)]


def test_retention_off_writes_no_session_audio(client, monkeypatch):
    monkeypatch.setattr(config, "RETAIN_SESSION_AUDIO", False)
    session_id, messages = _stream(client)
    assert messages, "nothing was screened"
    assert not (config.DATA_DIR / "sessions" / session_id).exists()


def test_cleanup_on_leaves_no_temp_wavs_but_keeps_the_retained_copies(client, monkeypatch):
    # Chunks are decoded by acquisition.app_ws (item 2), not ingest_audio: the router
    # writes no per-chunk temp WAVs, only the runner's one temp WAV per window.
    import glob
    import tempfile

    import server.audio_ingest as ingest
    import server.pipeline.runner as runner_mod
    import server.ws_router

    monkeypatch.setattr(config, "CLEANUP_TEMP_AUDIO", True)
    written: list[Path] = []

    def recording(real):
        def wrapper(*a, **kw):
            result = real(*a, **kw)
            if result.normalized_wav_path:
                written.append(Path(result.normalized_wav_path))
            return result
        return wrapper

    def per_chunk_ingest_must_not_run(*a, **kw):
        raise AssertionError("the runner path decoded a chunk with ingest_audio")

    monkeypatch.setattr(server.ws_router, "ingest_audio", per_chunk_ingest_must_not_run)
    monkeypatch.setattr(runner_mod, "ingest_pcm", recording(ingest.ingest_pcm))
    before = set(glob.glob(str(Path(tempfile.gettempdir()) / "satyacheck_acq_*")))
    session_id, _ = _stream(client)
    assert len(written) == 6, "one temp WAV per window"
    assert not [p for p in written if p.exists()], "temp WAVs left behind"
    assert set(glob.glob(str(Path(tempfile.gettempdir()) / "satyacheck_acq_*"))) <= before
    assert (config.DATA_DIR / "sessions" / session_id / "chunk_0000.wav").is_file()


def test_44k1_stereo_chunks_screen_like_16k_mono(client, tmp_path):
    """The app may record at any rate: acquisition resamples, and the windows match."""
    import subprocess
    import wave

    hi = tmp_path / "friend_44k1_stereo.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(CLIP), "-ar", "44100",
                    "-ac", "2", "-acodec", "pcm_s16le", str(hi)], check=True, timeout=60)
    session_id, messages = _stream_file(client, hi)
    updates = [m for m in messages if m["type"] == "screening_update"]
    assert [u["chunk_index"] for u in updates] == [0, 1, 2, 3, 4, 5]
    kept = sorted((config.DATA_DIR / "sessions" / session_id).iterdir())
    assert len(kept) == 4
    with wave.open(str(kept[0])) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        assert abs(w.getnframes() - 3 * 16000) <= 2


def test_flag_off_keeps_the_per_chunk_path(client, monkeypatch):
    import server.ws_router

    monkeypatch.setattr(config, "USE_PIPELINE_RUNNER", False)
    calls = []

    async def stub_screen(audio, caller_metadata=None, enrolled_embeddings=None):
        calls.append(audio.total_duration_s)
        return create_mock_fixture("unverified")

    monkeypatch.setattr(server.ws_router, "screen_audio", stub_screen)
    chunks = _split_into_wav_chunks(CLIP, chunk_s=3.0)
    session_id = f"test-runner-off-{uuid.uuid4().hex[:8]}"
    with client.websocket_connect(f"/api/ws/screen/{session_id}") as ws:
        for i, chunk in enumerate(chunks):
            ws.send_text(json.dumps({
                "type": "audio_chunk", "session_id": session_id, "chunk_index": i,
                "audio_base64": base64.b64encode(chunk).decode(),
                "is_final": i == len(chunks) - 1,
            }))
            assert json.loads(ws.receive_text())["type"] == "screening_update"
            assert json.loads(ws.receive_text())["type"] == "overlay_update"
    assert len(calls) == len(chunks), "one screen_audio per chunk, as before"


@pytest.mark.parametrize("bad", [r"..\..\evil", "../evil", "..", r"a\b", "x/../../y", ""])
def test_retention_refuses_a_session_id_that_is_not_a_plain_folder_name(bad, tmp_path, monkeypatch):
    import server.ws_router as wsr

    data = tmp_path / "a" / "b" / "data"
    data.mkdir(parents=True)
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "RETAIN_SESSION_AUDIO", True)
    wsr._retain_pcm(bad, b"\x00\x01" * 160, 0)
    written = [p for p in tmp_path.rglob("chunk_*.wav")]
    assert written == [], f"retention for {bad!r} wrote {written}"
    # A normal id is still retained, under data/sessions/<id>.
    wsr._retain_pcm("session_ok-1", b"\x00\x01" * 160, 0)
    assert (data / "sessions" / "session_ok-1" / "chunk_0000.wav").is_file()
