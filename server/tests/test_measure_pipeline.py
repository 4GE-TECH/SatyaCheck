"""Item 14: latency and false-positive measurement on the (simulated) Exotel path.

Two seams: the runner's `observer` hook, which reports how long each verdict took from
the arrival of the frame that completed its window, and `scripts/measure_pipeline.py`,
which replays WAV files as Exotel calls through the real route and runner. The
arithmetic is checked against hand-computed numbers; the end-to-end run uses fake
branches so it needs no models.
"""

from __future__ import annotations

import asyncio
import json
import math

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

CLIP = config.REPO_ROOT / "data" / "eval_set" / "clips" / "friend_test.wav"


# --- arithmetic ---------------------------------------------------------------------------

def test_percentiles_match_numpy_linear_interpolation():
    from scripts.measure_pipeline import percentile

    values = [10.0, 20.0, 30.0, 40.0, 100.0]
    assert percentile(values, 50) == 30.0
    assert percentile(values, 95) == pytest.approx(float(np.percentile(values, 95)))
    assert percentile([7.0], 95) == 7.0
    assert math.isnan(percentile([], 50))


def test_false_positive_rate_counts_only_genuine_sessions_reaching_a_warning():
    from scripts.measure_pipeline import summarise

    sessions = [
        {"file": "a.wav", "genuine": True, "final_band": "unverified", "latencies_ms": [100, 200]},
        {"file": "b.wav", "genuine": True, "final_band": "suspicious", "latencies_ms": [300]},
        {"file": "c.wav", "genuine": True, "final_band": "caution", "latencies_ms": [400]},
        {"file": "d.wav", "genuine": True, "final_band": "high_risk", "latencies_ms": [500]},
        {"file": "e.wav", "genuine": False, "final_band": "high_risk", "latencies_ms": [600]},
    ]
    out = summarise(sessions)
    assert out["n_sessions"] == 5 and out["n_genuine"] == 4 and out["n_windows"] == 6
    assert out["false_positive_rate"] == pytest.approx(2 / 4)        # suspicious + high_risk
    assert out["caution_rate"] == pytest.approx(1 / 4)
    assert sorted(out["false_positive_files"]) == ["b.wav", "d.wav"]
    assert out["latency_ms"]["p50"] == pytest.approx(float(np.percentile([100, 200, 300, 400, 500, 600], 50)))


def test_a_run_with_no_genuine_sessions_reports_no_rate_rather_than_zero():
    from scripts.measure_pipeline import summarise

    out = summarise([{"file": "e.wav", "genuine": False, "final_band": "high_risk", "latencies_ms": [1]}])
    assert out["false_positive_rate"] is None


# --- the runner's observer hook ---------------------------------------------------------------

def _branches(monkeypatch):
    import server.orchestrator as orch

    monkeypatch.setattr(config, "USE_REAL_SPEAKER", True)
    monkeypatch.setattr(config, "USE_REAL_SPOOF", True)
    monkeypatch.setattr(orch, "_real_speaker_branch", lambda p: SpeakerVerificationResult.neutral())
    monkeypatch.setattr(orch, "_real_spoof_branch",
                        lambda p: AntiSpoofResult(risk=0.2, details={"available": True}))


class _Quiet:
    def push(self, chunk, sample_rate=16000):
        return TranscriptResult.empty()

    def flush(self):
        return TranscriptResult.empty()


def test_the_observer_sees_every_dispatched_event_with_a_latency(monkeypatch, tmp_path):
    from server.pipeline.dispatcher import Dispatcher
    from server.pipeline.runner import SessionRunner

    _branches(monkeypatch)
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    from server.database import Base
    Base.metadata.create_all(engine)
    seen = []
    runner = SessionRunner(dispatcher=Dispatcher([]), session_factory=sessionmaker(bind=engine),
                           transcriber_factory=_Quiet, analyze=lambda t: ScriptAnalysisResult.neutral(),
                           observer=lambda event, seconds: seen.append((event, seconds)))
    tone = (0.3 * np.sin(2 * np.pi * 220 * np.arange(16000 * 5) / 16000) * 32767).astype("<i2").tobytes()

    async def go():
        await runner.open(SessionOpen(session_id="obs", source=AudioSource.EXOTEL))
        out = []
        for k, i in enumerate(range(0, len(tone), 3200)):
            out += await runner.push(AudioFrame(session_id="obs", seq=k, t_start_s=k * 0.1,
                                                pcm_s16le=tone[i:i + 3200]))
        out += await runner.close(SessionClose(session_id="obs", reason="t"))
        return out

    events = asyncio.run(go())
    assert [e for e, _ in seen] == events
    assert all(0.0 <= s < 30.0 for _, s in seen)


def test_a_failing_observer_never_breaks_scoring(monkeypatch, tmp_path, caplog):
    from server.pipeline.dispatcher import Dispatcher
    from server.pipeline.runner import SessionRunner

    _branches(monkeypatch)
    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    from server.database import Base
    Base.metadata.create_all(engine)

    def boom(event, seconds):
        raise RuntimeError("observer down")

    runner = SessionRunner(dispatcher=Dispatcher([]), session_factory=sessionmaker(bind=engine),
                           transcriber_factory=_Quiet, analyze=lambda t: ScriptAnalysisResult.neutral(),
                           observer=boom)
    tone = (0.3 * np.sin(2 * np.pi * 220 * np.arange(16000 * 3) / 16000) * 32767).astype("<i2").tobytes()

    async def go():
        await runner.open(SessionOpen(session_id="obs2", source=AudioSource.EXOTEL))
        out = await runner.push(AudioFrame(session_id="obs2", seq=0, t_start_s=0.0, pcm_s16le=tone))
        out += await runner.close(SessionClose(session_id="obs2", reason="t"))
        return out

    assert asyncio.run(go()), "verdicts still dispatched"
    assert any("observer down" in r.getMessage() for r in caplog.records)


# --- the CLI, end to end on fake branches -------------------------------------------------------

@pytest.mark.skipif(not CLIP.is_file(), reason="needs data/eval_set/clips/")
@pytest.mark.parametrize("encoding", ["raw", "mulaw"])
def test_the_cli_replays_a_clip_as_an_exotel_call_and_writes_numbers_only(monkeypatch, tmp_path, encoding):
    from scripts import measure_pipeline

    _branches(monkeypatch)
    out = tmp_path / "m.json"
    code = measure_pipeline.main(
        ["--clips", str(CLIP), "--genuine", "--speed", "50", "--encoding", encoding,
         "--out", str(out), "--label", "smoke"],
        runner_kwargs={"transcriber_factory": _Quiet,
                       "analyze": lambda t: ScriptAnalysisResult.neutral()},
    )
    assert code == 0
    report = json.loads(out.read_text())
    assert report["n_sessions"] == 1 and report["n_genuine"] == 1
    assert report["n_windows"] >= 4
    assert report["sessions"][0]["file"] == CLIP.name
    assert report["config"]["encoding"] == encoding and report["config"]["speed"] == 50.0
    assert "pcm" not in out.read_text().lower() or "pcm_s16le" not in out.read_text()


def test_the_cli_refuses_when_no_clip_exists(tmp_path):
    from scripts import measure_pipeline

    assert measure_pipeline.main(["--clips", str(tmp_path / "nope*.wav"), "--out", str(tmp_path / "o.json")]) == 1


def test_the_mulaw_encoder_round_trips_through_the_adapters_decoder():
    """A wrong encoder would hand the measurement distorted audio without any error."""
    from acquisition.exotel.codec import mulaw_decode
    from scripts.measure_pipeline import _mulaw_encode

    codes = bytes(range(256))
    assert _mulaw_encode(mulaw_decode(codes)) == bytes(c if c != 0x7F else 0xFF for c in codes)
    x = (np.sin(np.linspace(0, 40, 4000)) * 20000).astype(np.int16)
    back = mulaw_decode(_mulaw_encode(x)).astype(np.int32)
    assert np.max(np.abs(back - x) / (np.abs(x) + 64)) < 0.07  # G.711 is ~3-6% relative
