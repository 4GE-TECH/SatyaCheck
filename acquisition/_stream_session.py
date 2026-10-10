"""The reader/consumer split every live transport uses (Exotel, WebRTC).

Reading never waits for scoring. Seen live on Exotel: when scoring ran slower than real
time, the unread audio backed up in the socket and was discarded at hang-up, so the end of
the call was never heard. The transport puts every decoded item here as it arrives; the
consumer scores the newest frame of each batch and hands the backlog to the runner
unscored (the runner's catch-up queue decides what is caught up or reported as a gap).

`runner` is anything with async open(SessionOpen) / push(AudioFrame, score=bool) /
close(SessionClose). acquisition/ never imports server/ (CLAUDE.md boundaries).
"""

from __future__ import annotations

import asyncio
import logging

from contracts import AudioFrame, SessionClose, SessionOpen

log = logging.getLogger("satyacheck.acquisition.stream")


class StreamSession:
    """One call's queue and consumer task. `put` never blocks; `finish` drains, then stops."""

    _DONE = object()

    def __init__(self, runner, label: str) -> None:
        self.runner = runner
        self.label = label
        self.queue: asyncio.Queue = asyncio.Queue()
        self._task = asyncio.create_task(self._consume())

    def put(self, item) -> None:
        self.queue.put_nowait(item)

    async def _consume(self) -> None:
        while True:
            batch = [await self.queue.get()]
            while not self.queue.empty():
                batch.append(self.queue.get_nowait())
            last_frame = max((i for i, it in enumerate(batch) if isinstance(it, AudioFrame)), default=-1)
            for i, item in enumerate(batch):
                try:
                    if item is self._DONE:
                        return
                    if isinstance(item, SessionOpen):
                        await self.runner.open(item)
                    elif isinstance(item, AudioFrame):
                        await self.runner.push(item, score=(i == last_frame))
                    elif isinstance(item, SessionClose):
                        await self.runner.close(item)
                except Exception as e:  # noqa: BLE001 — keep consuming; log why
                    log.error(f"{self.label}: scoring step failed: {type(e).__name__}: {e}")

    async def finish(self) -> None:
        """Score what is still queued, then stop. Never raises."""
        backlog = self.queue.qsize()
        if backlog > 1:
            log.info(f"{self.label}: call ended with {backlog} item(s) still to score; finishing them")
        self.queue.put_nowait(self._DONE)
        try:
            await self._task
        except Exception as e:  # noqa: BLE001
            log.error(f"{self.label}: finishing the session failed: {e}")
