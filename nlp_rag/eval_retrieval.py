"""Retrieval and false-positive evaluation — the instrument corpus work is steered by.

`nlp_rag/PLAN.md` §12 asks for three numbers. This produces them:

1. **P@k strict** — the held-out excerpt's `expected_anchor` appears among the top-k
   retrieved documents, resolved to their anchors.
2. **P@k family** — same, by `scam_family`. A different advisory about the same scam is
   a useful answer; a different scam is not.
3. **Benign false-positive rate** — the fraction of the cohort scoring at or above the
   amber floor. This is the number that proves the two over-flagging guards in
   `PRD.md` §6, and it is the one that corpus growth puts at risk.

Plus the §5.1 calibration targets, so a run says both "did retrieval improve" and "did
the fixture scores survive".

**Held-out excerpts were never used to author a corpus document.** If the corpus and the
test set share an author, P@k measures the author's memory of their own writing.

**The benign cohort is scored leave-one-out.** Every benign document is *in* the cohort
that normalisation reads as background. Leaving its own ~1.0 self-similarity in that
background raises the mean, depresses its own z, and understates the false-positive rate
— the exact direction that makes a corpus look safer than it is.

Run::

    python -m nlp_rag.eval_retrieval             # human-readable
    python -m nlp_rag.eval_retrieval --json      # write nlp_rag/eval_baseline.json
    python -m nlp_rag.eval_retrieval --fake      # force the stand-in encoder
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import logging

from nlp_rag import thresholds
from nlp_rag.corpus_loader import Corpus, CorpusDoc, load_corpus
from nlp_rag.markers import find_markers
from nlp_rag.retrieve import RetrievalResult, Retriever
from nlp_rag.score import score_script

logger = logging.getLogger(__name__)

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
BASELINE_PATH = Path(__file__).resolve().parent / "eval_baseline.json"

#: The §5.1 targets, restated as data. Same transcripts as `tests/test_score.py`, so a
#: run and the test suite cannot disagree about what "the bank IVR case" means.
#:
#: **These are the TUNING set. Passing them is necessary, not evidence.** `SCRIPT_Z0` was
#: fitted while watching these exact strings, so they cannot also serve as validation —
#: that is training on the test set. They stay because their targets come from C's
#: contract fixtures rather than from anything measured here, which makes them a
#: regression guard against an external number.
#:
#: Validation lives in the distributional metrics instead: held-out scam recall over 50
#: transcripts and the benign false-positive rate over 103, neither of which was
#: consulted while choosing a threshold.
CALIBRATION_CASES: tuple[tuple[str, str, str, float], ...] = (
    (
        "clone_extortion",
        "Papa emergency ho gaya hai, police ne pakad liya hai. "
        "Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe.",
        ">=",
        0.90,
    ),
    (
        "family_checkin",
        "Hi Ma, I just reached the office. Will be home by 7 PM today.",
        "<=",
        0.10,
    ),
    (
        "bank_ivr",
        "Dear customer, your HDFC Bank statement for account ending 4402 is ready. "
        "Press 1 to receive on WhatsApp.",
        "<=",
        0.10,
    ),
)

# The language-bias guard used to live here as two Devanagari strings with a >= 0.90
# target. Both are gone, for two reasons that point the same way.
#
# The 0.90 came from the clone-extortion fixture. Nothing in `contracts.py` says a
# Devanagari parcel scam must score 0.90, so the target was invented, and one at 0.906
# with six thousandths of margin duly failed the moment the benign cohort grew — a
# threshold artefact reported as a defect.
#
# More importantly, two hand-picked strings are a worse instrument than the thing that
# replaced them: `recall_by_lang` measures the same property across 12 Devanagari and 15
# Hinglish held-out transcripts. If Hindi under-scores, a recall gap says so with a
# sample behind it.


# --- small, separately testable arithmetic -----------------------------------

def rank_of(target: str, retrieved: Sequence[str]) -> int | None:
    """1-based position of `target`, or None if it is not there."""
    for position, candidate in enumerate(retrieved, start=1):
        if candidate == target:
            return position
    return None


def mean(values: Iterable[bool | float]) -> float:
    """Mean of a possibly-empty sequence. Empty is 0.0, never a division error."""
    values = list(values)
    if not values:
        return 0.0
    return sum(float(v) for v in values) / len(values)


def without_self(retrieval: RetrievalResult, doc_id: str) -> RetrievalResult:
    """The same result with `doc_id` removed from the normalisation cohort.

    Similarities and ids are positionally aligned, so both are filtered together. An id
    that is not in the cohort leaves the result untouched.
    """
    if doc_id not in retrieval.cohort_ids:
        return retrieval

    kept = [
        (i, s)
        for i, s in zip(retrieval.cohort_ids, retrieval.cohort_similarities)
        if i != doc_id
    ]
    return dataclasses.replace(
        retrieval,
        cohort_ids=[i for i, _ in kept],
        cohort_similarities=[s for _, s in kept],
    )


# --- outcomes ----------------------------------------------------------------

@dataclass(frozen=True)
class HeldoutOutcome:
    doc_id: str
    expected_anchor: str
    expected_family: str
    retrieved: list[str]
    retrieved_families: list[str]
    top_similarity: float
    #: What the intent branch actually scored this known scam at. Retrieval finding the
    #: right document says nothing about whether the call was scored as risky, and until
    #: this existed the harness measured precision and false positives with no recall
    #: axis at all.
    risk: float = 0.0
    lang: str = "en"

    @property
    def rank(self) -> int | None:
        return rank_of(self.expected_anchor, self.retrieved)

    @property
    def strict_hit(self) -> bool:
        return self.rank is not None

    @property
    def family_hit(self) -> bool:
        return self.expected_family in self.retrieved_families

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "expected_anchor": self.expected_anchor,
            "expected_family": self.expected_family,
            "retrieved": self.retrieved,
            "rank": self.rank,
            "strict_hit": self.strict_hit,
            "family_hit": self.family_hit,
            "top_similarity": round(self.top_similarity, 4),
            "risk": round(self.risk, 4),
            "lang": self.lang,
        }


@dataclass(frozen=True)
class BenignOutcome:
    doc_id: str
    risk: float
    flagged: bool
    lang: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "risk": round(self.risk, 4),
            "flagged": self.flagged,
            "lang": self.lang,
        }


@dataclass(frozen=True)
class CalibrationOutcome:
    name: str
    risk: float
    comparator: str
    target: float

    @property
    def passed(self) -> bool:
        return self.risk >= self.target if self.comparator == ">=" else self.risk <= self.target

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "risk": round(self.risk, 4),
            "target": f"{self.comparator} {self.target}",
            "passed": self.passed,
        }


@dataclass(frozen=True)
class Report:
    encoder: str
    k: int
    amber_floor: float
    heldout: list[HeldoutOutcome] = field(default_factory=list)
    benign: list[BenignOutcome] = field(default_factory=list)
    calibration: list[CalibrationOutcome] = field(default_factory=list)
    corpus_counts: dict[str, int] = field(default_factory=dict)

    @property
    def p_at_k_strict(self) -> float:
        return mean(o.strict_hit for o in self.heldout)

    @property
    def p_at_k_family(self) -> float:
        return mean(o.family_hit for o in self.heldout)

    @property
    def mrr(self) -> float:
        return mean(1.0 / o.rank if o.rank else 0.0 for o in self.heldout)

    @property
    def benign_false_positive_rate(self) -> float:
        return mean(o.flagged for o in self.benign)

    # --- recall: does a known scam actually score as one? --------------------
    # Every held-out document IS a scam. P@k says the right advisory was retrieved; it
    # says nothing about the number the user sees. A system can retrieve perfectly and
    # still score every call green.

    @property
    def scam_recall_amber(self) -> float:
        """Fraction of known scams reaching at least the caution band."""
        return mean(o.risk >= self.amber_floor for o in self.heldout)

    @property
    def scam_recall_high_risk(self) -> float:
        return mean(o.risk >= thresholds.SCRIPT_HIGH_RISK for o in self.heldout)

    @property
    def recall_by_lang(self) -> dict[str, tuple[int, float]]:
        """Amber recall per language — the language-bias guard, distributionally.

        Two hand-picked Devanagari strings with an invented 0.90 target replaced by the
        actual property: a scam must not score lower for being in Hindi. A gap between
        these rows is the bias, with a sample behind it.
        """
        langs = sorted({o.lang for o in self.heldout})
        out: dict[str, tuple[int, float]] = {}
        for lang in langs:
            rows = [o for o in self.heldout if o.lang == lang]
            out[lang] = (len(rows), mean(o.risk >= self.amber_floor for o in rows))
        return out

    @property
    def silent_scams(self) -> list[str]:
        """Known scams the user would be shown no concern about at all."""
        return [o.doc_id for o in self.heldout if o.risk < self.amber_floor]

    @property
    def misses(self) -> list[str]:
        return [o.doc_id for o in self.heldout if not o.strict_hit]

    @property
    def false_positives(self) -> list[str]:
        return [o.doc_id for o in self.benign if o.flagged]

    def to_dict(self) -> dict[str, Any]:
        return {
            "encoder": self.encoder,
            "k": self.k,
            "amber_floor": self.amber_floor,
            "corpus_counts": self.corpus_counts,
            "p_at_k_strict": round(self.p_at_k_strict, 4),
            "p_at_k_family": round(self.p_at_k_family, 4),
            "mrr": round(self.mrr, 4),
            "benign_false_positive_rate": round(self.benign_false_positive_rate, 4),
            "scam_recall_amber": round(self.scam_recall_amber, 4),
            "scam_recall_high_risk": round(self.scam_recall_high_risk, 4),
            "recall_by_lang": {
                k: [n, round(r, 4)] for k, (n, r) in self.recall_by_lang.items()
            },
            "silent_scams": self.silent_scams,
            "misses": self.misses,
            "false_positives": self.false_positives,
            "heldout": [o.to_dict() for o in self.heldout],
            "benign": [o.to_dict() for o in self.benign],
            "calibration": [o.to_dict() for o in self.calibration],
        }


# --- the three passes ---------------------------------------------------------

def _resolved_anchor(corpus: Corpus, doc_id: str) -> str:
    """The anchor a retrieved document cites. A variant counts for its anchor."""
    return corpus.resolve_citation(doc_id).playbook_id


def evaluate_heldout(retriever: Retriever, corpus: Corpus, k: int) -> list[HeldoutOutcome]:
    outcomes: list[HeldoutOutcome] = []
    for doc in corpus.heldout:
        retrieval = retriever.search(doc.text, k=k)
        anchors = [_resolved_anchor(corpus, p.playbook_id) for p in retrieval.playbooks]
        scored = score_script(doc.text, retrieval, find_markers(doc.text))
        outcomes.append(
            HeldoutOutcome(
                doc_id=doc.id,
                expected_anchor=doc.expected_anchor or "",
                expected_family=doc.scam_family,
                retrieved=anchors,
                retrieved_families=[corpus.get(a).scam_family for a in anchors],
                top_similarity=retrieval.top_similarity,
                risk=scored.risk,
                lang=doc.lang,
            )
        )
    return outcomes


def evaluate_benign(retriever: Retriever, corpus: Corpus, k: int) -> list[BenignOutcome]:
    """Score every benign transcript as if it were a live call — leave-one-out."""
    outcomes: list[BenignOutcome] = []
    for doc in corpus.benign:
        retrieval = without_self(retriever.search(doc.text, k=k), doc.id)
        result = score_script(doc.text, retrieval, find_markers(doc.text))
        outcomes.append(
            BenignOutcome(
                doc_id=doc.id,
                risk=result.risk,
                flagged=result.risk >= thresholds.AMBER_FLOOR,
                lang=doc.lang,
            )
        )
    return outcomes


def evaluate_calibration(retriever: Retriever, k: int) -> list[CalibrationOutcome]:
    outcomes: list[CalibrationOutcome] = []
    for name, text, comparator, target in CALIBRATION_CASES:
        result = score_script(text, retriever.search(text, k=k), find_markers(text))
        outcomes.append(CalibrationOutcome(name, result.risk, comparator, target))
    return outcomes


def evaluate(retriever: Retriever, corpus: Corpus, k: int | None = None) -> Report:
    """Run all three passes. Pure with respect to the corpus; writes nothing."""
    k = thresholds.RAG_TOP_K if k is None else k
    return Report(
        encoder=type(retriever._encoder).__name__,  # noqa: SLF001 - reporting only
        k=k,
        amber_floor=thresholds.AMBER_FLOOR,
        heldout=evaluate_heldout(retriever, corpus, k),
        benign=evaluate_benign(retriever, corpus, k),
        calibration=evaluate_calibration(retriever, k),
        corpus_counts=_counts(corpus),
    )


def _counts(corpus: Corpus) -> dict[str, int]:
    indexed = corpus.retrievable
    return {
        "anchors_total": len(corpus.anchors),
        "anchors_indexed": sum(1 for d in indexed if not d.derived),
        "variants": sum(1 for d in indexed if d.derived),
        "benign": len(corpus.benign),
        "heldout": len(corpus.heldout),
        "families": len({d.scam_family for d in indexed}),
    }


# --- reporting ----------------------------------------------------------------

def _script_mix(docs: list[CorpusDoc]) -> str:
    counts: dict[str, int] = {}
    for doc in docs:
        counts[doc.lang] = counts.get(doc.lang, 0) + 1
    return "  ".join(f"{lang} {n}" for lang, n in sorted(counts.items()))


def render(report: Report, corpus: Corpus, baseline: dict[str, Any] | None = None) -> str:
    lines: list[str] = []
    add = lines.append

    def delta(key: str, value: float, higher_is_better: bool = True) -> str:
        if not baseline or key not in baseline:
            return ""
        change = value - float(baseline[key])
        if abs(change) < 1e-9:
            return "   (unchanged)"
        good = change > 0 if higher_is_better else change < 0
        return f"   ({change:+.3f} {'better' if good else 'WORSE'})"

    counts = report.corpus_counts
    add(f"encoder {report.encoder}   k={report.k}   amber floor {report.amber_floor}")
    add(
        f"corpus  {counts['anchors_indexed']} indexed anchors + {counts['variants']} "
        f"variants over {counts['families']} families · {counts['benign']} benign · "
        f"{counts['heldout']} held-out"
    )
    add(f"        scam    {_script_mix(corpus.retrievable)}")
    add(f"        benign  {_script_mix(corpus.benign)}")
    add("")

    add("RETRIEVAL")
    add(f"  P@{report.k} strict          {report.p_at_k_strict:6.1%}"
        + delta("p_at_k_strict", report.p_at_k_strict))
    add(f"  P@{report.k} family-level    {report.p_at_k_family:6.1%}"
        + delta("p_at_k_family", report.p_at_k_family))
    add(f"  MRR                   {report.mrr:6.3f}" + delta("mrr", report.mrr))
    if report.misses:
        add("  missed:")
        for outcome in report.heldout:
            if not outcome.strict_hit:
                add(f"    {outcome.doc_id:32} wanted {outcome.expected_anchor}")
                add(f"    {'':32} got    {', '.join(outcome.retrieved) or '(nothing)'}")
    add("")

    add("SCAM RECALL  (50 held-out transcripts, all known scams)")
    add(f"  scored >= amber       {report.scam_recall_amber:6.1%}"
        + delta("scam_recall_amber", report.scam_recall_amber))
    add(f"  scored >= high risk   {report.scam_recall_high_risk:6.1%}"
        + delta("scam_recall_high_risk", report.scam_recall_high_risk))
    add("  by language:")
    for lang, (n, rate) in report.recall_by_lang.items():
        add(f"    {lang:8} n={n:<3} {rate:6.1%}")
    if report.silent_scams:
        add(f"  scored below amber — the user would see no concern at all:")
        for outcome in sorted(report.heldout, key=lambda o: o.risk):
            if outcome.risk < report.amber_floor:
                add(f"    {outcome.risk:.3f}  {outcome.doc_id}")
    add("")

    add("BENIGN COHORT  (leave-one-out)")
    add(
        f"  false positives       {report.benign_false_positive_rate:6.1%}  "
        f"({len(report.false_positives)}/{len(report.benign)} at or above "
        f"{report.amber_floor})"
        + delta("benign_false_positive_rate", report.benign_false_positive_rate, False)
    )
    for outcome in sorted(report.benign, key=lambda o: -o.risk)[:5]:
        flag = "FP" if outcome.flagged else "  "
        add(f"    {flag} {outcome.risk:.3f}  {outcome.doc_id}")
    add("")

    add("CALIBRATION  (PLAN.md §5.1 — TUNING set: necessary, not evidence)")
    for row in report.calibration:
        add(
            f"  {'ok ' if row.passed else 'FAIL'}  {row.name:18} {row.risk:.3f}  "
            f"target {row.comparator} {row.target}"
        )
    return "\n".join(lines)


def _build_retriever(corpus: Corpus, force_fake: bool) -> Retriever:
    """Real encoder when the checkpoint is present, stand-in otherwise, always stated."""
    if not force_fake:
        from nlp_rag.embed import load_encoder

        encoder = load_encoder()
        if encoder is not None:
            from nlp_rag import index_store

            cached = index_store.load(
                *index_store.default_paths(),
                expect_encoder=index_store.encoder_id(encoder),
            )
            return Retriever(
                encoder,
                corpus,
                vectors=cached.vectors if cached else None,
                hashes=cached.hashes if cached else None,
            )

    from nlp_rag.tests.fakes import FakeEncoder

    return Retriever(FakeEncoder(), corpus)


#: How far a validation metric may drift before a run is called a regression. Wide
#: enough to absorb one document moving across a boundary in a 50-query set, narrow
#: enough that a real slide is caught.
REGRESSION_TOLERANCE = 0.03


def regressions(report: Report, baseline: dict[str, Any] | None) -> list[str]:
    """Validation metrics that got materially worse than the recorded baseline.

    The exit code cannot rest on the calibration rows alone. Those three strings are what
    `SCRIPT_Z0` was fitted against, so they pass by construction — the harness reported a
    clean run while 36% of known scams were scoring below the caution floor. These are the
    metrics that were never consulted during tuning, and regression against the last
    recorded state is the honest gate: it needs no invented absolute target.
    """
    if not baseline:
        return []

    # Same reasoning as `expect_encoder`: a metric is only comparable against a baseline
    # measured on the same data. Growing the held-out set from 16 to 50 moved P@3 from
    # 100% to 94% -- not a regression, a harder test -- and comparing across the two
    # reported three failures that had not happened.
    before_counts = baseline.get("corpus_counts", {})
    for key in ("heldout", "benign"):
        if before_counts.get(key) != report.corpus_counts.get(key):
            logger.warning(
                "baseline has %s %s, this run has %s; not comparing",
                before_counts.get(key),
                key,
                report.corpus_counts.get(key),
            )
            return []

    checks = (
        ("p_at_k_strict", report.p_at_k_strict, True),
        ("p_at_k_family", report.p_at_k_family, True),
        ("scam_recall_amber", report.scam_recall_amber, True),
        ("scam_recall_high_risk", report.scam_recall_high_risk, True),
        ("benign_false_positive_rate", report.benign_false_positive_rate, False),
    )
    out: list[str] = []
    for key, value, higher_is_better in checks:
        if key not in baseline:
            continue
        before = float(baseline[key])
        drift = value - before if higher_is_better else before - value
        if drift < -REGRESSION_TOLERANCE:
            out.append(f"{key} {before:.3f} -> {value:.3f}")
    return out


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = sys.argv[1:] if argv is None else argv
    corpus = load_corpus(CORPUS_DIR)
    report = evaluate(_build_retriever(corpus, force_fake="--fake" in argv), corpus)

    baseline: dict[str, Any] | None = None
    if BASELINE_PATH.is_file():
        try:
            stored = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
            # Never compare across encoders: the two score distributions are unrelated,
            # and a diff between them reads as a dramatic regression or improvement that
            # nothing in the corpus caused.
            if stored.get("encoder") == report.encoder:
                baseline = stored
            else:
                print(
                    f"baseline was captured under {stored.get('encoder')}, this run is "
                    f"{report.encoder} — not comparing\n"
                )
        except (json.JSONDecodeError, OSError):
            pass

    print(render(report, corpus, baseline))

    if "--json" in argv:
        BASELINE_PATH.write_text(
            json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nbaseline written to {BASELINE_PATH}")

    failures = [f"calibration {r.name}" for r in report.calibration if not r.passed]
    failures += regressions(report, baseline)
    if failures:
        print("\nFAIL: " + "; ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())


def evaluate_from_disk(force_fake: bool = False) -> Report:
    """Convenience for a REPL or another module: load, build, evaluate."""
    corpus = load_corpus(CORPUS_DIR)
    return evaluate(_build_retriever(corpus, force_fake), corpus)
