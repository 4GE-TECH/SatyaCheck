"""Item 15: no audio at rest unless retention is explicitly on.

Two places leave call audio on disk today:

  * every `ingest_audio` writes a normalised 16 kHz WAV to the OS temp directory and
    never deletes it — two per WebSocket chunk (the chunk, then the trailing window);
  * `ws_router` copies each chunk to `data/sessions/<id>/chunk_NNNN.wav`, which is what
    `scripts/enrol_from_call.py` enrols from.

`CLEANUP_TEMP_AUDIO` deletes the first, `RETAIN_SESSION_AUDIO` gates the second. Since
item 15b the defaults are private (cleanup on, retention off); the demo machine opts
back into retention, because its channel-matched enrollment reads the retained chunks.

Branch models are stubbed: what is under test is which files exist afterwards, not
the verdict. Ingestion is real (ffmpeg), because that is where the temp files come from.
"""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path

import pytest

import config
from contracts import create_mock_fixture

CLIP = config.REPO_ROOT / "data" / "eval_set" / "clips" / "friend_test.wav"

pytestmark = pytest.mark.skipif(not CLIP.is_file(), reason="needs data/eval_set/clips/")


@pytest.fixture
def temp_wavs(monkeypatch):
    """Record every normalised WAV that ingestion writes, through every router."""
    import server.audio_ingest as ingest
    import server.enroll_router
    import server.screen_router
    import server.ws_router

    written: list[Path] = []
    real = ingest.ingest_audio

    def recording(*args, **kwargs):
        result = real(*args, **kwargs)
        if result.normalized_wav_path:
            written.append(Path(result.normalized_wav_path))
        return result

    for module in (server.screen_router, server.ws_router, server.enroll_router):
        monkeypatch.setattr(module, "ingest_audio", recording)
    return written


@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import server.screen_router
    import server.ws_router
    from server.main import app

    async def stub_screen(audio, caller_metadata=None, enrolled_embeddings=None):
        return create_mock_fixture("unverified")

    monkeypatch.setattr(server.screen_router, "screen_audio", stub_screen)
    monkeypatch.setattr(server.ws_router, "screen_audio", stub_screen)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    with TestClient(app) as c:
        yield c


def _screen(client):
    with CLIP.open("rb") as fh:
        r = client.post("/api/screen", files={"file": ("c.wav", fh, "audio/wav")})
    assert r.status_code == 200, r.text


def _stream_one_chunk(client, session_id=None, url_id=None) -> str:
    session_id = session_id or f"test-retention-{uuid.uuid4().hex[:8]}"
    with client.websocket_connect(f"/api/ws/screen/{url_id or session_id}") as ws:
        ws.send_text(json.dumps({
            "type": "audio_chunk",
            "session_id": session_id,
            "chunk_index": 0,
            "audio_base64": base64.b64encode(CLIP.read_bytes()).decode(),
            "is_final": True,
        }))
        assert json.loads(ws.receive_text())["type"] == "screening_update"
        assert json.loads(ws.receive_text())["type"] == "overlay_update"
    return session_id


# --- defaults are today's behaviour -------------------------------------------

def test_defaults_keep_no_audio():
    assert config.RETAIN_SESSION_AUDIO is False
    assert config.CLEANUP_TEMP_AUDIO is True


def test_the_runbook_opts_back_into_retention():
    runbook = (config.REPO_ROOT / "DEMO_RUNBOOK.md").read_text(encoding="utf-8")
    assert "RETAIN_SESSION_AUDIO=true" in runbook


def test_retention_on_keeps_the_session_chunks(client, monkeypatch):
    monkeypatch.setattr(config, "RETAIN_SESSION_AUDIO", True)
    session_id = _stream_one_chunk(client)
    assert (config.DATA_DIR / "sessions" / session_id / "chunk_0000.wav").is_file()


# --- retention off -------------------------------------------------------------

def test_retention_off_writes_no_session_audio(client, monkeypatch):
    monkeypatch.setattr(config, "RETAIN_SESSION_AUDIO", False)
    session_id = _stream_one_chunk(client)
    assert not (config.DATA_DIR / "sessions" / session_id).exists()


# --- temp cleanup ---------------------------------------------------------------

def test_cleanup_off_leaves_temp_wavs(client, temp_wavs, monkeypatch):
    monkeypatch.setattr(config, "CLEANUP_TEMP_AUDIO", False)
    _screen(client)
    assert temp_wavs and all(p.exists() for p in temp_wavs)
    for p in temp_wavs:
        p.unlink(missing_ok=True)


def test_cleanup_on_removes_the_screen_temp_wav(client, temp_wavs, monkeypatch):
    monkeypatch.setattr(config, "CLEANUP_TEMP_AUDIO", True)
    _screen(client)
    assert temp_wavs, "ingestion wrote nothing — the test is not observing anything"
    assert not [p for p in temp_wavs if p.exists()]


def test_cleanup_on_removes_both_ws_temp_wavs(client, temp_wavs, monkeypatch):
    monkeypatch.setattr(config, "CLEANUP_TEMP_AUDIO", True)
    _stream_one_chunk(client)
    assert len(temp_wavs) == 2, "chunk + trailing window"
    assert not [p for p in temp_wavs if p.exists()]


def test_cleanup_does_not_remove_the_retained_copy(client, temp_wavs, monkeypatch):
    monkeypatch.setattr(config, "CLEANUP_TEMP_AUDIO", True)
    monkeypatch.setattr(config, "RETAIN_SESSION_AUDIO", True)
    session_id = _stream_one_chunk(client)
    assert (config.DATA_DIR / "sessions" / session_id / "chunk_0000.wav").is_file()


# --- the helper itself ------------------------------------------------------------

def test_discard_never_touches_a_caller_supplied_input(tmp_path, monkeypatch):
    from server.audio_ingest import discard, ingest_audio

    monkeypatch.setattr(config, "CLEANUP_TEMP_AUDIO", True)
    source = tmp_path / "input.wav"
    source.write_bytes(CLIP.read_bytes())
    ingested = ingest_audio(audio_path=str(source))
    discard(ingested)
    assert source.is_file()
    assert not Path(ingested.normalized_wav_path).exists()


def test_discard_tolerates_missing_and_absent_paths(monkeypatch):
    from server.audio_ingest import IngestedAudio, discard
    from contracts import QualityGateResult

    monkeypatch.setattr(config, "CLEANUP_TEMP_AUDIO", True)
    for path in (None, "/nonexistent/already-gone.wav"):
        discard(IngestedAudio("", 16000, 0.0, [], [], QualityGateResult.insufficient(),
                              normalized_wav_path=path))


def _failing_ingest(kind: str, monkeypatch):
    """Run one ingestion that fails at `kind` (ffmpeg, waveform decode, or later)."""
    import server.audio_ingest as ingest

    if kind == "ffmpeg":
        return ingest.ingest_audio(audio_bytes=b"not audio at all" * 10)
    if kind == "decode":
        monkeypatch.setattr(ingest, "_load_waveform", lambda p: ([], 0.0))
    else:  # an unexpected error after ffmpeg wrote the WAV
        def boom(waveform):
            raise RuntimeError("boom")
        monkeypatch.setattr(ingest, "_estimate_snr", boom)
    return ingest.ingest_audio(audio_bytes=CLIP.read_bytes())


@pytest.mark.parametrize("kind", ["ffmpeg", "decode", "exception"])
def test_cleanup_on_removes_the_temp_wav_of_a_failed_ingest(kind, tmp_path, monkeypatch):
    """A failed ingest hands no path to discard(), so ingest_audio must delete its own."""
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(config, "CLEANUP_TEMP_AUDIO", True)
    failed = _failing_ingest(kind, monkeypatch)
    assert failed.error and not failed.normalized_wav_path
    assert list(tmp_path.glob("*.wav")) == []


@pytest.mark.parametrize("kind", ["ffmpeg", "decode", "exception"])
def test_cleanup_off_keeps_the_failed_ingest_behaviour(kind, tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(config, "CLEANUP_TEMP_AUDIO", False)
    _failing_ingest(kind, monkeypatch)
    assert len(list(tmp_path.glob("*.wav"))) == 1


# --- enrollment, real ECAPA ---------------------------------------------------------

@pytest.mark.skipif(not (config.MODELS_DIR / "ecapa").is_dir(), reason="needs models/ecapa/")
def test_cleanup_on_still_enrolls_and_removes_the_temp_wav(tmp_path, temp_wavs, monkeypatch):
    from fastapi.testclient import TestClient

    from audio_ml import enroll
    from server.main import app

    monkeypatch.setattr(config, "CLEANUP_TEMP_AUDIO", True)
    monkeypatch.setattr(enroll, "ENROLLMENTS_DIR", tmp_path)
    monkeypatch.setattr(config, "ENROLLMENTS_DIR", tmp_path)

    clip = config.REPO_ROOT / "data" / "eval_set" / "clips" / "friend.wav"
    with TestClient(app) as c:
        with clip.open("rb") as fh:
            r = c.post("/api/enroll", data={"name": "Retention test", "relation": "Friend"},
                       files={"file": ("f.wav", fh, "audio/wav")})
        assert r.status_code == 201, r.text
        person_id = r.json()["person_id"]
        try:
            assert (tmp_path / f"{person_id}.npz").is_file()
            assert temp_wavs and not [p for p in temp_wavs if p.exists()]
        finally:
            c.delete(f"/api/persons/{person_id}")


# --- enrol_from_call explains an empty list --------------------------------------

def test_enrol_from_call_says_retention_is_off(monkeypatch, tmp_path, capsys):
    from scripts import enrol_from_call

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "RETAIN_SESSION_AUDIO", False)
    enrol_from_call.list_sessions()
    assert "RETAIN_SESSION_AUDIO" in capsys.readouterr().out


# --- the session id names a folder: it must not escape data/sessions ----------------

@pytest.mark.parametrize("url_id", ["..%5C..%5Cevil", "..%5Cevil", "a%5Cb", ".."])
def test_retention_refuses_a_session_id_that_is_not_a_plain_folder_name(client, monkeypatch, tmp_path, url_id):
    """%5C decodes to a backslash and survives routing as one path segment; on Windows
    `DATA_DIR / "sessions" / "..\..\evil"` is outside DATA_DIR."""
    data = tmp_path / "a" / "b" / "data"
    data.mkdir(parents=True)
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "RETAIN_SESSION_AUDIO", True)
    try:
        _stream_one_chunk(client, session_id="ignored", url_id=url_id)
    except Exception:
        pass  # rejecting the connection outright is also acceptable
    written = list(tmp_path.rglob("chunk_*.wav"))
    assert written == [], f"retention for {url_id!r} wrote {written}"


def test_a_plain_session_id_is_still_retained(client, monkeypatch):
    monkeypatch.setattr(config, "RETAIN_SESSION_AUDIO", True)
    assert (config.DATA_DIR / "sessions" / _stream_one_chunk(client, session_id=f"call-{uuid.uuid4().int % 10**13}") / "chunk_0000.wav").is_file()


def test_enrol_from_call_does_not_claim_retention_is_off_when_sessions_exist(
    monkeypatch, tmp_path, capsys
):
    # The flag here is this shell's, not the server's: the runbook sets it only on the
    # uvicorn line. Retained chunks on disk prove the server is keeping audio, so a
    # "retention is off, restart the server" warning above them would be false.
    from scripts import enrol_from_call

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "RETAIN_SESSION_AUDIO", False)
    session = tmp_path / "sessions" / "call-1"
    session.mkdir(parents=True)
    (session / "chunk_0000.wav").write_bytes(b"RIFF")
    enrol_from_call.list_sessions()
    out = capsys.readouterr().out
    assert "call-1" in out
    assert "RETAIN_SESSION_AUDIO" not in out
