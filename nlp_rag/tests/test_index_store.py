"""Pre-compiled index artefacts, so server start does not re-encode the corpus.

C asked for "compiled database indices" at `config.FAISS_INDEX_PATH` /
`config.FAISS_DOCSTORE_PATH`. Those are the agreed integration locations and are
honoured, but the payload is a numpy inner-product index, not FAISS — see
`nlp_rag/index_store.py` and the note in `nlp_rag/PLAN.md` §3.

The real benefit is not lookup speed (38 docs is instant either way). It is skipping
BGE-m3 encoding of the whole corpus on every process start.
"""

from __future__ import annotations

import numpy as np
import pytest

from nlp_rag import index_store
from nlp_rag.corpus_loader import load_corpus
from nlp_rag.retrieve import Retriever
from nlp_rag.tests.fakes import FakeEncoder

CORPUS_DIR = "nlp_rag/corpus"


class CountingEncoder:
    """Wraps the fake encoder and records how many texts it was asked to embed."""

    def __init__(self) -> None:
        self._inner = FakeEncoder()
        self.encoded: list[str] = []

    def encode(self, texts):
        self.encoded.extend(texts)
        return self._inner.encode(texts)


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "index.bin", tmp_path / "docstore.pkl"


# --- round trip --------------------------------------------------------------

def test_saved_vectors_load_back_unchanged(paths):
    index_path, docstore_path = paths
    vectors = {"a": np.array([0.6, 0.8], dtype=np.float32)}

    index_store.save(vectors, {"a": "some text"}, index_path, docstore_path)
    loaded = index_store.load(index_path, docstore_path)

    assert np.allclose(loaded.vectors["a"], [0.6, 0.8])


def test_saved_docstore_loads_back_unchanged(paths):
    index_path, docstore_path = paths
    index_store.save(
        {"a": np.array([1.0, 0.0], dtype=np.float32)},
        {"a": "some text"},
        index_path,
        docstore_path,
    )
    assert index_store.load(index_path, docstore_path).texts["a"] == "some text"


def test_both_artefacts_are_written(paths):
    index_path, docstore_path = paths
    index_store.save({"a": np.array([1.0], dtype=np.float32)}, {"a": "t"}, index_path, docstore_path)
    assert index_path.is_file() and docstore_path.is_file()


def test_the_artefact_declares_its_real_format(paths):
    """The filename says faiss. The file itself must not pretend to be one."""
    index_path, docstore_path = paths
    index_store.save({"a": np.array([1.0], dtype=np.float32)}, {"a": "t"}, index_path, docstore_path)
    assert index_store.load(index_path, docstore_path).format == index_store.FORMAT


# --- degradation, never raising ---------------------------------------------

def test_missing_artefacts_load_as_none(paths):
    assert index_store.load(*paths) is None


def test_corrupt_index_loads_as_none(paths):
    index_path, docstore_path = paths
    index_path.write_bytes(b"not an index")
    docstore_path.write_bytes(b"not a docstore")
    assert index_store.load(index_path, docstore_path) is None


def test_a_stale_artefact_is_rejected_rather_than_silently_used(paths):
    """A cache written by an older format must not be trusted."""
    index_path, docstore_path = paths
    index_store.save({"a": np.array([1.0], dtype=np.float32)}, {"a": "t"}, index_path, docstore_path)
    index_store.save(
        {"a": np.array([1.0], dtype=np.float32)}, {"a": "t"}, index_path, docstore_path,
        format_override="SATYACHECK_IPINDEX_V0",
    )
    assert index_store.load(index_path, docstore_path) is None


# --- the retriever uses it --------------------------------------------------

def test_a_cached_retriever_returns_the_same_results_as_an_encoding_one():
    corpus = load_corpus(CORPUS_DIR)
    fresh = Retriever(FakeEncoder(), corpus)
    cached = Retriever(FakeEncoder(), corpus, vectors=index_store.vectors_for(FakeEncoder(), corpus))

    query = "Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe"
    assert [p.playbook_id for p in fresh.search(query, k=3).playbooks] == [
        p.playbook_id for p in cached.search(query, k=3).playbooks
    ]


def test_a_cached_retriever_does_not_re_encode_the_corpus():
    corpus = load_corpus(CORPUS_DIR)
    vectors = index_store.vectors_for(FakeEncoder(), corpus)

    encoder = CountingEncoder()
    Retriever(encoder, corpus, vectors=vectors)
    assert encoder.encoded == [], "corpus was re-encoded despite a full cache"


def test_a_document_missing_from_the_cache_is_still_encoded():
    """Adding a corpus document must not require discarding the whole cache."""
    corpus = load_corpus(CORPUS_DIR)
    vectors = index_store.vectors_for(FakeEncoder(), corpus)
    dropped = next(iter(vectors))
    del vectors[dropped]

    encoder = CountingEncoder()
    Retriever(encoder, corpus, vectors=vectors)
    assert len(encoder.encoded) == 1


def test_an_uncached_retriever_still_works():
    corpus = load_corpus(CORPUS_DIR)
    assert Retriever(FakeEncoder(), corpus, vectors=None).search("test", k=1) is not None
