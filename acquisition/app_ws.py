"""App WebSocket adapter: one base64-decoded chunk (a complete RIFF WAV) -> AudioFrame(s).

The app sends self-contained WAV chunks (`AudioChunk.toWav()`), at whatever rate and
channel count the device recorded. Each becomes 16 kHz mono s16le with a continuing
`seq` and `t_start_s`, so downstream sees one unbroken timeline and never the chunking.

A chunk that is already 16 kHz mono 16-bit PCM is passed through bit-exact (ffmpeg
would produce the same samples; skipping it saves a process per chunk). Anything else
goes through ffmpeg. Imports only contracts, config and the stdlib/numpy.

Never raises (CLAUDE.md rule 5): an undecodable chunk returns [] with the reason logged,
and the timeline does not advance.

Owned by the Track 1 (acquisition) person.
"""

from __future__ import annotations

import io
import logging
import wave
from typing import Optional

import config
from acquisition._ffmpeg import decode_to_pcm16
from contracts import AudioFrame

log = logging.getLogger("satyacheck.acquisition.app_ws")


def _passthrough(data: bytes) -> Optional[bytes]:
    """The chunk's PCM if it is already 16 kHz mono s16 WAV; else None (use ffmpeg)."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            if (w.getcomptype() == "NONE" and w.getnchannels() == 1
                    and w.getsampwidth() == 2 and w.getframerate() == config.TARGET_SAMPLE_RATE):
                return w.readframes(w.getnframes())
    except Exception:  # noqa: BLE001 — not a plain PCM WAV; ffmpeg decides
        pass
    return None


class AppWsDecoder:
    """Per-session, stateful: chunk bytes in, AudioFrames on one continuing timeline out."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.next_seq = 0
        self._samples = 0  # samples emitted so far

    @property
    def t_s(self) -> float:
        """Session time at the end of everything decoded so far."""
        return self._samples / config.TARGET_SAMPLE_RATE

    def decode(self, data: bytes, is_final: bool = False) -> list[AudioFrame]:
        """Decode one chunk. Returns [] (logged) when it holds no decodable audio."""
        try:
            label = f"{self.session_id}"
            if not data:
                log.warning(f"[{label}] app chunk seq={self.next_seq}: empty, no audio")
                return []
            if not (data[:4] == b"RIFF" and data[8:12] == b"WAVE"):
                log.warning(f"[{label}] app chunk seq={self.next_seq} is not a RIFF WAV "
                            f"({len(data)} bytes); trying ffmpeg")
            pcm = _passthrough(data)
            if pcm is None:
                pcm = decode_to_pcm16(data, label)
            if not pcm:
                log.warning(f"[{label}] app chunk seq={self.next_seq} decoded to no audio; "
                            f"dropped")
                return []
            if len(pcm) % 2:
                pcm = pcm[:-1]
            frame = AudioFrame(session_id=self.session_id, seq=self.next_seq,
                               t_start_s=self.t_s, pcm_s16le=pcm, is_final=is_final)
            self.next_seq += 1
            self._samples += len(pcm) // 2
            return [frame]
        except Exception as e:  # noqa: BLE001
            log.error(f"[{self.session_id}] app chunk decode failed: {type(e).__name__}: {e}")
            return []


if __name__ == "__main__":
    import math
    import struct

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44_100)
        w.writeframes(b"".join(struct.pack("<hh", v, v) for v in (
            int(16000 * math.sin(2 * math.pi * 1000 * i / 44_100)) for i in range(44_100))))
    dec = AppWsDecoder("smoke")
    frames = dec.decode(buf.getvalue()) + dec.decode(buf.getvalue(), is_final=True)
    assert [f.seq for f in frames] == [0, 1] and frames[1].t_start_s == 1.0, frames
    assert dec.decode(b"garbage") == []
    print(f"[OK] app_ws: {len(frames)} frames, {dec.t_s:.2f}s at 16 kHz mono")
