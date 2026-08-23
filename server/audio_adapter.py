"""server/audio_adapter.py — translate `audio_ml`'s vocabulary into C's contracts.

A wrote `audio_ml/` against a divergent copy of `contracts.py` that the merge
resolved away. Rather than edit A's package to speak C's contract, or unfreeze the
contract to speak A's, this module is the single boundary where the two meet:
A's models live in `audio_ml/signals.py`, C's in `contracts.py`, and everything
crossing between them passes through the two functions below.

**This module does not mutate `contracts`.** It used to — it defined A's models
here and assigned them onto the contracts module at import time, which broke twice
over. `orchestrator.py` imported `audio_ml.api` on the line before this one, so the
patch had not run when A's modules needed it; and the patch overwrote
`contracts.SpoofSegment`, a class C's own code depends on, with an incompatible
one. Both failures were caught by the orchestrator's `except` and returned
`.neutral()`, whose verdict is `unknown` — indistinguishable from a working branch
that met a stranger. See `server/tests/test_audio_adapter.py`.

Owned by C. A's package needs no knowledge of this file.
"""

from __future__ import annotations

import config
import contracts
from audio_ml.signals import SpeakerSignal, SpoofSignal


def to_speaker_result(signal: SpeakerSignal) -> contracts.SpeakerVerificationResult:
    """Map A's `SpeakerSignal` onto C's `SpeakerVerificationResult`.

    `risk` is the one field A does not supply and fusion requires, so it is
    derived here from the verdict.

    **`unknown` maps to 0.5, never to 1.0.** CLAUDE.md is explicit that unknown is
    neutral rather than guilty: it means no enrolled person is close, which is the
    normal state for every genuine stranger — a real bank, a delivery driver, a
    doctor. Scoring it as guilty turns all of them red and the product becomes
    noise. `SpeakerVerificationResult.neutral()` agrees, defaulting risk to 0.5.

    match/mismatch are deliberately *not* interpolated from `norm_score`. A's
    verifier has already applied `config.SPEAKER_MATCH_THRESHOLD` and
    `SPEAKER_UNKNOWN_FLOOR` to reach the verdict; re-deriving a risk from the same
    score against C's differently-scaled `ASV_*` thresholds would double-count one
    decision and disagree with it.
    """
    if signal.verdict == "unknown":
        risk = 0.5
    elif signal.verdict == "mismatch":
        risk = 0.85
    else:  # match
        risk = 0.15

    return contracts.SpeakerVerificationResult(
        verdict=signal.verdict,
        matched_person_id=signal.best_match_id,
        matched_person_name=signal.best_match_name,
        raw_score=signal.raw_cosine,
        norm_score=signal.norm_score,
        risk=risk,
        # Live speech scores 0.65–0.80; above the threshold it is a recording
        # being played back, not a person speaking.
        is_replay=signal.raw_cosine > config.REPLAY_COSINE_THRESHOLD,
        confidence=abs(risk - 0.5) * 2.0,  # 0.0 at neutral, 1.0 at either extreme
        details={
            "relationship": signal.relationship,
            "flagged_voice_hits": signal.flagged_voice_hits,
            "condition_used": signal.condition_used,
        },
    )


def to_spoof_result(signal: SpoofSignal) -> contracts.AntiSpoofResult:
    """Map A's `SpoofSignal` onto C's `AntiSpoofResult`.

    Both sides carry the three statistics the design mandates — median, peak and
    max contiguous synthetic run — because median alone hides hybrid attacks,
    where a scammer speaks normally and switches to a cloned voice only for the
    sensitive part of the call.

    The per-segment shapes differ: A labels a window `human`/`synthetic`, C stores
    an `is_synthetic` bool. Converting is this function's job and was the whole
    F2 defect.

    `uncertain` is not reported as synthetic. It means the model abstained, which
    is not evidence of synthesis — and with no checkpoint present that is exactly
    what `audio_ml/spoof.py` returns for everything.
    """
    return contracts.AntiSpoofResult(
        median_score=signal.score,
        peak_score=signal.peak,
        max_synth_run_s=signal.max_synth_run_s,
        raw_score=signal.score,
        norm_score=signal.score,
        risk=signal.score,
        is_synthetic=signal.verdict in ("synthetic", "partial_synthetic"),
        timeline=[
            contracts.SpoofSegment(
                start_s=segment.start_s,
                end_s=segment.end_s,
                score=segment.score,
                is_synthetic=(segment.label == "synthetic"),
            )
            for segment in signal.timeline
        ],
        details={
            "verdict": signal.verdict,
            "n_chunks": signal.n_chunks,
        },
    )


if __name__ == "__main__":  # pragma: no cover - CLI smoke test
    from audio_ml.signals import SpoofSegment

    for verdict in ("match", "mismatch", "unknown"):
        mapped = to_speaker_result(SpeakerSignal(verdict=verdict, raw_cosine=0.9, norm_score=0.9))
        print(f"{verdict:<9} → risk {mapped.risk:.2f}  replay={mapped.is_replay}")

    spoof = to_spoof_result(
        SpoofSignal(
            score=0.62,
            peak=0.91,
            max_synth_run_s=4.0,
            verdict="partial_synthetic",
            timeline=[SpoofSegment(start_s=0.0, end_s=3.0, label="synthetic", score=0.91)],
        )
    )
    print(f"spoof     → risk {spoof.risk:.2f}  synthetic={spoof.is_synthetic} "
          f"timeline={len(spoof.timeline)} segment(s)")
