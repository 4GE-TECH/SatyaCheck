"""SatyaCheck — per-session rolling buffer (item 3).

Frames of any size go in (`contracts.AudioFrame`, 16 kHz mono s16le); a `Window` comes
out every `config.STREAM_HOP_S` seconds of audio, holding the trailing
`config.STREAM_CONTEXT_S` seconds — less at the very start of a call.

Why windows and not chunks: Whisper hallucinates on isolated 3 s slices (see
config.STREAM_CONTEXT_S), and how often a call is re-scored should not depend on how
big a particular client's chunks happen to be. Windows end on hop boundaries, so a 30 s
upload and a stream of 0.5 s frames of the same audio yield the same windows.

Never raises (CLAUDE.md rule 5): malformed, foreign or out-of-order frames are dropped
and logged, because a silently absorbed bad frame is indistinguishable from audio that
was scored.

C owns this file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

import config
from contracts import AudioFrame

log = logging.getLogger("satyacheck.pipeline.buffer")


@dataclass(frozen=True)
class Window:
    """One scoring window. `pcm` is float32 in [-1, 1) at `config.TARGET_SAMPLE_RATE`."""
    session_id: str
    index: int
    start_s: float
    end_s: float
    pcm: np.ndarray
    sha256: str
    is_final: bool = False


class SessionBuffer:
    """Rolling audio for one session. Not thread-safe; one per session."""

    def __init__(
        self,
        session_id: str,
        window_s: Optional[float] = None,
        hop_s: Optional[float] = None,
        max_session_s: Optional[float] = None,
        sample_rate: int = config.TARGET_SAMPLE_RATE,
    ) -> None:
        self.session_id = session_id
        self.window_s = config.STREAM_CONTEXT_S if window_s is None else window_s
        self.hop_s = config.STREAM_HOP_S if hop_s is None else hop_s
        self.max_session_s = config.STREAM_MAX_SESSION_S if max_session_s is None else max_session_s
        self.sample_rate = sample_rate

        self._window = int(round(self.window_s * sample_rate))
        self._hop = int(round(self.hop_s * sample_rate))
        self._cap = int(round(self.max_session_s * sample_rate))
        self._samples = np.zeros(0, dtype=np.float32)
        self._offset = 0          # session sample index of self._samples[0]
        self._total = 0           # session sample index of the end of the audio
        self._received = 0        # samples received (less than _total after a gap)
        self._next_end = self._hop
        self._last_end = 0        # end sample of the last emitted window
        self._index = 0
        self._next_seq = 0
        self._capped = False
        self._floor = 0           # windows never reach back past a sequence gap

    # --- observability ------------------------------------------------------------

    @property
    def total_s(self) -> float:
        """Seconds of audio received; lost frames are not counted."""
        return self._received / self.sample_rate

    @property
    def retained_samples(self) -> int:
        return len(self._samples)

    # --- input ----------------------------------------------------------------------

    def push(self, frame: AudioFrame) -> list[Window]:
        """Add a frame; return every window it completed (often none). Never raises."""
        try:
            gap = frame.seq > self._next_seq
            if not self._accept(frame):
                return []
            windows = self._jump(frame) if gap else []
            data = np.frombuffer(frame.pcm_s16le, dtype="<i2").astype(np.float32) / 32768.0
            room = max(0, self._cap - self._total)
            if len(data) > room:
                data = data[:room]
                if not self._capped:
                    self._capped = True
                    log.warning(
                        f"[{self.session_id}] reached STREAM_MAX_SESSION_S "
                        f"({self.max_session_s:.0f}s); later audio is not scored"
                    )
            self._samples = np.concatenate([self._samples, data])
            self._total += len(data)
            self._received += len(data)

            while self._next_end <= self._total:
                windows.append(self._emit(self._next_end))
                self._next_end += self._hop
            if frame.is_final:
                windows = self._finish(windows)
            self._trim()
            return windows
        except Exception as e:  # noqa: BLE001 — a broken frame must not end the call
            log.error(f"[{self.session_id}] buffer push failed: {type(e).__name__}: {e}")
            return []

    def flush(self) -> list[Window]:
        """End of session: score the tail since the last window, if any. Never raises."""
        try:
            return self._finish([])
        except Exception as e:  # noqa: BLE001
            log.error(f"[{self.session_id}] buffer flush failed: {type(e).__name__}: {e}")
            return []

    # --- internals ---------------------------------------------------------------------

    def _accept(self, frame: AudioFrame) -> bool:
        if frame.session_id != self.session_id:
            log.warning(f"[{self.session_id}] dropped a frame for session {frame.session_id!r}")
            return False
        if len(frame.pcm_s16le) % 2:
            log.warning(f"[{self.session_id}] dropped frame seq={frame.seq}: odd byte count, not s16le")
            return False
        if frame.seq < self._next_seq:
            log.warning(
                f"[{self.session_id}] dropped out of order frame seq={frame.seq} "
                f"(expected {self._next_seq})"
            )
            return False
        if frame.seq > self._next_seq:
            log.warning(
                f"[{self.session_id}] sequence gap: expected seq={self._next_seq}, got "
                f"{frame.seq}; {frame.seq - self._next_seq} frame(s) missing"
            )
        self._next_seq = frame.seq + 1
        return not self._capped

    def _jump(self, frame: AudioFrame) -> list[Window]:
        """After lost frames, resume at the frame's real session time.

        Without this, the audio either side of the gap is spliced together and every
        later window is labelled earlier than it happened by the gap's length, so spoof
        timelines and reason-code citations point at the wrong part of the call. The
        tail received before the gap is scored first so it is not silently lost.
        """
        start = int(round(frame.t_start_s * self.sample_rate))
        if start <= self._total:
            log.warning(
                f"[{self.session_id}] frame seq={frame.seq} after a gap has t_start_s="
                f"{frame.t_start_s:.3f}s, not past the {self._total / self.sample_rate:.3f}s already buffered; "
                f"window times after it are by sample count"
            )
            return []
        windows = [self._emit(self._total)] if self._total > self._last_end else []
        self._samples = np.zeros(0, dtype=np.float32)
        self._offset = self._total = self._last_end = self._floor = start
        self._next_end = (start // self._hop + 1) * self._hop
        return windows

    def _emit(self, end: int, final: bool = False) -> Window:
        start = max(self._floor, end - self._window)
        pcm = self._samples[start - self._offset:end - self._offset].copy()
        window = Window(
            session_id=self.session_id,
            index=self._index,
            start_s=start / self.sample_rate,
            end_s=end / self.sample_rate,
            pcm=pcm,
            sha256=hashlib.sha256(pcm.tobytes()).hexdigest(),
            is_final=final,
        )
        self._index += 1
        self._last_end = end
        return window

    def _finish(self, windows: list[Window]) -> list[Window]:
        if self._total > self._last_end:
            windows.append(self._emit(self._total, final=True))
        elif windows:
            # The last hop window already ends at the end of the audio: mark it final
            # rather than scoring the same samples twice.
            windows[-1] = dataclasses.replace(windows[-1], is_final=True)
        return windows

    def _trim(self) -> None:
        """Keep only what the next window can still need: the trailing `window_s`."""
        keep_from = max(0, self._total - self._window)
        drop = keep_from - self._offset
        if drop > 0:
            self._samples = self._samples[drop:]
            self._offset = keep_from
