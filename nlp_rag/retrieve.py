"""Retrieval over the scam-playbook corpus, with the benign cohort scored alongside.

Two indexes, one query. The scam index produces the citations shown to the user; the
benign index produces the background distribution scoring normalises against. They are
returned together because a similarity without its background is not interpretable —
see `nlp_rag/PLAN.md` §5.

The encoder is injected. BGE-m3 is an external model runtime and lives behind
`embed.BGEM3Encoder`; tests drive this with a deterministic fake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

import numpy as np

from contracts import RetrievedPlaybook
from nlp_rag.corpus_loader import Corpus
from nlp_rag.index import InnerProductIndex


class Encoder(Protocol):
    """One operation: text in, L2-normalised vectors out."""

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


@dataclass(frozen=True)
class RetrievalResult:
    """Playbook hits plus the cohort scores needed to interpret them."""

    playbooks: list[RetrievedPlaybook] = field(default_factory=list)
    cohort_similarities: list[float] = field(default_factory=list)
    top_similarity: float = 0.0
    top_doc_id: str | None = None
    #: Markers the top-scoring document exemplifies. Scoring suppresses these from the
    #: marker delta, because the retrieval score already reflects them.
    top_doc_markers: list[str] = field(default_factory=list)

    @classmethod
    def empty(cls) -> RetrievalResult:
        return cls()


class Retriever:
    """Builds both indexes once, then answers queries against them."""

    def __init__(
        self,
        encoder: Encoder,
        corpus: Corpus,
        vectors: dict[str, np.ndarray] | None = None,
    ) -> None:
        """`vectors` is an optional `{doc_id: embedding}` cache from `index_store`.

        Documents present in it are not re-encoded, which is what makes a warm start
        cheap under BGE-m3. Documents absent from it still are, so adding a corpus
        document never means discarding the whole cache.
        """
        self._encoder = encoder
        self._corpus = corpus

        self._scam_index = InnerProductIndex()
        self._cohort_index = InnerProductIndex()

        retrievable = corpus.retrievable
        if retrievable:
            self._scam_index.add(
                [doc.id for doc in retrievable],
                self._embed(retrievable, vectors),
            )

        benign = corpus.benign
        if benign:
            self._cohort_index.add(
                [doc.id for doc in benign],
                self._embed(benign, vectors),
            )

    def _embed(self, docs, cache: dict[str, np.ndarray] | None) -> np.ndarray:
        """Encode only what the cache does not already hold."""
        if cache is None:
            return self._encoder.encode([doc.text for doc in docs])

        missing = [doc for doc in docs if doc.id not in cache]
        fresh: dict[str, np.ndarray] = {}
        if missing:
            encoded = self._encoder.encode([doc.text for doc in missing])
            fresh = {
                doc.id: np.asarray(vec, dtype=np.float32)
                for doc, vec in zip(missing, encoded)
            }
        return np.stack(
            [cache.get(doc.id, fresh.get(doc.id)) for doc in docs]
        ).astype(np.float32)

    def search(self, text: str, k: int = 5) -> RetrievalResult:
        if not text or not text.strip():
            return RetrievalResult.empty()

        query = self._encoder.encode([text])[0]
        hits = self._scam_index.search(query, k)
        if not hits:
            return RetrievalResult(
                cohort_similarities=self._cohort_index.scores_against_all(query)
            )

        return RetrievalResult(
            playbooks=[
                self._corpus.to_playbook(doc_id, score) for doc_id, score in hits
            ],
            cohort_similarities=self._cohort_index.scores_against_all(query),
            top_similarity=hits[0][1],
            top_doc_id=hits[0][0],
            top_doc_markers=self._corpus.markers_for(hits[0][0]),
        )

    @property
    def corpus(self) -> Corpus:
        return self._corpus


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    import sys
    from pathlib import Path

    from nlp_rag.corpus_loader import load_corpus
    from nlp_rag.tests.fakes import FakeEncoder

    query = " ".join(sys.argv[1:]) or (
        "Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe"
    )
    retriever = Retriever(FakeEncoder(), load_corpus(Path(__file__).parent / "corpus"))
    result = retriever.search(query, k=3)

    print(f"query: {query}\n")
    for playbook in result.playbooks:
        print(f"  {playbook.similarity_score:.3f}  {playbook.title}")
        print(f"          {playbook.source_agency} · {playbook.source_url}")
    if result.cohort_similarities:
        cohort = np.array(result.cohort_similarities)
        print(f"\n  cohort: mean {cohort.mean():.3f}  std {cohort.std():.3f}  "
              f"max {cohort.max():.3f}")
