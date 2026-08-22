"""Turn a retrieval result and a set of markers into a calibrated script risk.

The pipeline, from `nlp_rag/PLAN.md` §5:

    z            = (top_similarity − mean(cohort)) / std(cohort)
    r_ret        = sigmoid((z − z0) / tau),  ceilinged
    marker_delta = cap * tanh(Σ incriminating − Σ |exculpatory|)
    risk         = clip(r_ret + marker_delta)

Three rules that are easy to lose and expensive to lose:

**Normalisation is load-bearing.** Raw BGE-m3 cosines sit in a compressed band, so an
un-normalised similarity maps every transcript to mid-range and the whole product scores
amber. The benign cohort supplies the background the score is read against.

**Markers are suppressed, not double-counted.** If the top-retrieved playbook already
exemplifies a marker, that marker is *why* the document retrieved. Counting it again
inflates risk exactly where the signal is strongest. Suppression is one-directional:
exculpatory markers always count, because risk-lowering evidence must never be silently
discarded.

**Markers alone cannot reach red.** Red with no retrieved document is a verdict with no
citation, and `PRD.md` NG2 forbids a verdict we cannot show evidence for.
"""

from __future__ import annotations

import math

from contracts import MarkerMatch, MarkerType, ScriptAnalysisResult
from nlp_rag import thresholds
from nlp_rag.retrieve import RetrievalResult


def abstain(reason: str, language: str = "en") -> ScriptAnalysisResult:
    """The abstention sentinel B owes C.

    `server/orchestrator.py` reads `details.get("available", True) is not False` and, on
    False, drops `w_text`, renormalises the remaining weights, and forces the CM gate's
    `intent` to a neutral 0.5 rather than 0.0.

    The default is `True`, so **silence reads as available**. Every path that returns
    `risk=0.0` without having actually analysed anything must come through here, or a
    dead ASR branch is read as a benign call and the trust score rises.
    """
    from nlp_rag.warnings import warnings_by_band

    result = ScriptAnalysisResult.neutral()
    result.details["available"] = False
    result.details["reason"] = reason
    # C reads this key unconditionally to pick copy for the fused band. An abstention
    # still needs it present: fusion may land on a risky band from the other two
    # branches alone, and that verdict still has to be speakable.
    result.details["vernacular_warnings"] = warnings_by_band(language)
    return result


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def _cohort_stats(cohort: list[float]) -> tuple[float, float] | None:
    """Mean and a floored standard deviation, or None when there is no cohort."""
    if not cohort:
        return None
    mean = sum(cohort) / len(cohort)
    variance = sum((c - mean) ** 2 for c in cohort) / len(cohort)
    return mean, max(math.sqrt(variance), thresholds.MIN_COHORT_STD)


def _retrieval_risk(retrieval: RetrievalResult) -> tuple[float, float | None]:
    """s-normalised retrieval risk, and the z-score it came from."""
    stats = _cohort_stats(retrieval.cohort_similarities)
    if stats is None or not retrieval.playbooks:
        return 0.0, None

    mean, std = stats
    z = (retrieval.top_similarity - mean) / std
    raw = _sigmoid((z - thresholds.SCRIPT_Z0) / thresholds.SCRIPT_TAU)
    return min(raw, thresholds.R_RET_CEILING), z


def _marker_delta(
    markers: list[MarkerMatch], already_counted: set[str]
) -> tuple[float, float]:
    """Bounded, squashed net contribution of the markers. Returns (delta, net weight)."""
    net = 0.0
    for marker in markers:
        if marker.marker_type is MarkerType.INCRIMINATING:
            if marker.marker_id in already_counted:
                continue  # the retrieval score already reflects this
            net += marker.weight
        else:
            net += marker.weight  # negative; never suppressed
    return thresholds.MARKER_DELTA_CAP * math.tanh(net), net


def _summarise(risk: float, incriminating: list[MarkerMatch], playbooks: list) -> str:
    if not incriminating and not playbooks:
        return "No significant fraud markers detected"
    if risk >= thresholds.SCRIPT_HIGH_RISK:
        return "High-severity scam script matched with corroborating citation"
    if risk >= thresholds.CORROBORATION_FLOOR:
        return "Partial match to a known scam script; verify before acting"
    if incriminating:
        return "Isolated risk markers present without corroborating playbook"
    return "No significant fraud markers detected"


def score_script(
    text: str,
    retrieval: RetrievalResult,
    markers: list[MarkerMatch],
) -> ScriptAnalysisResult:
    """Compute intent risk. Pure, stateless, and never raises."""
    incriminating = [m for m in markers if m.marker_type is MarkerType.INCRIMINATING]
    exculpatory = [m for m in markers if m.marker_type is MarkerType.EXCULPATORY]

    if not text or not text.strip():
        return abstain("empty_text")

    r_ret, z = _retrieval_risk(retrieval)
    suppressed = {
        m.marker_id
        for m in incriminating
        if m.marker_id in set(retrieval.top_doc_markers)
    }
    delta, net_weight = _marker_delta(markers, suppressed)

    risk = r_ret + delta

    # Markers alone may raise concern but not certainty.
    capped = False
    if r_ret < thresholds.CORROBORATION_FLOOR and risk >= thresholds.SCRIPT_HIGH_RISK:
        risk = thresholds.SCRIPT_HIGH_RISK - 0.01
        capped = True

    risk = max(thresholds.RISK_FLOOR, min(1.0, risk))

    # Top-k always returns something — that is what top-k does. A weak hit passed
    # through to the panel renders as evidence the score does not support, so a
    # citation must clear BOTH gates:
    #   - corroboration: clearly above the benign cohort background (cohort-relative)
    #   - config.RAG_SIMILARITY_THRESHOLD: strong in absolute cosine terms
    # The two fail for different reasons, and either one alone lets something through.
    corroborated = r_ret >= thresholds.CORROBORATION_FLOOR
    playbooks = (
        [
            p
            for p in retrieval.playbooks
            if p.similarity_score >= thresholds.RAG_SIMILARITY_THRESHOLD
        ]
        if corroborated
        else []
    )

    return ScriptAnalysisResult(
        risk=risk,
        incriminating_markers=incriminating,
        exculpatory_markers=exculpatory,
        playbooks=playbooks,
        intent_summary=_summarise(risk, incriminating, playbooks),
        details={
            # The branch analysed real text and produced real evidence. Fusion keeps
            # w_text and gates the CM branch on this risk rather than a neutral 0.5.
            "available": True,
            "z": round(z, 4) if z is not None else None,
            "r_ret": round(r_ret, 4),
            "marker_delta": round(delta, 4),
            "marker_net_weight": round(net_weight, 4),
            "suppressed_markers": sorted(suppressed),
            "cohort_size": len(retrieval.cohort_similarities),
            "corroborated": corroborated,
            "capped_uncorroborated": capped,
        },
    )


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    import sys
    from pathlib import Path

    from nlp_rag.corpus_loader import load_corpus
    from nlp_rag.markers import find_markers
    from nlp_rag.retrieve import Retriever
    from nlp_rag.tests.fakes import FakeEncoder

    samples = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else [
        "Papa emergency ho gaya hai, police ne pakad liya hai. "
        "Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe.",
        "Hi Ma, I just reached the office. Will be home by 7 PM today.",
        "Dear customer, your HDFC Bank statement for account ending 4402 is ready.",
        "Don't tell anyone. Share the OTP now. You will be arrested otherwise.",
    ]
    retriever = Retriever(FakeEncoder(), load_corpus(Path(__file__).parent / "corpus"))
    for sample in samples:
        result = score_script(sample, retriever.search(sample, k=3), find_markers(sample))
        print(f"\nrisk {result.risk:.3f}  {result.intent_summary}")
        print(f"  {sample[:78]}")
        print(f"  {result.details}")
