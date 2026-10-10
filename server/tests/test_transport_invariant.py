"""Item 2: the checks hear the same audio whatever the transport.

The rule (CLAUDE.md, "Module boundaries"): audio from any source reaches the pipeline as
`contracts.AudioFrame` (16 kHz mono s16le). The transport is named only on
`SessionOpen.source`, which only the runner and dispatcher read. Identity, authenticity
and intent never learn whether a call came from Exotel, the app's WebSocket, an upload
or a bystanding phone — so a verdict cannot depend on it.

  * STATIC  — the check modules cannot even name the transport (AST walk).
  * DYNAMIC — one real clip, three transports, byte-identical branch inputs.
  * SILENCE — digital zero is logged as such, and still scored.
  * Units for acquisition.app_ws and acquisition.upload.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import io
import logging
import wave
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from contracts import (
    AntiSpoofResult,
    AudioFrame,
    AudioSource,
    ScriptAnalysisResult,
    SessionClose,
    SessionOpen,
    SpeakerVerificationResult,
    TranscriptResult,
)

REPO = config.REPO_ROOT
CLIP = REPO / "data" / "eval_set" / "clips" / "friend_test.wav"  # 10.36 s, 16 kHz mono s16
SR = 16_000

# --- STATIC ---------------------------------------------------------------------------

CHECK_DIRS = ["audio_ml", "nlp_rag"]
CHECK_FILES = [
    "server/orchestrator.py",
    "server/escalation.py",
    "server/pipeline/buffer.py",
    "server/pipeline/transcript_worker.py",
]
FORBIDDEN_NAMES = {"AudioSource", "SessionOpen"}
FORBIDDEN_ATTRS = {"source", "channel_type"}


def _check_files() -> list[Path]:
    files = [REPO / f for f in CHECK_FILES]
    for d in CHECK_DIRS:
        files.extend(sorted(p for p in (REPO / d).rglob("*.py") if "__pycache__" not in p.parts))
    return files


def _violations(path: Path) -> list[str]:
    rel = path.relative_to(REPO).as_posix()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    except SyntaxError as e:
        return [f"{rel}:{e.lineno}: does not parse ({e.msg})"]
    out = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "acquisition" or a.name.startswith("acquisition."):
                    out.append(f"{rel}:{line}: imports {a.name}")
                if a.asname in FORBIDDEN_NAMES:
                    out.append(f"{rel}:{line}: binds {a.asname}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "acquisition" or mod.startswith("acquisition."):
                out.append(f"{rel}:{line}: imports from {mod}")
            for a in node.names:
                if a.name in FORBIDDEN_NAMES or a.asname in FORBIDDEN_NAMES:
                    out.append(f"{rel}:{line}: imports {a.name}")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            out.append(f"{rel}:{line}: names {node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_NAMES:
                out.append(f"{rel}:{line}: names .{node.attr}")
            if node.attr in FORBIDDEN_ATTRS:
                out.append(f"{rel}:{line}: reads .{node.attr}")
    return out


def test_the_check_set_is_not_empty():
    files = _check_files()
    assert all(f.is_file() for f in files[:len(CHECK_FILES)]), "a named check file moved"
    assert len(files) > len(CHECK_FILES) + 10, "audio_ml/ and nlp_rag/ were not walked"


def test_no_check_can_name_the_transport():
    found = [v for f in _check_files() for v in _violations(f)]
    assert not found, "the checks must not see the transport:\n  " + "\n  ".join(found)


def test_the_static_walker_catches_each_kind_of_leak(tmp_path):
    # Guard against a walker that silently passes everything.
    leaky = tmp_path / "leaky.py"
    leaky.write_text(
        "import acquisition.api\n"
        "from acquisition import api\n"
        "from contracts import AudioSource\n"
        "def f(msg, s):\n"
        "    return msg.source, s.channel_type, SessionOpen\n",
        encoding="utf-8",
    )
    old = REPO
    try:
        globals()["REPO"] = tmp_path
        found = _violations(leaky)
    finally:
        globals()["REPO"] = old
    assert len(found) == 6, found
    assert [v.split(":")[1] for v in found].count("5") == 3


def test_audio_frame_carries_no_transport():
    fields = set(AudioFrame.model_fields)
    assert not fields & {"source", "codec", "channel_type", "transport"}, fields
    assert "source" in SessionOpen.model_fields


def test_acquisition_imports_only_contracts_config_and_the_stdlib():
    allowed_first_party = {"contracts", "config", "acquisition"}
    banned = {"server", "audio_ml", "nlp_rag", "web", "scripts"}
    files = sorted((REPO / "acquisition").rglob("*.py"))
    assert files, "acquisition/ is missing"
    found = []
    for path in files:
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods = [node.module or ""]
            for m in mods:
                top = m.split(".")[0]
                if top in banned:
                    found.append(f"{rel}:{node.lineno}: imports {m}")
                elif (REPO / top).is_dir() or (REPO / f"{top}.py").is_file():
                    if top not in allowed_first_party:
                        found.append(f"{rel}:{node.lineno}: imports first-party {m}")
    assert not found, "\n  ".join(found)


# --- DYNAMIC --------------------------------------------------------------------------

class _NoText:
    """A transcriber that hears everything and says nothing; records what it heard."""

    heard: list[bytes] = []

    def push(self, chunk, sample_rate=SR):
        _NoText.heard.append(np.asarray(chunk, dtype=np.float32).tobytes())
        return TranscriptResult.empty()

    def flush(self):
        return TranscriptResult.empty()


class _Spy:
    """Stands in for the speaker and anti-spoof branches; records the WAV each one got."""

    def __init__(self):
        self.calls = {"speaker": [], "spoof": []}

    @staticmethod
    def _read(path: str) -> tuple[str, int, int, float]:
        with wave.open(path, "rb") as w:
            pcm = w.readframes(w.getnframes())
            return (hashlib.sha256(pcm).hexdigest(), w.getframerate(), w.getnchannels(),
                    round(w.getnframes() / w.getframerate(), 6))

    def speaker(self, path, owner_id=None):
        self.calls["speaker"].append(self._read(path))
        return SpeakerVerificationResult.neutral()

    def spoof(self, path):
        self.calls["spoof"].append(self._read(path))
        return AntiSpoofResult(risk=0.0, details={"available": True})


class _Recorder:
    name = "recorder"

    def __init__(self):
        self.events = []

    async def deliver(self, event):
        self.events.append(event)


@pytest.fixture
def db_factory(tmp_path):
    from server.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'invariant.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def spy(monkeypatch):
    import server.orchestrator as orch

    s = _Spy()
    monkeypatch.setattr(config, "USE_REAL_SPEAKER", True)
    monkeypatch.setattr(config, "USE_REAL_SPOOF", True)
    monkeypatch.setattr(orch, "_real_speaker_branch", s.speaker)
    monkeypatch.setattr(orch, "_real_spoof_branch", s.spoof)
    monkeypatch.setattr(config, "ESCALATION_PERSISTENCE_N", 1)
    return s


async def _run(frames: list[AudioFrame], source: AudioSource, sid: str, db_factory) -> list:
    from server.pipeline.dispatcher import Dispatcher
    from server.pipeline.runner import SessionRunner

    rec = _Recorder()
    runner = SessionRunner(dispatcher=Dispatcher([rec]), session_factory=db_factory,
                           transcriber_factory=_NoText,
                           analyze=lambda t: ScriptAnalysisResult.neutral())
    await runner.open(SessionOpen(session_id=sid, source=source))
    for f in frames:
        await runner.push(f)
    await runner.close(SessionClose(session_id=sid, reason="test"))
    return rec.events


def _clip_pcm() -> bytes:
    with wave.open(str(CLIP), "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (SR, 1, 2)
        return w.readframes(w.getnframes())


def _telephony_frames(sid: str) -> list[AudioFrame]:
    """(a) What a telephony adapter emits: 20 ms frames straight from 16 kHz samples."""
    pcm = _clip_pcm()
    step = int(0.02 * SR) * 2
    pieces = [pcm[i:i + step] for i in range(0, len(pcm), step)]
    return [AudioFrame(session_id=sid, seq=k, t_start_s=k * 0.02, pcm_s16le=p,
                       is_final=k == len(pieces) - 1) for k, p in enumerate(pieces)]


def _app_ws_frames(sid: str) -> list[AudioFrame]:
    """(b) The app's WebSocket: 3 s self-contained WAV chunks, decoded one at a time."""
    from acquisition.api import AppWsDecoder
    from server.tests.test_ws_rolling_buffer import _split_into_wav_chunks

    chunks = _split_into_wav_chunks(CLIP, chunk_s=3.0)
    dec = AppWsDecoder(sid)
    frames = []
    for i, c in enumerate(chunks):
        frames.extend(dec.decode(c, is_final=i == len(chunks) - 1))
    return frames


def _upload_frames(sid: str) -> list[AudioFrame]:
    """(c) An upload: the whole file through ffmpeg."""
    from acquisition.api import decode_upload

    return decode_upload(CLIP.read_bytes(), sid)


@pytest.mark.skipif(not CLIP.is_file(), reason="needs data/eval_set/clips/")
def test_every_transport_gives_the_checks_identical_audio(spy, db_factory):
    runs = {}
    for name, make, source in [
        ("telephony", _telephony_frames, AudioSource.EXOTEL),
        ("app_ws", _app_ws_frames, AudioSource.APP_WS),
        ("upload", _upload_frames, AudioSource.UPLOAD),
    ]:
        sid = f"inv-{name}"
        frames = make(sid)
        assert frames, f"{name}: no frames"
        spy.calls = {"speaker": [], "spoof": []}
        _NoText.heard = []
        events = asyncio.run(_run(frames, source, sid, db_factory))
        runs[name] = {
            "frames_pcm": hashlib.sha256(b"".join(f.pcm_s16le for f in frames)).hexdigest(),
            "speaker": list(spy.calls["speaker"]),
            "spoof": list(spy.calls["spoof"]),
            "asr": hashlib.sha256(b"".join(_NoText.heard)).hexdigest(),
            "asr_samples": sum(len(b) for b in _NoText.heard) // 4,
            "windows": [(e.window_index, e.is_final, e.response.fusion.band.value) for e in events],
        }

    base = runs["telephony"]
    # 10.36 s: windows end at 2, 4, 6, 8, 10 s, plus the 10.36 s tail.
    assert len(base["speaker"]) == 6, base["speaker"]
    assert {c[1:3] for c in base["speaker"]} == {(SR, 1)}
    assert base["speaker"] == base["spoof"], "the two branches must hear the same window"
    assert base["asr_samples"] == len(_clip_pcm()) // 2, "the transcriber did not hear the call"
    for name in ("app_ws", "upload"):
        run = runs[name]
        assert run["frames_pcm"] == base["frames_pcm"], f"{name}: frame audio differs"
        assert run["speaker"] == base["speaker"], f"{name}: speaker branch heard different audio"
        assert run["spoof"] == base["spoof"], f"{name}: anti-spoof branch heard different audio"
        assert run["asr"] == base["asr"], f"{name}: the transcriber heard different audio"
        assert run["windows"] == base["windows"], f"{name}: different verdict sequence"


# --- SILENCE --------------------------------------------------------------------------

def test_an_all_zero_stream_is_logged_silent_and_still_scored(spy, db_factory, caplog):
    sid = "silent-1"
    zero = bytes(2 * SR)  # 1 s of digital zero
    frames = [AudioFrame(session_id=sid, seq=k, t_start_s=float(k), pcm_s16le=zero)
              for k in range(7)]
    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        events = asyncio.run(_run(frames, AudioSource.APP_WS, sid, db_factory))
    silent = [r for r in caplog.records if "stream silent" in r.getMessage()]
    assert len(silent) == 1, "warn once per session, not once per window"
    assert silent[0].levelno == logging.WARNING
    assert sid in silent[0].getMessage()
    # 7 s: windows at 2, 4, 6 s, then the tail — all scored (insufficient), all dispatched.
    assert len(events) == 4 and events[-1].is_final
    assert all(e.response.fusion.band.value == "insufficient" for e in events)


def test_quiet_but_live_audio_is_not_called_silent(spy, db_factory, caplog):
    sid = "quiet-1"
    rng = np.random.default_rng(0)
    hiss = rng.integers(-3, 4, size=SR, dtype=np.int16).astype("<i2").tobytes()
    frames = [AudioFrame(session_id=sid, seq=k, t_start_s=float(k), pcm_s16le=hiss)
              for k in range(5)]
    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        asyncio.run(_run(frames, AudioSource.APP_WS, sid, db_factory))
    assert not [r for r in caplog.records if "stream silent" in r.getMessage()]


# --- acquisition.app_ws ---------------------------------------------------------------

def _sine_wav(rate: int, channels: int, seconds: float, freq: float = 1000.0,
              amp: float = 0.5) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    mono = np.round(amp * 32767 * np.sin(2 * np.pi * freq * t)).astype("<i2")
    pcm = np.repeat(mono, channels) if channels > 1 else mono
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _spectrum(frames: list[AudioFrame]) -> tuple[float, float]:
    x = np.frombuffer(b"".join(f.pcm_s16le for f in frames), dtype="<i2").astype(np.float64) / 32768.0
    x = x[len(x) // 10: -len(x) // 10]  # skip resampler edges
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    peak_hz = np.fft.rfftfreq(len(x), 1 / SR)[int(np.argmax(spec))]
    rms_db = 20 * np.log10(np.sqrt(np.mean(x ** 2)))
    return float(peak_hz), float(rms_db)


def test_app_ws_resamples_44k1_stereo_to_16k_mono_preserving_the_tone():
    from acquisition.api import AppWsDecoder

    dec = AppWsDecoder("ws-1")
    frames = dec.decode(_sine_wav(44_100, 2, 1.0))
    frames += dec.decode(_sine_wav(44_100, 2, 1.0), is_final=True)
    assert frames and all(f.sample_rate == SR and f.session_id == "ws-1" for f in frames)
    assert [f.seq for f in frames] == list(range(len(frames)))
    assert frames[-1].is_final and not any(f.is_final for f in frames[:-1])
    # Continuing timeline: each frame starts where the previous one's samples end.
    for a, b in zip(frames, frames[1:]):
        assert b.t_start_s == pytest.approx(a.t_start_s + len(a.pcm_s16le) / 2 / SR, abs=1e-9)
    peak_hz, rms_db = _spectrum(frames)
    assert abs(peak_hz - 1000.0) <= 2.0, peak_hz
    expected_db = 20 * np.log10(0.5 / np.sqrt(2))
    assert abs(rms_db - expected_db) <= 1.0, (rms_db, expected_db)


def test_app_ws_16k_mono_chunks_pass_through_bit_exact():
    from acquisition.api import AppWsDecoder

    chunk = _sine_wav(SR, 1, 0.5, freq=440.0)
    with wave.open(io.BytesIO(chunk)) as w:
        pcm = w.readframes(w.getnframes())
    frames = AppWsDecoder("ws-2").decode(chunk)
    assert b"".join(f.pcm_s16le for f in frames) == pcm


def test_app_ws_garbage_is_empty_and_logged_and_the_timeline_does_not_move(caplog):
    from acquisition.api import AppWsDecoder

    dec = AppWsDecoder("ws-3")
    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        assert dec.decode(b"\x00\x01not a wav at all" * 10) == []
    assert any("ws-3" in r.getMessage() for r in caplog.records), "no reason was logged"
    ok = dec.decode(_sine_wav(SR, 1, 0.5))
    assert ok and ok[0].seq == 0 and ok[0].t_start_s == 0.0


# --- acquisition.upload ---------------------------------------------------------------

def test_upload_splits_into_fixed_frames_ending_final():
    from acquisition.api import decode_upload

    frames = decode_upload(_sine_wav(22_050, 1, 2.3), "up-1", frame_s=0.5)
    assert [f.seq for f in frames] == list(range(5))
    assert [f.t_start_s for f in frames] == pytest.approx([0.0, 0.5, 1.0, 1.5, 2.0])
    assert all(len(f.pcm_s16le) == 2 * 8000 for f in frames[:-1])
    assert frames[-1].is_final and not any(f.is_final for f in frames[:-1])
    assert abs(_spectrum(frames)[0] - 1000.0) <= 2.0


def test_upload_accepts_a_path():
    from acquisition.api import decode_upload

    if not CLIP.is_file():
        pytest.skip("needs data/eval_set/clips/")
    frames = decode_upload(CLIP, "up-2")
    assert b"".join(f.pcm_s16le for f in frames) == _clip_pcm()


def test_upload_garbage_is_empty_and_logged(caplog):
    from acquisition.api import decode_upload

    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        assert decode_upload(b"this is not audio" * 100, "up-3") == []
    msgs = [r.getMessage() for r in caplog.records if "up-3" in r.getMessage()]
    assert msgs and any("ffmpeg" in m or "no audio" in m for m in msgs), msgs


def test_upload_empty_bytes_is_empty_and_logged(caplog):
    from acquisition.api import decode_upload

    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        assert decode_upload(b"", "up-4") == []
    assert any("up-4" in r.getMessage() for r in caplog.records)
