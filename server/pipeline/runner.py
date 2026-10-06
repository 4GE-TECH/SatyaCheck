"""SatyaCheck — session runner (item 5).

The one seam every audio source feeds: `open(SessionOpen)`, `push(AudioFrame)`,
`close(SessionClose)`. Per session it owns

  * a `SessionBuffer` — frames of any size in, a window every `STREAM_HOP_S` out;
  * a `TranscriptWorker` — fed every frame's new audio as it arrives, decoding beside
    the acoustic path, never in front of it;
  * an `EscalationGate` — persistence then latch, per session;
  * a `Dispatcher` — overlay, guardian, report, bank stub.

For each window: `ingest_pcm` (quality gate, temp WAV) -> `orchestrator.screen_window`
(speaker + anti-spoof, fused with whatever transcript the worker has published *now*,
or text abstaining when there is none) -> escalation -> dispatch -> discard the WAV.
The acoustic verdict never waits for ASR.

On close: the buffer's tail is flushed, the worker closed (its final transcript is
the cumulative one), and exactly one dispatched event carries `is_final=True` — the
tail scored with the final transcript, or, with no tail, the last window re-scored
with it. A session with no audio at all still ends on one final `insufficient`
verdict, so the report row and `status='complete'` are always written.

Never raises (CLAUDE.md rule 5). Every degradation is logged with the session id.

C owns this file.
"""

from __future__ import annotations

import asyncio
import time
import copy
import dataclasses
import logging
from typing import Awaitable, Callable, Optional

import numpy as np

import config
from contracts import AudioFrame, ScreeningResponse, SessionClose, SessionOpen
from server import orchestrator
from server.audio_ingest import discard, ingest_pcm
from server.escalation import _WARNING_RANK, EscalationGate
from server.pipeline.buffer import SessionBuffer, Window
from server.pipeline.dispatcher import Dispatcher, VerdictEvent, build_dispatcher
from server.pipeline.transcript_worker import TranscriptUpdate, TranscriptWorker

log = logging.getLogger("satyacheck.pipeline.runner")


def _rank(band) -> int:
    return _WARNING_RANK.get(band, 0) if band is not None else 0


@dataclasses.dataclass
class _Session:
    open: SessionOpen
    buffer: SessionBuffer
    worker: Optional[TranscriptWorker]
    gate: EscalationGate
    lock: asyncio.Lock
    last_window: Optional[Window] = None
    # The gate as it stood before `last_window` was applied. The close-time re-score of
    # that window replaces its persistence slot instead of taking a second one.
    gate_before_last: Optional[EscalationGate] = None
    last_shown: Optional[tuple] = None  # (band, trust) of the last dispatched event
    finished: bool = False
    silence_warned: bool = False
    # Backlog handling (push(score=False)): the newest window not yet scored, and how many
    # older ones were passed over to keep the verdict current.
    deferred: Optional[Window] = None
    deferred_count: int = 0


class SessionRunner:
    """Runs any number of sessions, keyed by `session_id`. One event loop."""

    def __init__(
        self,
        dispatcher: Optional[Dispatcher] = None,
        session_factory: Optional[Callable] = None,
        transcriber_factory: Optional[Callable[[], object]] = None,
        analyze: Optional[Callable] = None,
        observer: Optional[Callable[[VerdictEvent, float], None]] = None,
    ) -> None:
        if session_factory is None:
            from server.database import SessionLocal
            session_factory = SessionLocal
        self.session_factory = session_factory
        self.dispatcher = dispatcher if dispatcher is not None else build_dispatcher(
            session_factory=session_factory)
        self.transcriber_factory = transcriber_factory
        self.analyze = analyze
        # Measurement hook (item 14): called with each dispatched event and the seconds
        # since the frame (or close) that produced it arrived. Never changes scoring.
        self.observer = observer
        self._sessions: dict[str, _Session] = {}

    # --- observability ---------------------------------------------------------------

    def _observe(self, events, started: float) -> None:
        if self.observer is None:
            return
        elapsed = time.monotonic() - started
        for event in events:
            if event is None:
                continue
            try:
                self.observer(event, elapsed)
            except Exception as e:  # noqa: BLE001 — measurement must never break a call
                log.warning(f"[{event.session_id}] runner observer failed: {type(e).__name__}: {e}")

    def worker(self, session_id: str) -> Optional[TranscriptWorker]:
        s = self._sessions.get(session_id)
        return s.worker if s else None

    # --- the seam --------------------------------------------------------------------

    async def open(self, msg: SessionOpen) -> None:
        """Start a session. Re-opening a live id is logged and ignored. Never raises."""
        sid = msg.session_id
        try:
            if sid in self._sessions:
                log.warning(f"[{sid}] open for a session that is already running; ignored")
                return
            worker = None
            try:
                transcriber = self.transcriber_factory() if self.transcriber_factory else None
                worker = TranscriptWorker(sid, transcriber=transcriber, analyze=self.analyze)
                await worker.start()
            except Exception as e:  # noqa: BLE001 — no ASR: score acoustics, text abstains
                log.error(f"[{sid}] transcript worker failed to start, text will abstain "
                          f"for this session: {type(e).__name__}: {e}")
                worker = None
            self._sessions[sid] = _Session(
                open=msg,
                buffer=SessionBuffer(sid),
                worker=worker,
                gate=EscalationGate(max(1, int(config.ESCALATION_PERSISTENCE_N))),
                lock=asyncio.Lock(),
            )
            await asyncio.to_thread(self._write_session_row, msg)
            log.info(f"[{sid}] session opened (source={msg.source.value})")
        except Exception as e:  # noqa: BLE001
            log.error(f"[{sid}] open failed: {type(e).__name__}: {e}")

    async def push(self, frame: AudioFrame, score: bool = True) -> list[VerdictEvent]:
        """Add a frame; score and dispatch every window it completed. Returns the events.

        `score=False` buffers the audio and feeds ASR without scoring: a transport that is
        behind real time pushes its backlog that way, then the newest frame with
        `score=True`, which scores the newest window and logs how many it passed over.
        A frame with `is_final=True` ends the session (as `close` would). Never raises.
        """
        sid = frame.session_id
        started = time.monotonic()
        s = self._sessions.get(sid)
        if s is None:
            log.warning(f"[{sid}] dropped frame seq={frame.seq}: session not open")
            return []
        async with s.lock:
            if s.finished:
                log.warning(f"[{sid}] dropped frame seq={frame.seq}: session already closed")
                return []
            try:
                before = self._received(s)
                windows = s.buffer.push(frame)
                self._feed_worker(s, frame, before)
                events = []
                regular = [w for w in windows if not w.is_final]
                tail = [w for w in windows if w.is_final]
                if not score and not frame.is_final:
                    if regular:
                        s.deferred = regular[-1]
                        s.deferred_count += len(regular)
                    return []
                if s.deferred is not None:
                    if not regular:
                        regular = [s.deferred]
                        s.deferred_count -= 1
                    if s.deferred_count:
                        log.info(f"[{sid}] scoring behind real time: scored the newest window, "
                                 f"skipped {s.deferred_count} older one(s)")
                    s.deferred, s.deferred_count = None, 0
                for window in regular:
                    events.append(await self._score(s, window, final=False))
                if frame.is_final:
                    events.extend(await self._finish(s, tail, reason="final frame"))
                    self._sessions.pop(sid, None)  # a later close() is a no-op
                events = [e for e in events if e is not None]
                self._observe(events, started)
                return events
            except Exception as e:  # noqa: BLE001
                log.error(f"[{sid}] push failed on seq={frame.seq}: {type(e).__name__}: {e}")
                return []

    async def close(self, msg: SessionClose) -> list[VerdictEvent]:
        """End a session: score the tail, flush ASR, emit the one final event. Never raises.
        Closing a closed or unknown session is a logged no-op."""
        sid = msg.session_id
        started = time.monotonic()
        s = self._sessions.get(sid)
        if s is None:
            log.debug(f"[{sid}] close ({msg.reason}) for a session not running; nothing to do")
            return []
        try:
            async with s.lock:
                if s.finished:
                    return []
                events = [e for e in await self._finish(s, [], reason=msg.reason) if e is not None]
                self._observe(events, started)
                return events
        except Exception as e:  # noqa: BLE001
            log.error(f"[{sid}] close failed: {type(e).__name__}: {e}")
            return []
        finally:
            self._sessions.pop(sid, None)

    # --- internals ---------------------------------------------------------------------

    def _write_session_row(self, msg: SessionOpen) -> None:
        try:
            from server.database import ScreeningSession

            with self.session_factory() as db:
                row = db.get(ScreeningSession, msg.session_id)
                if row is None:
                    db.add(ScreeningSession(session_id=msg.session_id, status="streaming",
                                            channel_type=msg.source.value))
                else:
                    row.status = "streaming"
                db.commit()
        except Exception as e:  # noqa: BLE001 — the call is still screened, just not stored
            log.error(f"[{msg.session_id}] could not write the session row; the report for "
                      f"this call will be missing: {type(e).__name__}: {e}")

    @staticmethod
    def _received(s: _Session) -> int:
        return int(round(s.buffer.total_s * s.buffer.sample_rate))

    def _feed_worker(self, s: _Session, frame: AudioFrame, before: int) -> None:
        """Give ASR exactly the samples the buffer accepted (none for a dropped frame)."""
        if s.worker is None:
            return
        try:
            accepted = self._received(s) - before
            if accepted <= 0:
                return
            pcm = np.frombuffer(frame.pcm_s16le, dtype="<i2")[:accepted].astype(np.float32) / 32768.0
            s.worker.feed(pcm, upto_s=frame.t_start_s + accepted / s.buffer.sample_rate)
        except Exception as e:  # noqa: BLE001
            log.error(f"[{s.open.session_id}] could not feed ASR seq={frame.seq}; text may lag: "
                      f"{type(e).__name__}: {e}")

    def _text(self, update: Optional[TranscriptUpdate]):
        if update is None:
            return None, None
        return update.transcript, update.script

    async def _score(self, s: _Session, window: Window, final: bool,
                     update: Optional[TranscriptUpdate] = None,
                     rescore: bool = False) -> Optional[VerdictEvent]:
        sid = s.open.session_id
        if update is None and s.worker is not None:
            update = s.worker.latest  # whatever exists now; never awaited
        transcript, script = self._text(update)
        self._check_silence(s, window)
        ingested = None
        try:
            ingested = await asyncio.to_thread(ingest_pcm, window.pcm)
            if ingested.error:
                log.warning(f"[{sid}] window {window.index} ingest degraded: {ingested.error}")
            response = await orchestrator.screen_window(
                ingested, transcript, script,
                caller_metadata=s.open.caller_context, session_id=sid)
        except Exception as e:  # noqa: BLE001
            log.error(f"[{sid}] window {window.index} could not be scored: {type(e).__name__}: {e}")
            return None
        finally:
            if ingested is not None:
                discard(ingested)

        s.last_window = window
        return await self._emit(s, window.index, response, final, rescore=rescore)

    @staticmethod
    def _check_silence(s: _Session, window: Window) -> None:
        """Warn once per session when a whole hop of audio is exactly zero.

        A source that opens and delivers full buffers of digital silence passes every
        sample-count check — this is what Android hands any app recording beside a live
        call (CLAUDE.md, "Call audio cannot be captured..."). Real microphones never read
        exactly 0 for seconds. The window is still scored (the quality gate will call it
        insufficient); this log is how someone later tells silence from no audio.
        """
        try:
            if s.silence_warned or window.pcm.size == 0:
                return
            if window.end_s - window.start_s < s.buffer.hop_s - 1e-9:
                return  # a short tail is not sustained silence
            if float(np.max(np.abs(window.pcm))) != 0.0:
                return
            s.silence_warned = True
            log.warning(
                f"[{s.open.session_id}] stream silent: window {window.index} "
                f"({window.start_s:.2f}-{window.end_s:.2f}s, source={s.open.source.value}) "
                f"is digital zero — the source is delivering silence, not audio. Check the "
                f"capture path (a phone in a call hands other apps zeros); still scoring")
        except Exception as e:  # noqa: BLE001
            log.debug(f"[{s.open.session_id}] silence check failed: {type(e).__name__}: {e}")

    async def _emit(self, s: _Session, index: int, response: ScreeningResponse,
                    final: bool, rescore: bool = False) -> Optional[VerdictEvent]:
        sid = s.open.session_id
        try:
            # The session's caller context rides on every verdict it dispatches (the
            # report, guardian and overlay read it from the response). Set here, after
            # scoring, so it cannot be an input to fusion (FR-17).
            context = s.open.caller_context
            if context is None:
                context = response.caller_context
            response = response.model_copy(update={"session_id": sid,
                                                   "caller_context": context})
            before = _rank(s.gate.latched_band)
            window_view = (response.fusion.trust_score, response.fusion.band.value)
            if rescore and s.gate_before_last is not None and s.last_shown is not None:
                # Same audio as the window just applied: it supersedes that window's
                # verdict in the persistence run rather than counting as one more, so
                # one suspicious window cannot confirm itself (ESCALATION_PERSISTENCE_N).
                current = s.gate
                s.gate = copy.deepcopy(s.gate_before_last)
                gated = s.gate.apply(response)
                if _rank(s.gate.latched_band) < before:
                    # The latch never improves within a session: keep what was shown.
                    s.gate = current
                    band, trust = s.last_shown
                    gated = response.model_copy(update={"fusion": response.fusion.model_copy(
                        update={"band": band, "trust_score": trust})})
                response = gated
            else:
                s.gate_before_last = copy.deepcopy(s.gate)
                response = s.gate.apply(response)
            s.last_shown = (response.fusion.band, response.fusion.trust_score)
            escalated = _rank(s.gate.latched_band) > before
            if final:
                s.finished = True
            event = VerdictEvent(session_id=sid, response=response, window_index=index,
                                 escalated=escalated, is_final=final,
                                 window_trust_score=window_view[0], window_band=window_view[1])
            outcome = await self.dispatcher.dispatch(event)
            failed = [name for name, ok in outcome.items() if not ok]
            if failed:
                log.warning(f"[{sid}] window {index}: not delivered to {failed}")
            return event
        except Exception as e:  # noqa: BLE001
            log.error(f"[{sid}] window {index} could not be dispatched: {type(e).__name__}: {e}")
            return None

    async def _finish(self, s: _Session, tail: list[Window], reason: str) -> list[Optional[VerdictEvent]]:
        sid = s.open.session_id
        tail = list(tail) + s.buffer.flush()
        final_update: Optional[TranscriptUpdate] = None
        if s.worker is not None:
            try:
                final_update = await s.worker.close()
            except Exception as e:  # noqa: BLE001
                log.error(f"[{sid}] ASR close failed; final verdict uses the last transcript: "
                          f"{type(e).__name__}: {e}")
                final_update = s.worker.latest
        events: list[Optional[VerdictEvent]] = []
        for k, window in enumerate(tail):
            # Only the last tail window is final; the buffer may hand over more than one.
            events.append(await self._score(s, window, final=k == len(tail) - 1,
                                            update=final_update))
        if not tail:
            if s.last_window is not None:
                # The last hop window already ended at the end of the audio: re-score
                # it with the final transcript rather than invent an empty tail.
                events.append(await self._score(s, s.last_window, final=True, update=final_update,
                                                rescore=True))
            else:
                log.info(f"[{sid}] session closed with no audio ({reason}); final verdict "
                         f"is insufficient")
                events.append(await self._score(
                    s, Window(sid, 0, 0.0, 0.0, np.zeros(0, dtype=np.float32), "", True),
                    final=True, update=final_update))
        if not s.finished:
            # Scoring the final window failed outright: still close the session.
            log.error(f"[{sid}] no final verdict could be produced ({reason})")
            s.finished = True
        log.info(f"[{sid}] session finished ({reason})")
        return events


if __name__ == "__main__":
    # Smoke test: 7 s of tone through mock branches and a fake transcriber, printed sink.
    from contracts import AudioSource, TranscriptResult

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    class _Print:
        name = "print"

        async def deliver(self, event: VerdictEvent) -> None:
            f = event.response.fusion
            print(f"  window {event.window_index}: band={f.band.value} trust={f.trust_score} "
                  f"escalated={event.escalated} final={event.is_final}")

    class _Echo:
        def push(self, chunk, sample_rate=16000):
            return TranscriptResult(text="hello", detected_language="en", confidence=0.9)

        def flush(self):
            return TranscriptResult(text="hello, final", detected_language="en", confidence=0.9)

    async def _smoke() -> None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from server.database import Base

        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        # Mock branches: the mock spoof branch abstains, so a window scored before the
        # first transcript fuses on identity alone (unknown, 0.5) and reads suspicious.
        config.USE_REAL_SPEAKER = config.USE_REAL_SPOOF = False
        runner = SessionRunner(dispatcher=Dispatcher([_Print()]),
                               session_factory=sessionmaker(bind=engine),
                               transcriber_factory=_Echo,
                               analyze=lambda t: orchestrator.ScriptAnalysisResult.neutral())
        await runner.open(SessionOpen(session_id="smoke", source=AudioSource.UPLOAD))
        t = np.arange(7 * 16000) / 16000
        pcm = (0.3 * np.sin(2 * np.pi * 220 * t) * ((t % 0.5) < 0.4) * 32767).astype("<i2")
        for i in range(7):
            await runner.push(AudioFrame(session_id="smoke", seq=i, t_start_s=float(i),
                                         pcm_s16le=pcm[i * 16000:(i + 1) * 16000].tobytes()))
        events = await runner.close(SessionClose(session_id="smoke", reason="smoke"))
        assert len(events) == 1 and events[0].is_final, events
        print("[OK] runner smoke test passed")

    asyncio.run(_smoke())
