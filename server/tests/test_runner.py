"""Item 5: the runner — frames in, one dispatched verdict per window out.

`SessionRunner` is the seam every audio source feeds (`open` / `push` / `close` with the
C1 contract models). Per session it owns the rolling buffer, the out-of-band transcript
worker, the escalation gate and the dispatcher, and it scores each window with
`orchestrator.screen_window` — speaker and anti-spoof only; text comes from whatever the
transcript worker has published so far. The acoustic verdict never waits for Whisper.

Everything model-shaped is faked here (speaker, spoof, transcriber, sinks), so these pin
cadence, ordering, escalation and cleanup rather than model output. Fusion itself is the
real, unchanged `_compute_fusion`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time

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
    SpeakerVerdict,
    SpeakerVerificationResult,
    TranscriptResult,
    TrustBand,
)
from server import audio_ingest
from server import orchestrator
from server.pipeline import runner as runner_mod
from server.pipeline.dispatcher import Dispatcher, ReportSink
from server.pipeline.runner import SessionRunner

SR = 16_000
SID = "run-1"


# --- audio ----------------------------------------------------------------------------

def _speechy(seconds: float) -> np.ndarray:
    """Passes the quality gate: 0.4 s tone bursts, 0.1 s near-silent gaps (high SNR)."""
    n = int(round(seconds * SR))
    t = np.arange(n) / SR
    tone = 0.3 * np.sin(2 * np.pi * 220.0 * t)
    gap = (t % 0.5) >= 0.4
    tone[gap] = 1e-4 * np.sin(2 * np.pi * 50.0 * t[gap])
    return tone.astype(np.float32)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(round(seconds * SR)), dtype=np.float32)


def _frames(pcm: np.ndarray, frame_s: float, session_id: str = SID, seq0: int = 0,
            t0: float = 0.0, final_last: bool = False) -> list[AudioFrame]:
    step = int(round(frame_s * SR))
    out = []
    for k, i in enumerate(range(0, len(pcm), step)):
        piece = pcm[i:i + step]
        s16 = np.clip(np.round(piece * 32768.0), -32768, 32767).astype("<i2").tobytes()
        out.append(AudioFrame(session_id=session_id, seq=seq0 + k, t_start_s=t0 + i / SR,
                              pcm_s16le=s16))
    if final_last and out:
        out[-1] = out[-1].model_copy(update={"is_final": True})
    return out


# --- fakes ----------------------------------------------------------------------------

class Recorder:
    name = "recorder"

    def __init__(self):
        self.events = []
        self.times = []

    async def deliver(self, event):
        self.events.append(event)
        self.times.append(time.perf_counter())


class FakeTranscriber:
    """StreamingTranscriber's interface. Sleeps on every push."""

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.seconds = 0.0
        self.first_done_at = None
        self.flushed = False

    def push(self, chunk, sample_rate=SR):
        time.sleep(self.delay)
        self.seconds += len(chunk) / sample_rate
        if self.first_done_at is None:
            self.first_done_at = time.perf_counter()
        return TranscriptResult(text=f"heard {self.seconds:.1f}s", detected_language="en", confidence=0.9)

    def flush(self):
        self.flushed = True
        return TranscriptResult(text=f"final {self.seconds:.1f}s", detected_language="en", confidence=0.9)


def _analyze(transcript):
    return ScriptAnalysisResult(risk=0.0, details={"available": True})


# (speaker verdict, speaker risk, spoof risk) per window, driving the fused band in
# identity_check. Chosen to land in the same band whether or not a transcript (risk 0)
# is available yet, since that depends on worker timing: fused risk with text live /
# abstaining is caution .20/.27, suspicious .40/.53, high risk .75/1.0.
BANDS = {
    "verified": (SpeakerVerdict.MATCH, 0.0, 0.0),
    "caution": (SpeakerVerdict.MISMATCH, 0.5, 0.0),
    "suspicious": (SpeakerVerdict.MISMATCH, 1.0, 0.0),
    "high_risk": (SpeakerVerdict.MISMATCH, 1.0, 1.0),
}


class Branches:
    """Fake speaker + spoof branches, played from a per-window plan."""

    def __init__(self, plan=None, speaker_fail_on=None):
        self.plan = list(plan or [])
        self.speaker_fail_on = speaker_fail_on
        self.speaker_calls = 0
        self.spoof_calls = 0
        self.paths = []
        self._lock = threading.Lock()

    def _entry(self, i):
        name = self.plan[i] if i < len(self.plan) else "verified"
        return BANDS[name]

    def speaker(self, wav_path):
        with self._lock:
            i = self.speaker_calls
            self.speaker_calls += 1
            self.paths.append(wav_path)
        assert os.path.exists(wav_path), "branch got a path that does not exist"
        if self.speaker_fail_on is not None and i == self.speaker_fail_on:
            raise RuntimeError("ECAPA exploded")
        verdict, risk, _ = self._entry(i)
        return SpeakerVerificationResult(verdict=verdict, risk=risk, raw_score=0.5,
                                         matched_person_id="p1", matched_person_name="Papa")

    def spoof(self, wav_path):
        with self._lock:
            i = self.spoof_calls
            self.spoof_calls += 1
        _, _, spoof_risk = self._entry(i)
        return AntiSpoofResult(risk=spoof_risk, median_score=spoof_risk, peak_score=spoof_risk,
                               is_synthetic=spoof_risk > 0.5, details={"available": True})


@pytest.fixture
def branches(monkeypatch):
    b = Branches()
    monkeypatch.setattr(config, "USE_REAL_SPEAKER", True)
    monkeypatch.setattr(config, "USE_REAL_SPOOF", True)
    monkeypatch.setattr(orchestrator, "_real_speaker_branch", b.speaker)
    monkeypatch.setattr(orchestrator, "_real_spoof_branch", b.spoof)
    return b


@pytest.fixture(autouse=True)
def fast_ingest(monkeypatch):
    # Silero VAD chunking is not read by the gate or by the fake branches; loading it
    # per window only makes these tests slow.
    monkeypatch.setattr(audio_ingest, "_vad_chunk", lambda waveform, sample_rate: [])
    monkeypatch.setattr(config, "ESCALATION_PERSISTENCE_N", 1)
    # The fakes return whatever the plan says at any length; the short-window rule for
    # the real anti-spoof model is tested on its own below.
    monkeypatch.setattr(config, "STREAM_SPOOF_MIN_WINDOW_S", 0.0)


@pytest.fixture
def db_factory(tmp_path):
    from server.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'runner.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def fusions(monkeypatch):
    calls = []
    real = orchestrator._compute_fusion

    def counting(speaker, spoof, script):
        calls.append(time.perf_counter())
        return real(speaker, spoof, script)

    monkeypatch.setattr(orchestrator, "_compute_fusion", counting)
    return calls


def _runner(db_factory, sinks, transcriber=None):
    transcriber = transcriber or FakeTranscriber()
    return SessionRunner(
        dispatcher=Dispatcher(sinks),
        session_factory=db_factory,
        transcriber_factory=lambda: transcriber,
        analyze=_analyze,
    )


def _open(session_id=SID):
    return SessionOpen(session_id=session_id, source=AudioSource.UPLOAD)


# --- one fusion, one dispatch per window ---------------------------------------------------

@pytest.mark.parametrize("frame_s", [0.5, 3.0, 12.0])
def test_one_fusion_and_one_dispatch_per_window_in_order(frame_s, branches, fusions, db_factory):
    rec = Recorder()

    async def scenario():
        runner = _runner(db_factory, [rec])
        await runner.open(_open())
        for frame in _frames(_speechy(12.0), frame_s):
            await runner.push(frame)
        pushed = (len(fusions), [e.window_index for e in rec.events])
        await runner.close(SessionClose(session_id=SID, reason="test"))
        return pushed

    n_fusions, indices = asyncio.run(scenario())
    # 12 s of audio, a window every 2 s.
    assert indices == [0, 1, 2, 3, 4, 5]
    assert n_fusions == 6
    assert branches.speaker_calls >= 6 and branches.spoof_calls >= 6
    assert all(e.session_id == SID and e.response.session_id == SID for e in rec.events)


# --- quality gate ----------------------------------------------------------------------------

def test_an_insufficient_window_is_dispatched_but_does_not_clear_a_latched_warning(
        branches, db_factory, monkeypatch, caplog):
    monkeypatch.setattr(config, "STREAM_CONTEXT_S", 2.0)  # non-overlapping windows
    branches.plan = ["high_risk"]
    rec = Recorder()

    async def scenario():
        runner = _runner(db_factory, [rec])
        await runner.open(_open())
        for frame in _frames(np.concatenate([_speechy(2.0), _silence(2.0)]), 1.0):
            await runner.push(frame)
        await runner.close(SessionClose(session_id=SID, reason="test"))

    with caplog.at_level(logging.INFO):
        asyncio.run(scenario())

    first, second = rec.events[0], rec.events[1]
    assert first.response.fusion.band == TrustBand.HIGH_RISK
    assert second.response.quality.passed is False, "window 1 was silence"
    assert second.response.fusion.band == TrustBand.HIGH_RISK, "latched warning cleared"
    assert branches.speaker_calls == 1, "an insufficient window must not be scored"
    assert any(SID in r.getMessage() and "quality gate" in r.getMessage().lower()
               for r in caplog.records), "the rejection was not logged with the session id"


# --- a branch failing -----------------------------------------------------------------------

def test_a_branch_exception_is_neutral_logged_and_the_session_continues(branches, db_factory, caplog):
    branches.plan = ["verified", "high_risk"]
    branches.speaker_fail_on = 0
    rec = Recorder()

    async def scenario():
        runner = _runner(db_factory, [rec])
        await runner.open(_open())
        for frame in _frames(_speechy(4.0), 1.0):
            await runner.push(frame)
        await runner.close(SessionClose(session_id=SID, reason="test"))

    with caplog.at_level(logging.ERROR):
        asyncio.run(scenario())

    first = rec.events[0].response
    assert first.speaker.verdict == SpeakerVerdict.UNKNOWN
    assert first.speaker.risk == 0.5
    assert any(SID in r.getMessage() and "speaker" in r.getMessage().lower()
               and "ECAPA exploded" in r.getMessage() for r in caplog.records)
    assert rec.events[1].response.fusion.band == TrustBand.HIGH_RISK, "session did not continue"


# --- ASR never blocks the acoustic verdict -------------------------------------------------------

def test_acoustic_verdicts_do_not_wait_for_asr_and_later_windows_use_the_newest_transcript(
        branches, db_factory):
    transcriber = FakeTranscriber(delay=1.0)
    rec = Recorder()

    async def scenario():
        runner = _runner(db_factory, [rec], transcriber)
        await runner.open(_open())
        started = time.perf_counter()
        for frame in _frames(_speechy(6.0), 0.5):
            await runner.push(frame)
        early = list(rec.events)
        early_done = time.perf_counter()
        assert transcriber.first_done_at is None, "fixture: ASR finished too quickly to test"

        worker = runner.worker(SID)
        await worker.wait_idle()
        newest = worker.latest.transcript.text

        for frame in _frames(_speechy(2.0), 0.5, seq0=12, t0=6.0):
            await runner.push(frame)
        late = rec.events[len(early):]
        await runner.close(SessionClose(session_id=SID, reason="test"))
        return started, early, early_done, newest, late

    started, early, early_done, newest, late = asyncio.run(scenario())
    assert [e.window_index for e in early] == [0, 1, 2]
    assert early_done - started < 1.0, "acoustic verdicts waited on the 1 s transcriber"
    assert all(t < transcriber.first_done_at for t in rec.times[:3])
    assert all(e.response.transcript.text == "" for e in early)
    assert all(e.response.script.details.get("available") is False for e in early), \
        "no transcript yet must abstain, not score as benign"
    assert newest == "heard 6.0s"
    assert [e.window_index for e in late] == [3]
    assert late[0].response.transcript.text == newest


# --- close ------------------------------------------------------------------------------------------

def _rows(db_factory):
    from server.database import ScreeningResult, ScreeningSession

    with db_factory() as db:
        rows = db.query(ScreeningResult).order_by(ScreeningResult.id).all()
        session = db.get(ScreeningSession, SID)
        return [(r.chunk_index, r.is_final) for r in rows], (session.status if session else None)


@pytest.mark.parametrize("seconds,final_frame", [(7.0, False), (6.0, False), (7.0, True)])
def test_close_emits_exactly_one_final_event_and_the_report_ends_final(
        seconds, final_frame, branches, db_factory):
    rec = Recorder()
    transcriber = FakeTranscriber()

    async def scenario():
        runner = _runner(db_factory, [rec, ReportSink(db_factory)], transcriber)
        await runner.open(_open())
        with db_factory() as db:
            from server.database import ScreeningSession
            assert db.get(ScreeningSession, SID).status == "streaming"
        for frame in _frames(_speechy(seconds), 1.0, final_last=final_frame):
            await runner.push(frame)
        await runner.close(SessionClose(session_id=SID, reason="test"))
        await runner.close(SessionClose(session_id=SID, reason="again"))  # idempotent

    asyncio.run(scenario())
    finals = [e for e in rec.events if e.is_final]
    assert len(finals) == 1
    assert rec.events[-1].is_final
    assert transcriber.flushed
    assert finals[0].response.transcript.text.startswith("final"), "final verdict lacks the final transcript"
    rows, status = _rows(db_factory)
    assert [f for _, f in rows].count(True) == 1 and rows[-1][1] is True
    assert status == "complete"
    if seconds == 6.0:
        # No tail after the last hop window: that window is re-scored and marked final.
        assert rec.events[-1].window_index == 2 and len(rec.events) == 4
    else:
        assert rec.events[-1].window_index == 3 and len(rec.events) == 4


def test_a_session_with_no_audio_still_ends_with_one_final_verdict(branches, db_factory):
    rec = Recorder()

    async def scenario():
        runner = _runner(db_factory, [rec, ReportSink(db_factory)])
        await runner.open(_open())
        await runner.close(SessionClose(session_id=SID, reason="client disconnected"))

    asyncio.run(scenario())
    assert len(rec.events) == 1 and rec.events[0].is_final
    assert rec.events[0].response.fusion.band == TrustBand.INSUFFICIENT
    assert _rows(db_factory)[1] == "complete"


# --- escalation -------------------------------------------------------------------------------------

@pytest.mark.parametrize("n,plan,expected", [
    (1, ["verified", "caution", "caution", "high_risk", "verified", "suspicious"],
     [False, True, False, True, False, False]),
    (2, ["verified", "caution", "caution", "high_risk", "high_risk", "verified"],
     [False, False, True, False, True, False]),
])
def test_escalated_only_where_the_latched_band_rose(n, plan, expected, branches, db_factory, monkeypatch):
    monkeypatch.setattr(config, "ESCALATION_PERSISTENCE_N", n)
    branches.plan = plan
    rec = Recorder()

    async def scenario():
        runner = _runner(db_factory, [rec])
        await runner.open(_open())
        for frame in _frames(_speechy(12.0), 2.0):
            await runner.push(frame)
        await runner.close(SessionClose(session_id=SID, reason="test"))

    asyncio.run(scenario())
    assert [e.escalated for e in rec.events[:6]] == expected


# --- temp audio ---------------------------------------------------------------------------------------

def test_temp_wavs_are_deleted_when_cleanup_is_on(branches, db_factory, monkeypatch):
    monkeypatch.setattr(config, "CLEANUP_TEMP_AUDIO", True)
    made = []
    real = runner_mod.ingest_pcm

    def recording(samples, *a, **kw):
        audio = real(samples, *a, **kw)
        if audio.normalized_wav_path:
            made.append(audio.normalized_wav_path)
        return audio

    monkeypatch.setattr(runner_mod, "ingest_pcm", recording)
    rec = Recorder()

    async def scenario():
        runner = _runner(db_factory, [rec])
        await runner.open(_open())
        for frame in _frames(_speechy(5.0), 1.0):
            await runner.push(frame)
        await runner.close(SessionClose(session_id=SID, reason="test"))

    asyncio.run(scenario())
    assert len(made) >= 3
    assert not [p for p in made if os.path.exists(p)], "temp WAVs left behind"


# --- never raises -------------------------------------------------------------------------------------

def test_frames_for_an_unopened_session_are_dropped_and_logged(branches, db_factory, caplog):
    rec = Recorder()

    async def scenario():
        runner = _runner(db_factory, [rec])
        return await runner.push(_frames(_speechy(2.0), 2.0, session_id="ghost")[0])

    with caplog.at_level(logging.WARNING):
        out = asyncio.run(scenario())
    assert out == [] and rec.events == []
    assert any("ghost" in r.getMessage() for r in caplog.records)


def test_screen_window_without_a_transcript_abstains_on_text(branches):
    audio = audio_ingest.ingest_pcm(_speechy(3.0))
    try:
        response = asyncio.run(orchestrator.screen_window(audio, None, None))
    finally:
        audio_ingest.discard(audio)
    assert response.transcript.text == ""
    assert response.fusion.weights_used.text_weight == 0.0
    assert branches.speaker_calls == 1 and branches.spoof_calls == 1


# --- start-of-call windows: abstain rather than guess ------------------------------------
#
# Measured on data/eval_set/clips/friend_test.wav (a genuine call) through the runner
# with real models: the first window is 2 s, AASIST tiles it to its 4.04 s input and
# scores P(synthetic) 0.998; ECAPA cannot embed 2 s (it needs 3 s inside one VAD
# segment) so the speaker is unknown; no transcript exists yet. That window fused to
# suspicious, latched, and the overlay stayed red for the whole genuine call.

def _screen(branches, seconds, transcript=None, script=None):
    audio = audio_ingest.ingest_pcm(_speechy(seconds))
    try:
        return asyncio.run(orchestrator.screen_window(audio, transcript, script, session_id=SID))
    finally:
        audio_ingest.discard(audio)


def test_anti_spoof_abstains_on_a_window_shorter_than_its_input(branches, monkeypatch, caplog):
    monkeypatch.setattr(config, "STREAM_SPOOF_MIN_WINDOW_S", 64600 / 16000)
    branches.plan = ["high_risk", "high_risk"]
    with caplog.at_level(logging.INFO):
        short = _screen(branches, 2.0)
    assert short.spoof.details.get("available") is False
    assert any(SID in r.getMessage() and "anti-spoof" in r.getMessage() for r in caplog.records)
    full = _screen(branches, 5.0)
    assert full.spoof.details.get("available") is True and full.spoof.risk == 1.0


def test_a_window_where_nothing_was_measured_is_insufficient_not_suspicious(branches, monkeypatch, caplog):
    # Stranger (unknown, the neutral 0.5), anti-spoof abstaining, no transcript yet:
    # fusing that is identity's constant 0.5 alone, which bands as suspicious.
    monkeypatch.setattr(orchestrator, "_real_spoof_branch",
                        lambda p: AntiSpoofResult(details={"available": False}))
    monkeypatch.setattr(orchestrator, "_real_speaker_branch",
                        lambda p: SpeakerVerificationResult.neutral())
    with caplog.at_level(logging.INFO):
        nothing = _screen(branches, 5.0)
    assert nothing.fusion.band == TrustBand.INSUFFICIENT
    assert any(SID in r.getMessage() and "nothing measured" in r.getMessage() for r in caplog.records)

    # Any one live signal is enough to score.
    live_text = ScriptAnalysisResult(risk=0.0, details={"available": True})
    scored = _screen(branches, 5.0, TranscriptResult(text="hello beta"), live_text)
    assert scored.fusion.band == TrustBand.UNVERIFIED


def test_a_genuine_call_start_does_not_latch_red(branches, monkeypatch, db_factory):
    """The friend_test.wav shape as measured, faked: the speaker is unknown on the 2 s
    window (ECAPA cannot embed it) and a match from 4 s on; AASIST near 1.0 on the tiled
    2 s window, then the full-window medians; no transcript in time."""
    monkeypatch.setattr(config, "STREAM_SPOOF_MIN_WINDOW_S", 64600 / 16000)
    scores = iter([0.998, 0.874, 0.547, 0.377, 0.607, 0.614, 0.614])
    speakers = iter([SpeakerVerificationResult.neutral()] + [
        SpeakerVerificationResult(verdict=SpeakerVerdict.MATCH, risk=0.2, raw_score=0.6,
                                  matched_person_id="p1", matched_person_name="Friend")] * 6)
    monkeypatch.setattr(orchestrator, "_real_speaker_branch", lambda p: next(speakers))
    monkeypatch.setattr(orchestrator, "_real_spoof_branch",
                        lambda p: AntiSpoofResult(risk=next(scores), is_synthetic=True,
                                                  details={"available": True}))
    rec = Recorder()

    async def scenario():
        runner = _runner(db_factory, [rec], FakeTranscriber(delay=5.0))  # ASR never in time
        await runner.open(_open())
        for frame in _frames(_speechy(12.0), 2.0):
            await runner.push(frame)
        return list(rec.events)

    events = asyncio.run(scenario())
    assert events[0].response.fusion.band == TrustBand.INSUFFICIENT
    assert all(e.response.fusion.band not in (TrustBand.SUSPICIOUS, TrustBand.HIGH_RISK)
               for e in events), [e.response.fusion.band.value for e in events]


# --- review fixes: final event keeps its evidence; the re-score is not a second window ----

def test_a_quality_rejected_window_keeps_the_session_transcript_and_script(branches):
    """A quiet final window must not erase the whole-call transcript from the record:
    the report reads transcript and playbooks from the final row only."""
    transcript = TranscriptResult(text="send money now", detected_language="en", confidence=0.9)
    script = ScriptAnalysisResult(risk=0.9, details={"available": True})
    audio = audio_ingest.ingest_pcm(_silence(5.0))
    try:
        assert not audio.quality.passed
        response = asyncio.run(orchestrator.screen_window(audio, transcript, script, session_id=SID))
    finally:
        audio_ingest.discard(audio)
    assert response.fusion.band == TrustBand.INSUFFICIENT
    assert response.transcript.text == "send money now"
    assert response.script.risk == 0.9


def test_a_quiet_tail_still_ends_on_the_final_transcript(branches, db_factory):
    rec = Recorder()
    transcriber = FakeTranscriber()

    async def scenario():
        runner = _runner(db_factory, [rec, ReportSink(db_factory)], transcriber)
        await runner.open(_open())
        pcm = np.concatenate([_speechy(10.0), _silence(9.0)])
        for frame in _frames(pcm, 2.0):
            await runner.push(frame)
        await runner.close(SessionClose(session_id=SID, reason="test"))

    asyncio.run(scenario())
    final = rec.events[-1]
    assert final.is_final and not final.response.quality.passed
    assert final.response.transcript.text.startswith("final"), "quiet tail dropped the transcript"


def test_the_final_rescore_of_the_last_window_is_not_counted_twice_for_persistence(
        branches, db_factory, monkeypatch):
    # N=2: one suspicious window must not confirm itself by being re-scored on close.
    monkeypatch.setattr(config, "ESCALATION_PERSISTENCE_N", 2)
    branches.plan = ["verified", "verified", "suspicious", "suspicious"]
    rec = Recorder()

    async def scenario():
        runner = _runner(db_factory, [rec])
        await runner.open(_open())
        for frame in _frames(_speechy(6.0), 1.0):
            await runner.push(frame)
        await runner.close(SessionClose(session_id=SID, reason="test"))

    asyncio.run(scenario())
    final = rec.events[-1]
    assert final.is_final and final.window_index == rec.events[-2].window_index
    assert not any(e.escalated for e in rec.events)
    assert final.response.fusion.band != TrustBand.SUSPICIOUS


def test_the_final_rescore_never_unlatches_a_confirmed_warning(branches, db_factory):
    # The re-score replaces the last window's persistence slot; if it comes back lower
    # (say the final transcript cleared it), the latched red must still stand.
    branches.plan = ["verified", "verified", "high_risk", "verified"]
    rec = Recorder()

    async def scenario():
        runner = _runner(db_factory, [rec])
        await runner.open(_open())
        for frame in _frames(_speechy(6.0), 1.0):
            await runner.push(frame)
        await runner.close(SessionClose(session_id=SID, reason="test"))

    asyncio.run(scenario())
    assert rec.events[-2].response.fusion.band == TrustBand.HIGH_RISK
    final = rec.events[-1]
    assert final.is_final and final.response.fusion.band == TrustBand.HIGH_RISK
    assert not final.escalated
