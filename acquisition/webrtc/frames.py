"""LiveKit audio -> contracts.AudioFrame, on one continuing timeline per voice.

The agent asks LiveKit for 16 kHz mono (`rtc.AudioStream(track, sample_rate=16000,
num_channels=1)`), so no resampling happens here: LiveKit hands over 10 ms int16 buffers
and this joins them into FRAME_S frames, the size every other transport sends.

Pure (no LiveKit import), so it is tested without a server.

    python -m acquisition.webrtc.frames     # smoke test
"""

from __future__ import annotations

from typing import Optional

from contracts import AudioFrame

RATE = 16000
FRAME_S = 0.5
_FRAME_BYTES = int(RATE * FRAME_S) * 2


class FrameAssembler:
    """Collects int16 PCM and emits FRAME_S AudioFrames with increasing seq and t_start_s.

    A reconnect of the same voice keeps the same assembler, so its timeline and seq
    continue: the runner sees one session, not two.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._pending = bytearray()
        self._seq = 0
        self._samples = 0          # samples already emitted

    @property
    def seconds(self) -> float:
        return self._samples / RATE

    def feed(self, pcm_s16le: bytes) -> list[AudioFrame]:
        """Add PCM; return every whole frame it completed. Odd trailing bytes wait."""
        self._pending.extend(pcm_s16le)
        out = []
        while len(self._pending) >= _FRAME_BYTES:
            chunk = bytes(self._pending[:_FRAME_BYTES])
            del self._pending[:_FRAME_BYTES]
            out.append(self._frame(chunk, final=False))
        return out

    def flush(self, final: bool = True) -> Optional[AudioFrame]:
        """The partial tail as a last frame (even-length), or a bare final marker."""
        tail = bytes(self._pending[: len(self._pending) // 2 * 2])
        self._pending.clear()
        if not tail and not final:
            return None
        return self._frame(tail, final=final)

    def _frame(self, chunk: bytes, final: bool) -> AudioFrame:
        frame = AudioFrame(session_id=self.session_id, seq=self._seq, t_start_s=self._samples / RATE,
                           pcm_s16le=chunk, is_final=final)
        self._seq += 1
        self._samples += len(chunk) // 2
        return frame


if __name__ == "__main__":
    a = FrameAssembler("smoke")
    frames = [f for _ in range(120) for f in a.feed(b"\x00\x01" * 160)]   # 120 x 10 ms
    tail = a.flush()
    print(len(frames), "frames;", [f.t_start_s for f in frames], "tail", len(tail.pcm_s16le), tail.is_final)
    assert len(frames) == 2 and frames[1].t_start_s == 0.5 and tail.is_final
    print("[OK] frame assembler smoke test")
