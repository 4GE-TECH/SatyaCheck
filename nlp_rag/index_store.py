"""Pre-compiled corpus embeddings, so a process start does not re-encode everything.

C asked for "compiled database indices" at `config.FAISS_INDEX_PATH` and
`config.FAISS_DOCSTORE_PATH`. Those paths are honoured — they are the agreed
integration locations — but **the payload is not FAISS**.

`nlp_rag/index.py` uses a numpy inner-product index. At this corpus size that is
behaviourally identical to `IndexFlatIP` (both are an exhaustive dot product over
L2-normalised vectors) and it removes a wheel from the install. Nothing in `server/`
reads these files, so the filename is the only thing FAISS about them; every artefact
therefore carries `FORMAT` so anyone who opens one immediately learns what it is.

Suggested to C: rename the constants to `RAG_INDEX_PATH` / `RAG_DOCSTORE_PATH`.

The win here is not lookup speed. Thirty-eight documents are instant either way. It is
skipping BGE-m3 encoding of the whole corpus every time the server boots.

Build with::

    python -m nlp_rag.index_store
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

#: Bumped whenever the on-disk layout changes. A mismatch is rejected, never coerced —
#: silently reading a stale cache would serve embeddings from a different model.
FORMAT = "SATYACHECK_IPINDEX_V1"


@dataclass(frozen=True)
class CachedIndex:
    """What was read back off disk."""

    format: str
    vectors: dict[str, np.ndarray]
    texts: dict[str, str]


def vectors_for(encoder, corpus) -> dict[str, np.ndarray]:
    """Encode every indexable document, returning `{doc_id: vector}`."""
    docs = list(corpus.retrievable) + list(corpus.benign)
    if not docs:
        return {}
    encoded = encoder.encode([d.text for d in docs])
    return {d.id: np.asarray(v, dtype=np.float32) for d, v in zip(docs, encoded)}


def save(
    vectors: dict[str, np.ndarray],
    texts: dict[str, str],
    index_path: str | Path,
    docstore_path: str | Path,
    format_override: str | None = None,
) -> None:
    """Write both artefacts. Creates parent directories as needed."""
    index_path, docstore_path = Path(index_path), Path(docstore_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    docstore_path.parent.mkdir(parents=True, exist_ok=True)

    fmt = format_override or FORMAT
    ids = list(vectors)
    matrix = (
        np.stack([vectors[i] for i in ids]).astype(np.float32)
        if ids
        else np.zeros((0, 0), dtype=np.float32)
    )
    # Write through a handle, not a path. `np.savez` appends ".npz" to any path that
    # lacks it, which would silently produce `faiss_index.bin.npz` — a cache that never
    # hits and re-encodes the corpus on every boot without ever reporting an error.
    with index_path.open("wb") as fh:
        np.savez(
            fh,
            format=np.array([fmt]),
            ids=np.array(ids, dtype=object),
            vectors=matrix,
        )
    with docstore_path.open("wb") as fh:
        pickle.dump({"format": fmt, "texts": texts}, fh)


def load(index_path: str | Path, docstore_path: str | Path) -> CachedIndex | None:
    """Read both artefacts back, or None if absent, corrupt or stale. Never raises."""
    index_path, docstore_path = Path(index_path), Path(docstore_path)
    if not index_path.is_file() or not docstore_path.is_file():
        return None
    try:
        with np.load(index_path, allow_pickle=True) as archive:
            fmt = str(archive["format"][0])
            ids = [str(i) for i in archive["ids"]]
            matrix = archive["vectors"]
        with docstore_path.open("rb") as fh:
            docstore = pickle.load(fh)

        if fmt != FORMAT or docstore.get("format") != FORMAT:
            logger.warning("index cache format %s != %s; rebuilding", fmt, FORMAT)
            return None

        return CachedIndex(
            format=fmt,
            vectors={i: np.asarray(v, dtype=np.float32) for i, v in zip(ids, matrix)},
            texts=docstore.get("texts", {}),
        )
    except Exception as exc:  # noqa: BLE001 - a bad cache degrades to a rebuild
        logger.warning("index cache unreadable (%s); rebuilding", exc)
        return None


def default_paths() -> tuple[Path, Path]:
    """C's declared locations, falling back to `data/` before config.py exists."""
    try:
        import config

        return Path(config.FAISS_INDEX_PATH), Path(config.FAISS_DOCSTORE_PATH)
    except Exception:  # noqa: BLE001
        root = Path(__file__).resolve().parent.parent / "data"
        return root / "faiss_index.bin", root / "faiss_docstore.pkl"


if __name__ == "__main__":  # pragma: no cover - build the artefacts
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from nlp_rag.corpus_loader import load_corpus

    corpus = load_corpus(Path(__file__).resolve().parent / "corpus")

    try:
        from nlp_rag.embed import load_encoder

        encoder = load_encoder()
    except Exception:  # noqa: BLE001
        encoder = None

    if encoder is None:
        print("No encoder available — download models/bge-m3 first. Nothing written.")
        sys.exit(1)

    vectors = vectors_for(encoder, corpus)
    texts = {d.id: d.text for d in list(corpus.retrievable) + list(corpus.benign)}
    index_path, docstore_path = default_paths()
    save(vectors, texts, index_path, docstore_path)
    print(f"{len(vectors)} vectors → {index_path}\n{len(texts)} docs → {docstore_path}")
