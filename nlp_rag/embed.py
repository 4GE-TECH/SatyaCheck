"""BGE-m3 adapter.

The model boundary. `Retriever` depends on the `Encoder` protocol, not on this module,
so everything downstream is testable without a 2.2 GB checkpoint.

Nothing here is wired yet: `FlagEmbedding` is not installed and `models/` does not exist.
`load_encoder` returns None in that state and the intent branch degrades to markers only,
which is visible in `ScriptAnalysisResult.details`. When A's H0 downloads land, this is
the only file that changes.

No runtime network calls: `local_files_only` is forced, so a missing checkpoint fails
fast rather than silently pulling 2.2 GB over venue wifi mid-demo.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import numpy as np

logger = logging.getLogger(__name__)

#: `CLAUDE.md` rule 4 — everything loads from ./models/, path owned by C's config.py.
try:  # pragma: no cover - depends on whether C has shipped config.py yet
    import config as _config
except ImportError:  # pragma: no cover
    _config = None

_MODELS_DIR = getattr(_config, "MODELS_DIR", None) or (
    Path(__file__).resolve().parent.parent / "models"
)
#: e.g. "BAAI/bge-m3" → models/bge-m3
MODEL_NAME: str = getattr(_config, "BGE_MODEL_NAME", "BAAI/bge-m3")
MODEL_DIR = Path(_MODELS_DIR) / MODEL_NAME.split("/")[-1]


class BGEM3Encoder:
    """Wraps `BAAI/bge-m3` behind the two-line `Encoder` protocol."""

    def __init__(self, model_dir: Path = MODEL_DIR) -> None:
        from sentence_transformers import SentenceTransformer  # deferred: heavy import

        self._model = SentenceTransformer(str(model_dir), local_files_only=True)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        return self._model.encode(
            list(texts), normalize_embeddings=True, show_progress_bar=False
        ).astype(np.float32)


def load_encoder(model_dir: Path = MODEL_DIR) -> BGEM3Encoder | None:
    """Return a live encoder, or None if the model stack is not available.

    Returning None rather than raising is deliberate: a missing checkpoint degrades the
    intent branch to markers, and C's request still completes.
    """
    if not model_dir.exists():
        logger.warning("BGE-m3 not found at %s; intent branch runs markers-only", model_dir)
        return None
    try:
        return BGEM3Encoder(model_dir)
    except Exception as exc:  # noqa: BLE001 - any load failure degrades identically
        logger.warning("BGE-m3 failed to load (%s); intent branch runs markers-only", exc)
        return None


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    encoder = load_encoder()
    if encoder is None:
        print(f"no encoder: {MODEL_DIR} missing or unloadable")
    else:
        vectors = encoder.encode(["turant paise bhejo", "will be home by 7"])
        print(f"encoded {vectors.shape}, norms {np.linalg.norm(vectors, axis=1)}")
