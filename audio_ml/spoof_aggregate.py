"""
audio_ml/spoof_aggregate.py — temporal aggregation for the authenticity branch

WHY THIS EXISTS
---------------
The original spec aggregated per-chunk anti-spoof scores with a MEDIAN, chosen
for robustness against one bad chunk. That is correct for a fully-synthetic or
fully-human call, and exactly wrong for a hybrid one.

Hybrid attack: the scammer speaks normally, switches to a cloned voice for the
sensitive part ("read me the OTP"), then switches back. If 25% of chunks are
synthetic, the median returns "bonafide" and we miss precisely the attack that
matters most.

Fix: report THREE statistics plus a timeline.
    score           = median   -> stable headline, resists single bad chunks
    peak            = max      -> catches a short synthetic burst
    max_synth_run_s = longest contiguous synthetic window -> the real signal
    timeline        = merged segments -> drives the UI strip

The UI strip is also the best visual in the build: watching it turn red exactly
when the caller asks for the OTP is a very good ten seconds of demo.

Owner: Member A.
"""

from __future__ import annotations
import statistics
from typing import List, Tuple, Optional

try:
    from config import SPOOF_SYNTHETIC_THRESHOLD, SPOOF_BONAFIDE_THRESHOLD
except Exception:
    SPOOF_SYNTHETIC_THRESHOLD = 0.65
    SPOOF_BONAFIDE_THRESHOLD = 0.35

# A synthetic stretch shorter than this is noise, not an attack.
MIN_SYNTH_RUN_S = 3.0
# Don't emit hundreds of one-chunk segments; merge anything closer than this.
MERGE_GAP_S = 1.0


def aggregate(
    chunk_scores: List[float],
    chunk_spans: List[Tuple[float, float]],
    threshold: float = SPOOF_SYNTHETIC_THRESHOLD,
):
    """
    chunk_scores : per-chunk P(synthetic), same length as chunk_spans
    chunk_spans  : [(start_s, end_s), ...] in call time

    Returns a SpoofSignal (or a dict if contracts.py is not importable yet).
    Never raises — on empty or malformed input, returns the neutral default.
    """
    try:
        return _aggregate_inner(chunk_scores, chunk_spans, threshold)
    except Exception as e:  # pragma: no cover
        import logging
        logging.exception("spoof aggregation failed: %s", e)
        return _signal(0.5, 0.5, 0.0, [], "uncertain", 0)


def _aggregate_inner(chunk_scores, chunk_spans, threshold):
    if not chunk_scores:
        return _signal(0.5, 0.5, 0.0, [], "uncertain", 0)

    n = min(len(chunk_scores), len(chunk_spans))
    scores = [float(s) for s in chunk_scores[:n]]
    spans = list(chunk_spans[:n])

    median = statistics.median(scores)
    peak = max(scores)

    segments = _merge_segments(scores, spans, threshold)
    max_run = max((e - s for s, e, lab in segments if lab == "synthetic"),
                  default=0.0)

    # ---- verdict ---------------------------------------------------------
    if median >= threshold:
        verdict = "synthetic"
    elif max_run >= MIN_SYNTH_RUN_S:
        # The call is mostly human but contains a sustained synthetic stretch.
        verdict = "partial_synthetic"
    elif median <= SPOOF_BONAFIDE_THRESHOLD:
        verdict = "bonafide"
    else:
        verdict = "uncertain"

    timeline = [
        {"start_s": round(s, 2), "end_s": round(e, 2), "label": lab,
         "score": round(sc, 3)}
        for s, e, lab, sc in _with_scores(segments, scores, spans)
    ]

    return _signal(median, peak, max_run, timeline, verdict, n)


def _merge_segments(scores, spans, threshold):
    """Label each chunk, then merge contiguous same-label runs."""
    labelled = [
        (spans[i][0], spans[i][1], "synthetic" if scores[i] >= threshold else "human")
        for i in range(len(scores))
    ]
    merged = []
    for start, end, lab in labelled:
        if merged and merged[-1][2] == lab and start - merged[-1][1] <= MERGE_GAP_S:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end), lab)
        else:
            merged.append((start, end, lab))
    return [tuple(m) for m in merged]


def _with_scores(segments, scores, spans):
    """Attach the mean chunk score belonging to each merged segment."""
    out = []
    for s, e, lab in segments:
        vals = [scores[i] for i in range(len(scores))
                if spans[i][0] >= s - 1e-6 and spans[i][1] <= e + 1e-6]
        out.append((s, e, lab, sum(vals) / len(vals) if vals else 0.5))
    return out


def _signal(score, peak, max_run, timeline, verdict, n_chunks):
    payload = {
        "score": round(float(score), 4),
        "peak": round(float(peak), 4),
        "max_synth_run_s": round(float(max_run), 2),
        "timeline": timeline,
        "verdict": verdict,
        "n_chunks": n_chunks,
    }
    try:
        from contracts import SpoofSignal
        return SpoofSignal(**payload)
    except Exception:
        return payload


# --------------------------------------------------------------------------
# Smoke test:  python -m audio_ml.spoof_aggregate
# --------------------------------------------------------------------------
if __name__ == "__main__":
    def spans(n, step=2.0, width=3.0):
        return [(i * step, i * step + width) for i in range(n)]

    # 12 chunks, human except a 4-chunk synthetic burst in the middle
    hybrid = [0.08, 0.11, 0.09, 0.14, 0.91, 0.94, 0.89, 0.92, 0.12, 0.10, 0.07, 0.13]
    r = aggregate(hybrid, spans(len(hybrid)))
    d = r if isinstance(r, dict) else r.model_dump()
    print("HYBRID :", d["verdict"],
          "| median", d["score"], "| peak", d["peak"],
          "| run", d["max_synth_run_s"], "s")
    for seg in d["timeline"]:
        print("   ", seg)

    allsynth = [0.9] * 8
    d2 = aggregate(allsynth, spans(8))
    d2 = d2 if isinstance(d2, dict) else d2.model_dump()
    print("SYNTH  :", d2["verdict"], "| median", d2["score"])

    human = [0.07] * 8
    d3 = aggregate(human, spans(8))
    d3 = d3 if isinstance(d3, dict) else d3.model_dump()
    print("HUMAN  :", d3["verdict"], "| median", d3["score"])
