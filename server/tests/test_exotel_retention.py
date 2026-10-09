"""Exotel calls are retained like app sessions when RETAIN_SESSION_AUDIO is on.

A live Exotel call came back "unverified" for 73 s because ASR gated every transcript,
and there was no audio to replay: only the app WebSocket path wrote
data/sessions/<id>/. The Exotel runner now writes the whole call as
data/sessions/<id>/chunk_0000.wav (the name enrol_from_call globs), and nothing when
retention is off.
"""

from __future__ import annotations

import asyncio
import wave

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from contracts import (AntiSpoofResult, AudioFrame, AudioSource, ScriptAnalysisResult, SessionClose,
                       SessionOpen, SpeakerVerificationResult, TranscriptResult)


class _Quiet:
    def push(self, chunk, sample_rate=16000):
        return TranscriptResult.empty()

    def flush(self):
        return TranscriptResult.empty()


@pytest.fixture
def runner(monkeypatch, tmp_path):
    import server.main
    import server.orchestrator as orch
    from server.database import Base
    from server.pipeline.dispatcher import Dispatcher

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(orch, "_real_speaker_branch", lambda p: SpeakerVerificationResult.neutral())
    monkeypatch.setattr(orch, "_real_spoof_branch", lambda p: AntiSpoofResult(risk=0.2, details={"available": True}))
    engine = create_engine(f"sqlite:///{tmp_path / 'r.db'}")
    Base.metadata.create_all(engine)
    return server.main._RetainingRunner(
        dispatcher=Dispatcher([]), session_factory=sessionmaker(bind=engine),
        transcriber_factory=_Quiet, analyze=lambda t: ScriptAnalysisResult.neutral())


def _call(runner, sid="call-7", seconds=3.0):
    t = np.arange(int(16000 * seconds)) / 16000
    pcm = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2").tobytes()
    step = 3200  # 0.1 s

    async def go():
        await runner.open(SessionOpen(session_id=sid, source=AudioSource.EXOTEL, opened_at="2026-10-07T00:00:00Z"))
        for k, i in enumerate(range(0, len(pcm), step)):
            await runner.push(AudioFrame(session_id=sid, seq=k, t_start_s=i / 32000, pcm_s16le=pcm[i:i + step]))
        await runner.close(SessionClose(session_id=sid, reason="callended"))

    asyncio.run(go())
    return pcm


def test_retention_on_writes_the_whole_call(runner, monkeypatch):
    monkeypatch.setattr(config, "RETAIN_SESSION_AUDIO", True)
    pcm = _call(runner)
    d = config.DATA_DIR / "sessions" / "call-7"
    assert [p.name for p in d.iterdir()] == ["chunk_0000.wav"]
    with wave.open(str(d / "chunk_0000.wav")) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        assert w.readframes(w.getnframes()) == pcm


def test_retention_off_writes_nothing(runner, monkeypatch):
    monkeypatch.setattr(config, "RETAIN_SESSION_AUDIO", False)
    _call(runner)
    assert not (config.DATA_DIR / "sessions").exists()


def test_the_exotel_factory_retains():
    import server.main

    assert isinstance(server.main._exotel_runner(), server.main._RetainingRunner)
