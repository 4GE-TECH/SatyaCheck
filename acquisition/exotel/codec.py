"""Telephony audio primitives for the Exotel adapter: G.711 mu-law and resampling.

Private to acquisition/exotel. numpy + scipy only (CLAUDE.md boundaries).
"""

from __future__ import annotations

from math import gcd

import numpy as np


def _expand(code: int) -> int:
    """ITU-T G.711 mu-law expansion of one 8-bit code to a 16-bit linear value."""
    u = ~code & 0xFF
    sign, exponent, mantissa = u & 0x80, (u >> 4) & 0x07, u & 0x0F
    magnitude = (((mantissa << 3) + 0x84) << exponent) - 0x84
    return -magnitude if sign else magnitude


_MULAW_TABLE = np.array([_expand(c) for c in range(256)], dtype=np.int16)


def mulaw_decode(data: bytes) -> np.ndarray:
    """G.711 mu-law bytes -> int16 linear PCM (one sample per byte)."""
    return _MULAW_TABLE[np.frombuffer(data, dtype=np.uint8)]


class StreamingResampler:
    """Rational resampler (in_rate -> out_rate) that keeps its filter state between
    calls, so feeding a stream in chunks of any size yields exactly the samples that
    filtering the whole stream at once would.

    Zero-stuff by L, low-pass FIR (cut-off at the lower Nyquist, gain L), keep every
    M-th sample of the *global* upsampled stream. The FIR's delay line (`zi`) and the
    decimation phase both carry across calls. Same-rate input passes through untouched.
    """

    def __init__(self, in_rate: int, out_rate: int, taps_per_phase: int = 32) -> None:
        g = gcd(int(in_rate), int(out_rate))
        self.up = int(out_rate) // g
        self.down = int(in_rate) // g
        self.identity = self.up == 1 and self.down == 1
        if self.identity:
            return
        from scipy.signal import firwin

        factor = max(self.up, self.down)
        numtaps = taps_per_phase * factor + 1
        self.taps = firwin(numtaps, 1.0 / factor, window=("kaiser", 8.0)) * self.up
        self.zi = np.zeros(numtaps - 1)
        self.position = 0  # index, in the global upsampled stream, of the next input slot

    def process(self, x) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64).ravel()
        if self.identity:
            return x
        if x.size == 0:
            return x
        from scipy.signal import lfilter

        stuffed = np.zeros(x.size * self.up)
        stuffed[:: self.up] = x
        y, self.zi = lfilter(self.taps, 1.0, stuffed, zi=self.zi)
        first = (-self.position) % self.down
        self.position += stuffed.size
        return y[first:: self.down]
