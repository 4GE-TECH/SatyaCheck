"""Build the out-of-distribution reference bank for Model A (item 8).

    python -m audio_ml.eval.build_ood_ref --manifest <ifd>/manifest.csv \\
        [--out models/antispoof/ood_ref.npz] [--k 10] [--percentile 95] [--max-per-class 400]

The bank is AASIST's own penultimate embedding for windows of IFD **train** files —
the data Model A was fine-tuned on. The threshold is the `--percentile` of k-NN cosine
distance for windows of IFD **val** files, so by construction about
(100 - percentile)% of in-domain windows fall beyond it. Test files are never touched.

Exit codes: 0 ok · 1 bad input · 3 nothing could be embedded (Model A missing?).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np

from audio_ml.ood import OodReference, _normalise, knn_distance

logger = logging.getLogger(__name__)


def _sample(rows: list[dict], split: str, per_class: int, rng: np.random.Generator) -> list[dict]:
    by_label = defaultdict(list)
    for r in rows:
        if r["split"] == split:
            by_label[r["label"]].append(r)
    picked = []
    for label in sorted(by_label):
        group = by_label[label]
        idx = rng.permutation(len(group))[:per_class]
        picked += [group[i] for i in sorted(idx)]
    return picked


def _embed_all(rows, root, embedder) -> np.ndarray:
    parts = []
    for i, r in enumerate(rows, 1):
        emb = embedder(Path(root) / r["filepath"])
        if emb.size:
            parts.append(np.asarray(emb, dtype=np.float32))
        if i % 100 == 0:
            logger.info("embedded %d/%d files", i, len(rows))
    return np.vstack(parts) if parts else np.zeros((0, 0), dtype=np.float32)


def _default_embedder(path: Path) -> np.ndarray:
    from audio_ml.spoof import window_embeddings

    return window_embeddings(str(path))


def main(argv: Optional[Sequence[str]] = None,
         embedder: Callable[[Path], np.ndarray] = _default_embedder) -> int:
    try:
        import config
        default_out = config.SPOOF_OOD_REF_PATH
        default_k, default_pct = config.SPOOF_OOD_K, config.SPOOF_OOD_PERCENTILE
    except Exception:  # noqa: BLE001
        default_out, default_k, default_pct = Path("models/antispoof/ood_ref.npz"), 10, 95.0

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--audio-root", type=Path)
    ap.add_argument("--out", type=Path, default=default_out)
    ap.add_argument("--k", type=int, default=default_k)
    ap.add_argument("--percentile", type=float, default=default_pct)
    ap.add_argument("--max-per-class", type=int, default=400, help="train files per class in the bank")
    ap.add_argument("--max-val-per-class", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    if not args.manifest.is_file():
        logger.error("manifest not found: %s", args.manifest)
        return 1
    root = args.audio_root or args.manifest.parent
    with args.manifest.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    rng = np.random.default_rng(args.seed)

    bank = _embed_all(_sample(rows, "train", args.max_per_class, rng), root, embedder)
    val = _embed_all(_sample(rows, "val", args.max_val_per_class, rng), root, embedder)
    if bank.size == 0 or val.size == 0:
        logger.error("no %s windows could be embedded — is Model A installed?",
                     "train" if bank.size == 0 else "val")
        return 3

    distances = knn_distance(val, bank, args.k)
    threshold = float(np.percentile(distances, args.percentile))
    ref = OodReference(embeddings=_normalise(bank), threshold=threshold, k=args.k,
                       percentile=args.percentile, n_reference=len(bank))
    ref.save(args.out)
    print(json.dumps({
        "out": str(args.out), "n_reference_windows": len(bank), "n_val_windows": len(val),
        "k": args.k, "percentile": args.percentile, "threshold": round(threshold, 6),
        "val_distance_median": round(float(np.median(distances)), 6),
    }, indent=2))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    sys.exit(main())
