"""SatyaCheck — out-of-band transcript worker (item 4).

ASR is the slow branch: a 9 s window costs 5 to 15 s of Whisper on CPU int8. Gathered
with the speaker and anti-spoof branches in `screen_audio`, it set the latency of every
verdict. Here it runs beside the acoustic path instead of inside it:

  * `feed()` never blocks — it queues the new audio and returns;
  * one background task per session drains *everything* queued (in order, coalesced
    into one push) into nlp_rag's `StreamingTranscriber`, which owns when to decode;
  * after each push it runs `analyze_script` on the cumulative transcript and publishes
    a `TranscriptUpdate`; the runner fuses with `latest` whenever a window is ready.

Decoding runs on a single-thread executor shared by all sessions: Whisper calls are
never concurrent, so one long call cannot be starved into two slow ones.

Never raises into the caller (CLAUDE.md rule 5). A failed decode is logged and the
previous update stands; with no update yet, the runner scores text as unavailable.

C owns this file.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

import config
from contracts import ScriptAnalysisResult, TranscriptResult

log = logging.getLogger("satyacheck.pipeline.transcript")

_ASR_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="satyacheck-asr")


@dataclass(frozen=True)
class TranscriptUpdate:
    session_id: str
    upto_s: float                 # session time the transcript covers up to
    transcript: TranscriptResult
    script: ScriptAnalysisResult
    is_final: bool = False
    rev: int = 0                  # increases with every update this session publishes
    tentative: str = ""           # newest, uncommitted text (CommittingTranscriber); may change


def _default_transcriber():
    """Bounded, committing ASR (Phase 3); the whole-call re-decoder behind the flag."""
    if config.STREAM_COMMITTING_ASR:
        from nlp_rag.api import CommittingTranscriber

        return CommittingTranscriber()
    from nlp_rag.api import StreamingTranscriber

    return StreamingTranscriber()


def _default_analyze(transcript: TranscriptResult) -> ScriptAnalysisResult:
    from nlp_rag.api import analyze_script

    return analyze_script(transcript)


class TranscriptWorker:
    def __init__(self, session_id: str, transcriber=None,
                 analyze: Optional[Callable[[TranscriptResult], ScriptAnalysisResult]] = None,
                 sample_rate: int = config.TARGET_SAMPLE_RATE,
                 observer: Optional[Callable[["TranscriptUpdate"], None]] = None) -> None:
        self.session_id = session_id
        # Told of every published update (the LLM shadow). Must return at once: it runs on
        # the ASR thread. Its result is never read back.
        self._observer = observer
        self.transcriber = transcriber if transcriber is not None else _default_transcriber()
        self._analyze = analyze or _default_analyze
        self.sample_rate = sample_rate
        self.latest: Optional[TranscriptUpdate] = None
        self._rev = 0   # TranscriptUpdate.rev: counts published updates
        self._pending: list[np.ndarray] = []
        self._pending_upto = 0.0
        self._wake = asyncio.Event()
        self._idle = asyncio.Event()
        self._idle.set()
        self._closed = False
        self._fed_any = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"asr-{self.session_id}")

    def feed(self, pcm: np.ndarray, upto_s: float) -> None:
        """Queue new audio (float32, 16 kHz). Returns at once. Ignored after close()."""
        if self._closed:
            return
        self._pending.append(np.asarray(pcm, dtype=np.float32))
        self._fed_any = True
        self._pending_upto = upto_s
        self._idle.clear()
        self._wake.set()

    async def wait_idle(self) -> None:
        """Until everything fed so far has been pushed and analysed (tests, final flush)."""
        await self._idle.wait()

    async def close(self) -> Optional[TranscriptUpdate]:
        """Drain, flush the transcriber's tail, publish a final update, stop."""
        if self._closed:
            return self.latest
        await self.wait_idle()
        self._closed = True
        self._wake.set()
        if self._task is not None:
            await self._task
        if not self._fed_any:
            return None  # a session with no audio has nothing to transcribe
        loop = asyncio.get_running_loop()
        try:
            transcript = await loop.run_in_executor(_ASR_EXECUTOR, self.transcriber.flush)
            self._publish(transcript, self._pending_upto, is_final=True)
        except Exception as e:  # noqa: BLE001
            log.error(f"[{self.session_id}] final ASR flush failed: {type(e).__name__}: {e}")
        return self.latest

    # --- internals ----------------------------------------------------------------------------

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            await self._wake.wait()
            self._wake.clear()
            if not self._pending:
                self._idle.set()
                if self._closed:
                    return
                continue
            chunk = np.concatenate(self._pending)
            upto = self._pending_upto
            self._pending = []
            try:
                transcript = await loop.run_in_executor(_ASR_EXECUTOR, self._decode, chunk)
                await loop.run_in_executor(_ASR_EXECUTOR, self._publish, transcript, upto)
            except Exception as e:  # noqa: BLE001 — keep the previous update, keep going
                log.error(f"[{self.session_id}] ASR push failed at {upto:.1f}s: {type(e).__name__}: {e}")
            if self._pending:
                self._wake.set()
            else:
                self._idle.set()
                if self._closed:
                    return

    def _decode(self, chunk: np.ndarray) -> TranscriptResult:
        from server.capacity import inference_slot

        with inference_slot("asr"):
            return self.transcriber.push(chunk, self.sample_rate)

    def _publish(self, transcript: TranscriptResult, upto_s: float, is_final: bool = False) -> None:
        script = self._analyze(transcript)
        self._rev += 1
        tentative = str(getattr(self.transcriber, "tentative_text", "") or "")
        self.latest = TranscriptUpdate(self.session_id, upto_s, transcript, script, is_final,
                                       rev=self._rev, tentative=tentative)
        if self._observer is not None:
            try:
                self._observer(self.latest)
            except Exception as e:  # noqa: BLE001 — an observer never affects transcription
                log.error(f"[{self.session_id}] transcript observer failed: {type(e).__name__}: {e}")
