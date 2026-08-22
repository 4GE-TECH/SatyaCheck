"""Test doubles for the model boundary.

BGE-m3 and faster-whisper are external model runtimes — legitimate places to stand in
a fake. Nothing internal is ever doubled.

`FakeEncoder` is deterministic and lexical: it hashes word tokens into a fixed-width
vector and L2-normalises. Text that shares vocabulary scores higher, which is enough to
drive retrieval behaviour without a 2.2 GB checkpoint. It is not a quality model and no
test should assert on its absolute scores.
"""

from __future__ import annotations

import hashlib
import re
from typing import Sequence

import numpy as np

_TOKEN = re.compile(r"\w+", re.UNICODE)


class FakeEncoder:
    """Deterministic hashing encoder standing in for BGE-m3."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in _TOKEN.findall(text.lower()):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
                vectors[row, int.from_bytes(digest, "big") % self.dim] += 1.0
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return vectors / norms
