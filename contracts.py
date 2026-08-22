"""
contracts.py — THE FROZEN DATA CONTRACT

Four people code against this file. Do NOT rename, reorder or "improve" any
field. Contract changes are announced in the team chat with the words
"CONTRACT CHANGE" before being made.

Owner: Member C.  Frozen at H0:45.
"""

from __future__ import annotations
from pydantic import BaseModel
from typing import Literal, Optional, List

Band = Literal["green", "amber", "red", "unverified", "insufficient"]
Mode = Literal["identity_check", "authority_check"]


class AudioQuality(BaseModel):
    sample_rate: int = 16000
    speech_s: float = 0.0
    snr_db: float = 0.0
    condition: Literal["wb", "nb8k"] = "wb"
    insufficient: bool = False


class SpeakerSignal(BaseModel):
    best_match_id: Optional[str] = None
    best_match_name: Optional[str] = None
    relationship: Optional[str] = None          # family | friend | colleague
    raw_cosine: float = 0.0                     # > 0.95 implies replay
    norm_score: float = 0.0                     # after s-normalisation
    verdict: Literal["match", "mismatch", "unknown"] = "unknown"
    flagged_voice_hits: int = 0
    condition_used: str = "wb"


class SpoofSegment(BaseModel):
    start_s: float
    end_s: float
    label: Literal["human", "synthetic"]
    score: float


class SpoofSignal(BaseModel):
    score: float = 0.5                          # median — the headline
    peak: float = 0.5                           # max — catches short bursts
    max_synth_run_s: float = 0.0                # longest synthetic stretch
    timeline: List[SpoofSegment] = []
    verdict: Literal["bonafide", "synthetic", "partial_synthetic", "uncertain"] = "uncertain"
    n_chunks: int = 0


class CorpusMatch(BaseModel):
    doc_id: str
    family: str
    title: str
    similarity: float
    source_url: str


class Marker(BaseModel):
    code: str
    label: str
    direction: Literal["incriminating", "exculpatory"]
    evidence_span: str = ""


class ScriptSignal(BaseModel):
    top_matches: List[CorpusMatch] = []
    markers: List[Marker] = []
    risk: float = 0.0


class TranscriptResult(BaseModel):
    text: str = ""
    language: str = "unknown"
    segments: List[dict] = []


class ReasonCode(BaseModel):
    code: str
    severity: Literal["high", "med", "low"]
    headline: str
    detail: str
    citation: Optional[str] = None


class FusionResult(BaseModel):
    trust_score: int = 50
    band: Band = "amber"
    mode: Mode = "identity_check"
    risk_breakdown: dict = {}
    weights_used: dict = {}


class Actions(BaseModel):
    challenge_question: Optional[str] = None
    warning_audio_url: Optional[str] = None
    report_id: Optional[str] = None


class Person(BaseModel):
    person_id: str
    name: str
    relationship: str = "family"
    enrolled_at: str = ""
    n_samples: int = 0
    conditions: List[str] = ["wb", "nb8k"]


class SessionVerdict(BaseModel):
    session_id: str
    duration_s: float = 0.0
    audio_quality: AudioQuality = AudioQuality()
    trust_score: int = 50
    band: Band = "amber"
    mode: Mode = "identity_check"
    speaker: SpeakerSignal = SpeakerSignal()
    spoof: SpoofSignal = SpoofSignal()
    script: ScriptSignal = ScriptSignal()
    transcript: TranscriptResult = TranscriptResult()
    reason_codes: List[ReasonCode] = []
    actions: Actions = Actions()
