"""Item 4: ASR runs out of band — acoustic and identity verdicts never wait for Whisper.

Measured on the demo laptop: a 9 s window costs 5 to 15 s of Whisper on CPU int8. In
`screen_audio` all three branches are gathered, so the slowest — ASR — sets the latency
of every verdict, including the speaker and anti-spoof results that were ready in well
under a second.

`TranscriptWorker` takes ASR off that path. `feed()` returns immediately; a background
task pushes the audio, in order and coalesced, into nlp_rag's StreamingTranscriber
(which owns *when* to decode) and publishes the latest transcript and script analysis.
The runner fuses with whatever is newest when a window is ready.

The transcriber here is a fake that records what it was given and sleeps, so these test
cadence and ordering — the properties that matter — rather than Whisper's output.
"""

from __future__ import annotations

import asyncio
import logging
import time

import numpy as np
import pytest

from contracts import ScriptAnalysisResult, TranscriptResult
from server.pipeline.transcript_worker import TranscriptUpdate, TranscriptWorker

SR = 16_000


class SlowTranscriber:
    """StreamingTranscriber's interface: push(chunk, sample_rate) and flush()."""

    def __init__(self, delay=0.3, fail_on=None):
        self.delay, self.fail_on = delay, fail_on
        self.pushed: list[np.ndarray] = []
        self.calls = 0
        self.flushed = False

    def _result(self):
        seconds = sum(len(c) for c in self.pushed) / SR
        return TranscriptResult(text=f"heard {seconds:.1f}s", detected_language="en", confidence=0.9)

    def push(self, chunk, sample_rate=SR):
        self.calls += 1
        if self.fail_on is not None and self.calls == self.fail_on:
            raise RuntimeError("decoder crashed")
        time.sleep(self.delay)
        self.pushed.append(np.asarray(chunk))
        return self._result()

    def flush(self):
        self.flushed = True
        return self._result()


def _analyze(transcript):
    return ScriptAnalysisResult(risk=0.42, details={"available": True, "text": transcript.text})


def _chunk(seconds, value):
    return np.full(int(seconds * SR), value, dtype=np.float32)


def _worker(transcriber, **kw):
    return TranscriptWorker("s1", transcriber=transcriber, analyze=_analyze, **kw)


def test_feed_returns_immediately_while_asr_is_slow():
    async def scenario():
        worker = _worker(SlowTranscriber(delay=1.0))
        await worker.start()
        started = time.perf_counter()
        worker.feed(_chunk(3.0, 0.1), upto_s=3.0)
        fed_in = time.perf_counter() - started
        assert worker.latest is None, "nothing decoded yet"
        await worker.close()
        return fed_in

    assert asyncio.run(scenario()) < 0.05


def test_an_update_is_published_once_decoded():
    async def scenario():
        worker = _worker(SlowTranscriber(delay=0.05))
        await worker.start()
        worker.feed(_chunk(3.0, 0.1), upto_s=3.0)
        await worker.wait_idle()
        latest = worker.latest
        await worker.close()
        return latest

    latest = asyncio.run(scenario())
    assert isinstance(latest, TranscriptUpdate)
    assert latest.upto_s == 3.0
    assert latest.transcript.text == "heard 3.0s"
    assert latest.script.risk == 0.42


def test_audio_fed_during_a_slow_decode_is_coalesced_not_dropped():
    async def scenario():
        transcriber = SlowTranscriber(delay=0.3)
        worker = _worker(transcriber)
        await worker.start()
        for i in range(6):
            worker.feed(_chunk(1.0, float(i)), upto_s=float(i + 1))
            await asyncio.sleep(0.02)
        await worker.wait_idle()
        await worker.close()
        return transcriber, worker.latest

    transcriber, latest = asyncio.run(scenario())
    assert transcriber.calls < 6, "six pushes would mean no coalescing"
    audio = np.concatenate(transcriber.pushed)
    assert len(audio) == 6 * SR, "every sample must reach the transcriber"
    assert np.array_equal(audio[::SR], np.arange(6, dtype=np.float32)), "in order"
    assert latest.upto_s == 6.0


def test_close_flushes_the_tail_and_publishes_a_final_update():
    async def scenario():
        transcriber = SlowTranscriber(delay=0.01)
        worker = _worker(transcriber)
        await worker.start()
        worker.feed(_chunk(2.0, 0.1), upto_s=2.0)
        final = await worker.close()
        return transcriber, final

    transcriber, final = asyncio.run(scenario())
    assert transcriber.flushed
    assert final is not None and final.is_final and final.upto_s == 2.0


def test_a_decoder_failure_is_logged_and_the_worker_keeps_going(caplog):
    async def scenario():
        worker = _worker(SlowTranscriber(delay=0.01, fail_on=1))
        await worker.start()
        worker.feed(_chunk(1.0, 0.1), upto_s=1.0)
        await worker.wait_idle()
        first = worker.latest
        worker.feed(_chunk(1.0, 0.2), upto_s=2.0)
        await worker.wait_idle()
        second = worker.latest
        await worker.close()
        return first, second

    with caplog.at_level(logging.ERROR, logger="satyacheck.pipeline.transcript"):
        first, second = asyncio.run(scenario())
    assert first is None
    assert second is not None and second.upto_s == 2.0
    assert any("decoder crashed" in r.getMessage() for r in caplog.records)


def test_feed_after_close_is_ignored():
    async def scenario():
        worker = _worker(SlowTranscriber(delay=0.0))
        await worker.start()
        await worker.close()
        worker.feed(_chunk(1.0, 0.1), upto_s=1.0)
        return worker.latest

    assert asyncio.run(scenario()) is None


def test_the_default_transcriber_is_nlp_rags_streaming_transcriber():
    from nlp_rag.api import StreamingTranscriber

    worker = TranscriptWorker("s1")
    assert isinstance(worker.transcriber, StreamingTranscriber)


import config  # noqa: E402

_WHISPER = config.MODELS_DIR / f"faster-whisper-{config.WHISPER_MODEL_SIZE}"
_CLIP = config.REPO_ROOT / "data" / "eval_set" / "clips" / "held-digital-arrest-004.wav"


@pytest.mark.skipif(not _WHISPER.is_dir() or not _CLIP.is_file(), reason="needs Whisper and the clip")
def test_real_asr_over_streamed_chunks_produces_a_scored_transcript():
    from server.audio_ingest import ingest_audio

    audio = np.asarray(ingest_audio(audio_path=str(_CLIP)).waveform, dtype=np.float32)

    async def scenario():
        worker = TranscriptWorker("real")
        await worker.start()
        step = 3 * SR
        for start in range(0, len(audio), step):
            worker.feed(audio[start:start + step], upto_s=min(len(audio), start + step) / SR)
        return await worker.close()

    from nlp_rag import thresholds
    from nlp_rag.api import analyze_script, transcribe

    final = asyncio.run(scenario())
    assert final is not None and final.is_final
    assert len(final.transcript.text) > 40, final.transcript.text
    assert final.script.details.get("available") is True
    # Streaming 3 s chunks out of band must lose nothing against scoring the whole file.
    whole = analyze_script(transcribe(str(_CLIP)))
    assert final.transcript.text == transcribe(str(_CLIP)).text
    assert final.script.risk == pytest.approx(whole.risk, abs=1e-6)
    assert final.script.risk >= thresholds.AMBER_FLOOR
