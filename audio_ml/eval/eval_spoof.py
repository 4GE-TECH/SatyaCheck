"""Authenticity-branch evaluation: EER and min t-DCF on a leakage-checked split (item 12).

    python -m audio_ml.eval.eval_spoof --manifest <dir>/manifest.csv --out data/spoof_eval.json

The manifest is the IFD format Model A was fine-tuned from (columns ``filepath, label,
speaker_id, split, orig_sr, ...``; label 1 = bonafide, 0 = deepfake; paths relative to
the manifest's directory). Model A's split lives outside this repo — see PLAN, item 12.

ORDER IS THE POINT. Before a single file is scored:

  1. no speaker may appear in two splits;
  2. no audio file's bytes (SHA-256) may appear in two splits that touch an evaluated
     split — a renamed copy of a training file in test is the same file.

Either failure exits 2 and writes nothing. A number measured on leaked data is worse
than no number, because it gets quoted.

Then each evaluated split is scored with ``detect_spoof`` (median P(synthetic) per
file) and reported with its n per class, plus a breakdown by *original* sample rate:
in IFD, bonafide and deepfake files were captured at different rates in different
proportions, so a detector can partly learn resampling artefacts rather than synthesis.
A per-rate EER that is much worse than the pooled one is that confound showing.

Exit codes: 0 ok · 1 bad input · 2 leakage · 3 nothing could be scored.

min t-DCF follows the ASVspoof 2019 evaluation plan (Kinnunen et al., "t-DCF: a
detection cost function for the tandem assessment of spoofing countermeasures and
automatic speaker verification", 2018) with the 2019 default cost model. It needs the
ASV system's error rates; IFD ships no ASV trials, so the default is an *ideal* ASV
(all ASV error rates 0), which reduces t-DCF to a cost-weighted CM-only DCF. The report
says which assumption was used. Which ASV rates to use is an open question (PLAN).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

BONAFIDE, SPOOF = 1, 0
DEFAULT_EVAL_SPLITS = ("test", "test_c")


# --- metrics ---------------------------------------------------------------------

def _error_curves(bonafide: Sequence[float], spoof: Sequence[float]):
    """Miss rate (bonafide flagged spoof) and false-accept rate (spoof passed as
    bonafide) at every threshold. A file is flagged spoof when score >= threshold."""
    bona = np.sort(np.asarray(bonafide, dtype=float))
    spf = np.sort(np.asarray(spoof, dtype=float))
    if bona.size == 0 or spf.size == 0:
        raise ValueError("need at least one bonafide and one spoof score")
    thresholds = np.concatenate([np.unique(np.concatenate([bona, spf])), [np.inf]])
    p_miss = 1.0 - np.searchsorted(bona, thresholds, side="left") / bona.size
    p_fa = np.searchsorted(spf, thresholds, side="left") / spf.size
    return thresholds, p_miss, p_fa


def compute_eer(bonafide: Sequence[float], spoof: Sequence[float]) -> tuple[float, float]:
    """Equal error rate and the threshold it occurs at."""
    thresholds, p_miss, p_fa = _error_curves(bonafide, spoof)
    i = int(np.argmin(np.abs(p_miss - p_fa)))
    return float((p_miss[i] + p_fa[i]) / 2.0), float(thresholds[i])


@dataclass(frozen=True)
class AsvRates:
    """The ASV system's error rates at its own operating threshold."""
    p_miss: float        # genuine target trials rejected
    p_fa: float          # zero-effort impostors accepted
    p_miss_spoof: float  # spoofs rejected by ASV alone


IDEAL_ASV = AsvRates(0.0, 0.0, 0.0)

# ASVspoof 2019 default cost model.
P_SPOOF = 0.05
P_TAR = (1 - P_SPOOF) * 0.99
P_NON = (1 - P_SPOOF) * 0.01
C_MISS_ASV, C_FA_ASV, C_MISS_CM, C_FA_CM = 1.0, 10.0, 1.0, 10.0


def min_tdcf(bonafide: Sequence[float], spoof: Sequence[float], asv: AsvRates) -> float:
    """Minimum normalised tandem detection cost over all CM thresholds."""
    c1 = P_TAR * (C_MISS_CM - C_MISS_ASV * asv.p_miss) - P_NON * C_FA_ASV * asv.p_fa
    c2 = C_FA_CM * P_SPOOF * (1.0 - asv.p_miss_spoof)
    if c1 <= 0 or c2 <= 0:
        raise ValueError(
            f"t-DCF undefined for these ASV rates (C1={c1:.4f}, C2={c2:.4f}): "
            "the ASV system is worse than accepting or rejecting everything"
        )
    _, p_miss, p_fa = _error_curves(bonafide, spoof)
    return float(np.min(c1 * p_miss + c2 * p_fa) / min(c1, c2))


# --- manifest and leakage -------------------------------------------------------------

@dataclass(frozen=True)
class ManifestRow:
    filepath: str
    label: int
    speaker_id: str
    split: str
    orig_sr: int


def load_manifest(path: Path) -> list[ManifestRow]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return [
            ManifestRow(r["filepath"], int(r["label"]), r["speaker_id"], r["split"],
                        int(float(r.get("orig_sr") or 0)))
            for r in csv.DictReader(fh)
        ]


def check_speaker_disjoint(rows: Iterable[ManifestRow]) -> list[str]:
    speakers: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        speakers[r.split].add(r.speaker_id)
    problems = []
    for a, b in combinations(sorted(speakers), 2):
        shared = speakers[a] & speakers[b]
        if shared:
            problems.append(f"speakers in both {a} and {b}: {sorted(shared)}")
    return problems


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 16):
            h.update(chunk)
    return h.hexdigest()


def check_hash_disjoint(
    rows: Iterable[ManifestRow], root: Path, eval_splits: Optional[Iterable[str]] = None,
) -> list[str]:
    """Identical bytes in two splits. With `eval_splits`, only pairs touching one count."""
    focus = set(eval_splits) if eval_splits is not None else None
    by_hash: dict[str, list[ManifestRow]] = defaultdict(list)
    problems = []
    rows = list(rows)
    for i, r in enumerate(rows, 1):
        path = Path(root) / r.filepath
        if not path.is_file():
            problems.append(f"missing file: {r.filepath}")
            continue
        by_hash[_sha256(path)].append(r)
        if i % 2000 == 0:
            logger.info("hashed %d/%d files", i, len(rows))
    for digest, same in by_hash.items():
        splits = {r.split for r in same}
        if len(splits) < 2 or (focus is not None and not splits & focus):
            continue
        names = ", ".join(f"{r.split}:{r.filepath}" for r in same)
        problems.append(f"identical audio {digest[:12]} in {sorted(splits)}: {names}")
    return problems


# --- scoring and report -----------------------------------------------------------------

def _detect_spoof_scorer(path: Path) -> Optional[float]:
    """Median P(synthetic), or None when the branch abstained (no window scored)."""
    from audio_ml.spoof import detect_spoof

    signal = detect_spoof(str(path))
    return signal.score if signal.n_chunks > 0 else None


def _summary(scored: list[tuple[ManifestRow, float]], asv: AsvRates) -> dict:
    bona = [s for r, s in scored if r.label == BONAFIDE]
    spf = [s for r, s in scored if r.label == SPOOF]
    out: dict = {"n_bonafide": len(bona), "n_spoof": len(spf)}
    if bona and spf:
        eer, threshold = compute_eer(bona, spf)
        out.update(eer=round(eer, 4), eer_threshold=round(threshold, 4),
                   min_tdcf=round(min_tdcf(bona, spf, asv), 4))
    else:
        out["note"] = "one class absent; no EER"
    return out


def evaluate(rows, root, splits, scorer, asv) -> dict:
    report = {}
    for split in splits:
        subset = [r for r in rows if r.split == split]
        if not subset:
            logger.warning("split %r has no rows in the manifest; not evaluated", split)
            continue
        scored, failed = [], 0
        for i, r in enumerate(subset, 1):
            score = scorer(Path(root) / r.filepath)
            if score is None:
                failed += 1
            else:
                scored.append((r, float(score)))
            if i % 200 == 0:
                logger.info("%s: scored %d/%d", split, i, len(subset))
        summary = _summary(scored, asv)
        summary["n_unscored"] = failed
        by_sr = defaultdict(list)
        for r, s in scored:
            by_sr[str(r.orig_sr)].append((r, s))
        summary["by_orig_sr"] = {sr: _summary(items, asv) for sr, items in sorted(by_sr.items())}
        report[split] = summary
    return report


def main(argv: Optional[Sequence[str]] = None,
         scorer: Callable[[Path], Optional[float]] = _detect_spoof_scorer) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--audio-root", type=Path, help="defaults to the manifest's directory")
    ap.add_argument("--splits", nargs="+", default=list(DEFAULT_EVAL_SPLITS))
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--limit", type=int, help="score at most N files per split and class (smoke runs)")
    args = ap.parse_args(argv)

    if not args.manifest.is_file():
        logger.error("manifest not found: %s", args.manifest)
        return 1
    root = args.audio_root or args.manifest.parent
    rows = load_manifest(args.manifest)
    present = {r.split for r in rows}
    if not present & set(args.splits):
        logger.error("none of the requested splits %s is in the manifest (it has %s)",
                     args.splits, sorted(present))
        return 1

    speaker_problems = check_speaker_disjoint(rows)
    hash_problems = check_hash_disjoint(rows, root, eval_splits=args.splits)
    for p in speaker_problems + hash_problems:
        logger.error("LEAKAGE: %s", p)
    if speaker_problems or hash_problems:
        logger.error("refusing to score a leaky split; nothing written")
        return 2

    if args.limit:
        kept, seen = [], defaultdict(int)
        for r in rows:
            # Per split *and class*: manifests are often sorted by label, and a
            # one-class sample has no EER at all.
            key = (r.split, r.label)
            if r.split in args.splits and seen[key] >= args.limit:
                continue
            seen[key] += 1
            kept.append(r)
        rows = kept

    splits = evaluate(rows, root, args.splits, scorer, IDEAL_ASV)
    if not any(s["n_bonafide"] + s["n_spoof"] for s in splits.values()):
        logger.error("no file could be scored — is Model A installed? (models/antispoof/)")
        return 3

    report = {
        "manifest": str(args.manifest),
        "score": "median P(synthetic) per file, audio_ml.spoof.detect_spoof",
        "tdcf_asv_assumption": "ideal",
        "limit_per_split": args.limit,
        "leakage": {"speaker_overlap": speaker_problems, "hash_overlap": hash_problems},
        "splits": splits,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("wrote %s", args.out)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    sys.exit(main())
