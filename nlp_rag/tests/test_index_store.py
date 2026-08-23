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


# --- a cache belongs to the encoder that wrote it ----------------------------
# FORMAT guards the on-disk *layout*. It says nothing about which model produced the
# numbers, and BGE-m3 vectors are 1024-dim while the stand-in encoder's are 256 — so a
# cache written by one and read by the other does not degrade, it raises a matmul shape
# error out of the middle of a request.

def test_a_cache_written_by_another_encoder_is_rejected(paths):
    index_path, docstore_path = paths
    index_store.save(
        {"a": np.array([1.0], dtype=np.float32)},
        {"a": "t"},
        index_path,
        docstore_path,
        encoder="BGEM3Encoder",
    )
    assert index_store.load(index_path, docstore_path, expect_encoder="FakeEncoder") is None


def test_a_cache_written_by_the_same_encoder_is_accepted(paths):
    index_path, docstore_path = paths
    index_store.save(
        {"a": np.array([1.0], dtype=np.float32)},
        {"a": "t"},
        index_path,
        docstore_path,
        encoder="FakeEncoder",
    )
    assert index_store.load(index_path, docstore_path, expect_encoder="FakeEncoder")


def test_a_cache_with_no_recorded_encoder_is_still_readable(paths):
    """Advisory, like the hashes. An older artefact degrades rather than failing."""
    index_path, docstore_path = paths
    index_store.save({"a": np.array([1.0], dtype=np.float32)}, {"a": "t"}, index_path, docstore_path)
    assert index_store.load(index_path, docstore_path, expect_encoder="FakeEncoder")


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


# --- editing a document must invalidate its vector ---------------------------
# The failure this guards is silent and total: a cache keyed on document id alone
# serves the embedding of the *previous* wording forever. Rewriting corpus bodies is
# exactly what corpus work is, so the stale vector would be the normal case, and
# nothing would report it.

def _edited(corpus, doc_id: str, text: str):
    """A copy of `corpus` with one document's text replaced, id unchanged."""
    import dataclasses

    from nlp_rag.corpus_loader import Corpus

    return Corpus(
        dataclasses.replace(d, text=text) if d.id == doc_id else d
        for d in list(corpus.retrievable) + list(corpus.benign) + list(corpus.heldout)
    )


def test_editing_a_documents_text_re_encodes_it():
    corpus = load_corpus(CORPUS_DIR)
    cache = index_store.vectors_for(FakeEncoder(), corpus)
    hashes = index_store.hashes_for(corpus)

    target = corpus.retrievable[0].id
    rewritten = _edited(corpus, target, "completely different wording than before")

    encoder = CountingEncoder()
    Retriever(encoder, rewritten, vectors=cache, hashes=hashes)
    assert len(encoder.encoded) == 1, (
        "an edited document was served from its stale vector"
    )


def test_the_re_encoded_vector_is_the_one_actually_used():
    """Counting the encode call is not enough — the fresh vector must also win.

    A stale document is present in both the cache and the freshly-encoded map. Reading
    the cache first re-serves exactly the vector the re-encode was meant to replace,
    and the encode-count assertion above would still pass.
    """
    corpus = load_corpus(CORPUS_DIR)
    cache = index_store.vectors_for(FakeEncoder(), corpus)
    hashes = index_store.hashes_for(corpus)

    target = corpus.retrievable[0].id
    marker = "zzqqxx unmistakable rewritten wording"
    rewritten = _edited(corpus, target, marker)

    retriever = Retriever(FakeEncoder(), rewritten, vectors=cache, hashes=hashes)
    hits = retriever.search(marker, k=1).playbooks
    assert hits, "the rewritten document did not retrieve on its own new text"
    assert hits[0].playbook_id == rewritten.resolve_citation(target).playbook_id


def test_an_unedited_document_is_still_served_from_cache():
    corpus = load_corpus(CORPUS_DIR)
    cache = index_store.vectors_for(FakeEncoder(), corpus)
    hashes = index_store.hashes_for(corpus)

    encoder = CountingEncoder()
    Retriever(encoder, corpus, vectors=cache, hashes=hashes)
    assert encoder.encoded == []


def test_hashes_survive_the_round_trip(paths):
    index_path, docstore_path = paths
    index_store.save(
        {"a": np.array([1.0], dtype=np.float32)},
        {"a": "some text"},
        index_path,
        docstore_path,
        hashes={"a": "deadbeef"},
    )
    assert index_store.load(index_path, docstore_path).hashes == {"a": "deadbeef"}


def test_a_cache_without_hashes_still_loads():
    """Hashes are advisory. A cache that predates them degrades to id-only matching."""
    corpus = load_corpus(CORPUS_DIR)
    cache = index_store.vectors_for(FakeEncoder(), corpus)

    encoder = CountingEncoder()
    Retriever(encoder, corpus, vectors=cache, hashes=None)
    assert encoder.encoded == []


def test_an_uncached_retriever_still_works():
    corpus = load_corpus(CORPUS_DIR)
    assert Retriever(FakeEncoder(), corpus, vectors=None).search("test", k=1) is not None
