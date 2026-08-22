"""Flat inner-product vector index.

On L2-normalised vectors, inner product *is* cosine similarity, so this is behaviourally
identical to a FAISS `IndexFlatIP`. It is deliberately flat:

- IVF and PQ require a **training** step, which `CLAUDE.md` rule 1 forbids outright.
- Under ~10k vectors an exhaustive dot product is not the bottleneck; the encoder is.

The corpus tops out around 300 documents. Swapping this for `faiss.IndexFlatIP` at H1 is
a drop-in change behind the same two methods, and changes no result.
"""

from __future__ import annotations

import numpy as np


class InnerProductIndex:
    """Exhaustive cosine-similarity index over L2-normalised vectors."""

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._matrix: np.ndarray | None = None

    def add(self, ids: list[str], vectors: np.ndarray) -> None:
        if len(ids) != vectors.shape[0]:
            raise ValueError(f"{len(ids)} ids but {vectors.shape[0]} vectors")
        self._ids = list(ids)
        self._matrix = np.ascontiguousarray(vectors, dtype=np.float32)

    def search(self, query: np.ndarray, k: int) -> list[tuple[str, float]]:
        """Return the `k` highest-scoring (id, similarity) pairs, best first."""
        if self._matrix is None or not self._ids or k <= 0:
            return []

        scores = self._matrix @ np.asarray(query, dtype=np.float32)
        k = min(k, len(self._ids))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(self._ids[i], float(scores[i])) for i in top]

    def scores_against_all(self, query: np.ndarray) -> list[float]:
        """Similarity against every vector — the background distribution for s-norm."""
        if self._matrix is None or not self._ids:
            return []
        return [float(s) for s in self._matrix @ np.asarray(query, dtype=np.float32)]

    def __len__(self) -> int:
        return len(self._ids)
