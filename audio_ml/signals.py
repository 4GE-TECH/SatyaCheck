"""`audio_ml`'s own signal models — A's vocabulary, owned by A's package.

These four classes used to be imported from `contracts`, which does not define
them: `contracts.py` is C's frozen shared contract and speaks a different
vocabulary (`SpeakerVerificationResult`, `AntiSpoofResult`, `EnrolledPerson`).
A wrote `audio_ml/` against an earlier, divergent copy of `contracts.py` that was
resolved away during the merge, leaving every module in this package importing a
name that no longer existed.

The gap was papered over by monkeypatching these classes *onto* the contracts
module from `server/audio_adapter.py`. That failed two ways at once:

  * `server/orchestrator.py` imported `audio_ml.api` on the line *before* the
    adapter, so the patch had not run yet — ImportError, caught, branch dead.
  * the patch also overwrote `contracts.SpoofSegment`, a class C's own code uses,
    with an incompatible one.

Keeping them here instead means `audio_ml` imports on its own — which the seven
`scripts/` and `audio_ml/eval/test_scenarios.py` already assumed — and
`contracts.py` stays genuinely frozen. `server/audio_adapter.py` translates these
into C's vocabulary at the boundary, which is the one place the two should meet.

Nothing outside `audio_ml/` and `server/audio_adapter.py` should import this
module. C's contract remains the interface everyone else codes against.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

__all__ = [
    "SpeakerSignal",
    "SpoofSegment",
    "SpoofSignal",
    "Person",
    "FusionResult",
]


class SpeakerSignal(BaseModel):
    """Identity branch output.

    `verdict` has three values, and `unknown` is neutral rather than guilty — it
    means no enrolled person is close, which is the normal state for every
    genuine stranger. `server/audio_adapter.to_speaker_result` is where that
    becomes a risk number.
    """

    best_match_id: Optional[str] = None
    best_match_name: Optional[str] = None
    relationship: Optional[str] = None
    raw_cosine: float = 0.0
    norm_score: float = 0.0
    verdict: Literal["match", "mismatch", "unknown"] = "unknown"
    flagged_voice_hits: int = 0
    condition_used: str = "wb"


class SpoofSegment(BaseModel):
    """One scored window of the authenticity timeline.

    Note `label` where C's `contracts.SpoofSegment` has `is_synthetic`. The two
    are not interchangeable; the adapter converts.
    """

    start_s: float
    end_s: float
    label: Literal["human", "synthetic"]
    score: float


class SpoofSignal(BaseModel):
    """Authenticity branch output.

    Reports three statistics, not one. Median alone hides hybrid attacks, where a
    scammer switches to a cloned voice only for the sensitive part of the call —
    `peak` catches short bursts and `max_synth_run_s` is the real signal.
    """

    score: float = 0.5
    peak: float = 0.5
    max_synth_run_s: float = 0.0
    timeline: List[SpoofSegment] = Field(default_factory=list)
    verdict: Literal["bonafide", "synthetic", "partial_synthetic", "uncertain"] = "uncertain"
    n_chunks: int = 0


class Person(BaseModel):
    """An enrolled speaker as `audio_ml/enroll.py` stores it on disk.

    Metadata only. C's SQLite `EnrolledPerson` is authoritative for the UI and
    for shared secrets; this describes the `.npz` voiceprint beside it.
    """

    person_id: str
    name: str
    relationship: str = "family"
    enrolled_at: str = ""
    n_samples: int = 0
    conditions: List[str] = Field(default_factory=lambda: ["wb", "nb8k"])


class FusionResult(BaseModel):
    """A's fusion output.

    Present for completeness so `audio_ml/fusion.py` and
    `audio_ml/eval/test_scenarios.py` run standalone. **Not** what the product
    serves: `config.USE_REAL_FUSION` is False and C's `_compute_fusion` returns a
    `contracts.TrustScoreResult` instead. See `nlp_rag/NEEDS_FROM_A.md` item 8.
    """

    trust_score: float
    band: str
    mode: str
    risk_breakdown: Dict[str, Any] = Field(default_factory=dict)
    weights_used: Dict[str, float] = Field(default_factory=dict)
