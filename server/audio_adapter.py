"""
server/audio_adapter.py — Maps A's data models to C's frozen data contracts.

Because contracts.py is frozen and A built against a different version,
we define A's vocabulary here, monkeypatch contracts.py so A's imports succeed,
and provide mapping functions to C's types.
"""

import sys
import contracts
from pydantic import BaseModel
from typing import Literal, Optional, List
import config

# ==============================================================================
# 1. A's Data Models (Monkeypatched into contracts.py)
# ==============================================================================

class SpeakerSignal(BaseModel):
    best_match_id: Optional[str] = None
    best_match_name: Optional[str] = None
    relationship: Optional[str] = None
    raw_cosine: float = 0.0
    norm_score: float = 0.0
    verdict: Literal["match", "mismatch", "unknown"] = "unknown"
    flagged_voice_hits: int = 0
    condition_used: str = "wb"

class SpoofSegment(BaseModel):
    start_s: float
    end_s: float
    label: Literal["human", "synthetic"]
    score: float

class SpoofSignal(BaseModel):
    score: float = 0.5
    peak: float = 0.5
    max_synth_run_s: float = 0.0
    timeline: List[SpoofSegment] = []
    verdict: Literal["bonafide", "synthetic", "partial_synthetic", "uncertain"] = "uncertain"
    n_chunks: int = 0

class Person(BaseModel):
    person_id: str
    name: str
    relationship: str = "family"
    enrolled_at: str = ""
    n_samples: int = 0
    conditions: List[str] = ["wb", "nb8k"]

# Inject into contracts module
contracts.SpeakerSignal = SpeakerSignal
contracts.SpoofSegment = SpoofSegment
contracts.SpoofSignal = SpoofSignal
contracts.Person = Person


# ==============================================================================
# 2. Adapter Functions (A's Models -> C's Models)
# ==============================================================================

def to_speaker_result(signal: SpeakerSignal) -> contracts.SpeakerVerificationResult:
    """Map A's SpeakerSignal to C's SpeakerVerificationResult."""
    # verdict matches Literal["match", "mismatch", "unknown"] in A and contracts.SpeakerVerdict in C.
    # We can just pass it as string, Pydantic will coerce to enum.
    
    # Derive risk
    # unknown maps to 0.5.
    # For match/mismatch, we can use the norm_score mapped against thresholds.
    if signal.verdict == "unknown":
        risk = 0.5
    elif signal.verdict == "mismatch":
        risk = 0.85 # High risk
    else:
        risk = 0.15 # Low risk (match)
        
    is_replay = signal.raw_cosine > config.REPLAY_COSINE_THRESHOLD

    return contracts.SpeakerVerificationResult(
        verdict=signal.verdict,
        matched_person_id=signal.best_match_id,
        matched_person_name=signal.best_match_name,
        raw_score=signal.raw_cosine,
        norm_score=signal.norm_score,
        risk=risk,
        is_replay=is_replay,
        details={
            "relationship": signal.relationship,
            "flagged_voice_hits": signal.flagged_voice_hits,
            "condition_used": signal.condition_used
        }
    )

def to_spoof_result(signal: SpoofSignal) -> contracts.AntiSpoofResult:
    """Map A's SpoofSignal to C's AntiSpoofResult."""
    # map timelines
    timeline = []
    for s in signal.timeline:
        timeline.append(contracts.SpoofSegment(
            start_s=s.start_s,
            end_s=s.end_s,
            score=s.score,
            is_synthetic=(s.label == "synthetic")
        ))
        
    return contracts.AntiSpoofResult(
        median_score=signal.score,
        peak_score=signal.peak,
        max_synth_run_s=signal.max_synth_run_s,
        raw_score=signal.score,
        norm_score=signal.score,
        risk=signal.score, # score is median probability, so risk is just the score
        is_synthetic=(signal.verdict in ("synthetic", "partial_synthetic")),
        timeline=timeline,
        details={
            "verdict": signal.verdict,
            "n_chunks": signal.n_chunks
        }
    )
