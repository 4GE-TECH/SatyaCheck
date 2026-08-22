"""SatyaCheck — Core Data Contracts and Schemas

This module defines all shared Pydantic data models, enums, and neutral default
factories used across audio_ml, nlp_rag, server, and web API layers.

FROZEN FILE: Module boundaries and external interfaces rely on these exact types.
Public functions in all modules must return valid instances of these models and
never raise exceptions into callers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# =====================================================================
# Enums and Type Aliases
# =====================================================================

class SpeakerVerdict(str, Enum):
    """Speaker verification verdict.
    
    CRITICAL DOMAIN RULE:
    'unknown' is neutral (risk 0.5), not guilty. It signifies that no enrolled
    contact was closely matched, which is the normal state for any genuine stranger.
    """
    MATCH = "match"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class OperatingMode(str, Enum):
    """Operating mode selected automatically based on speaker identity.
    
    - 'identity_check': When caller claims or matches/mismatches an enrolled person.
      Weights: ASV 0.40, CM 0.35, Text 0.25
    - 'authority_check': When no enrolled person is matched ('unknown').
      Speaker branch abstains / minimizes weight. Weights: ASV 0.10, CM 0.45, Text 0.45
    """
    IDENTITY_CHECK = "identity_check"
    AUTHORITY_CHECK = "authority_check"


class TrustBand(str, Enum):
    """Trust level classification for user display.
    
    CRITICAL DOMAIN RULE:
    Never show 'verified' (green) in authority_check mode.
    If speech < 1.5s or SNR < 5dB, band is 'insufficient'.
    """
    VERIFIED = "verified"       # Green (high trust, verified identity)
    CAUTION = "caution"         # Amber (moderate risk or unusual request)
    SUSPICIOUS = "suspicious"   # Orange / Light Red (elevated spoof or scam markers)
    HIGH_RISK = "high_risk"     # Red (confirmed clone / severe scam intent)
    UNVERIFIED = "unverified"   # Grey (neutral stranger in authority_check)
    INSUFFICIENT = "insufficient"  # Grey (audio too short or noisy to evaluate)


class SignalType(str, Enum):
    """Source branch generating evidence."""
    IDENTITY = "identity"
    AUTHENTICITY = "authenticity"
    INTENT = "intent"
    QUALITY = "quality"
    META = "meta"


class MarkerType(str, Enum):
    """Linguistic marker direction.
    
    - INCRIMINATING: Raises scam risk (e.g., isolation demands, urgent UPI transfer, fake arrest).
    - EXCULPATORY: Lowers scam risk (e.g., inviting verification, 'call Papa', 'talk to doctor').
    """
    INCRIMINATING = "incriminating"
    EXCULPATORY = "exculpatory"


class SeverityLevel(str, Enum):
    """Severity level for reason codes and alerts."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AcousticCondition(str, Enum):
    """Acoustic condition for condition-matched voiceprint enrollment."""
    WIDEBAND_16K = "wideband_16k"
    NARROWBAND_8K = "narrowband_8k"
    CODEC_AMR_NB = "codec_amr_nb"
    CODEC_OPUS = "codec_opus"


# =====================================================================
# Quality Gate
# =====================================================================

class QualityGateResult(BaseModel):
    """Audio quality pre-flight check before multi-signal scoring."""
    passed: bool = Field(..., description="Whether audio meets minimal scoring criteria")
    speech_duration_s: float = Field(0.0, description="Total active voice duration detected in seconds")
    snr_db: float = Field(0.0, description="Estimated Signal-to-Noise Ratio in dB")
    min_speech_threshold_s: float = Field(1.5, description="Required minimum speech duration")
    min_snr_threshold_db: float = Field(5.0, description="Required minimum SNR in dB")
    reason: Optional[str] = Field(None, description="Explanation if quality gate failed")

    @classmethod
    def insufficient(cls, speech_duration_s: float = 0.0, snr_db: float = 0.0, reason: str = "Insufficient speech or high noise") -> QualityGateResult:
        return cls(
            passed=False,
            speech_duration_s=speech_duration_s,
            snr_db=snr_db,
            reason=reason
        )

    @classmethod
    def passed_default(cls, speech_duration_s: float = 3.0, snr_db: float = 20.0) -> QualityGateResult:
        return cls(
            passed=True,
            speech_duration_s=speech_duration_s,
            snr_db=snr_db,
            reason=None
        )


# =====================================================================
# Speaker Identity (audio_ml/verify.py)
# =====================================================================

class SpeakerVerificationResult(BaseModel):
    """Result of speaker identity verification against enrolled voiceprints."""
    verdict: SpeakerVerdict = Field(SpeakerVerdict.UNKNOWN, description="match, mismatch, or unknown")
    matched_person_id: Optional[str] = Field(None, description="Enrolled contact ID if match/mismatch found")
    matched_person_name: Optional[str] = Field(None, description="Enrolled contact name")
    claimed_person_id: Optional[str] = Field(None, description="Claimed contact ID from caller metadata if provided")
    raw_score: float = Field(0.0, description="Raw cosine similarity / distance score")
    norm_score: float = Field(0.0, description="S-normalised score against background cohort")
    risk: float = Field(0.5, ge=0.0, le=1.0, description="Identity risk (0.0 = confirmed genuine, 0.5 = neutral unknown, 1.0 = confirmed mismatch)")
    is_replay: bool = Field(False, description="Flagged if cosine > 0.95 indicating replayed recording")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Confidence in the verification decision")
    details: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic parameters (cohort stats, thresholds)")

    @classmethod
    def neutral(cls) -> SpeakerVerificationResult:
        return cls(
            verdict=SpeakerVerdict.UNKNOWN,
            matched_person_id=None,
            matched_person_name=None,
            raw_score=0.0,
            norm_score=0.0,
            risk=0.5,
            is_replay=False,
            confidence=0.5,
            details={"fallback": True}
        )


# =====================================================================
# Authenticity / Anti-Spoof (audio_ml/spoof.py)
# =====================================================================

class SpoofSegment(BaseModel):
    """Acoustic deepfake / synthesis detection score for a specific audio window."""
    start_s: float = Field(..., description="Segment start offset in seconds")
    end_s: float = Field(..., description="Segment end offset in seconds")
    score: float = Field(..., ge=0.0, le=1.0, description="Synthetic probability for this window (0=bonafide, 1=spoof)")
    is_synthetic: bool = Field(..., description="Whether this window exceeds synthetic threshold")


class AntiSpoofResult(BaseModel):
    """Result of anti-spoofing and synthetic speech detection.
    
    CRITICAL DOMAIN RULE:
    Reporting median alone hides hybrid attacks. We report median, peak,
    and max contiguous synthetic run duration.
    """
    median_score: float = Field(0.0, ge=0.0, le=1.0, description="Median synthetic score across all chunks")
    peak_score: float = Field(0.0, ge=0.0, le=1.0, description="Peak synthetic score across all chunks")
    max_synth_run_s: float = Field(0.0, ge=0.0, description="Maximum contiguous duration of synthetic speech in seconds")
    raw_score: float = Field(0.0, description="Aggregate raw synthetic score")
    norm_score: float = Field(0.0, description="Normalised synthetic score")
    risk: float = Field(0.0, ge=0.0, le=1.0, description="Base authenticity risk before intent gating")
    is_synthetic: bool = Field(False, description="Overall synthetic speech flag")
    timeline: List[SpoofSegment] = Field(default_factory=list, description="Per-chunk synthetic probability timeline")
    details: Dict[str, Any] = Field(default_factory=dict, description="Model diagnostic info")

    @classmethod
    def neutral(cls) -> AntiSpoofResult:
        return cls(
            median_score=0.0,
            peak_score=0.0,
            max_synth_run_s=0.0,
            raw_score=0.0,
            norm_score=0.0,
            risk=0.0,
            is_synthetic=False,
            timeline=[],
            details={"fallback": True}
        )


# =====================================================================
# Intent / RAG / Script Analysis (nlp_rag/api.py)
# =====================================================================

class TranscriptSegment(BaseModel):
    """Timestamped transcript chunk."""
    start_s: float = Field(..., description="Start time in seconds")
    end_s: float = Field(..., description="End time in seconds")
    text: str = Field(..., description="Transcribed text")
    language: Optional[str] = Field(None, description="Detected language code (e.g., 'hi', 'en', 'hi-en')")


class TranscriptResult(BaseModel):
    """ASR result supporting Hindi, English, and code-switched Hinglish."""
    text: str = Field("", description="Full transcript text")
    segments: List[TranscriptSegment] = Field(default_factory=list, description="Individual transcript segments")
    detected_language: str = Field("unknown", description="Primary detected language code")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="ASR transcription confidence")

    @classmethod
    def empty(cls) -> TranscriptResult:
        return cls(text="", segments=[], detected_language="unknown", confidence=0.0)


class MarkerMatch(BaseModel):
    """Pattern or regex match for incriminating or exculpatory language."""
    marker_id: str = Field(..., description="Unique marker identifier (e.g. 'MK_ISOLATION_DEMAND')")
    marker_type: MarkerType = Field(..., description="incriminating (raises risk) or exculpatory (lowers risk)")
    category: str = Field(..., description="Category (e.g. 'isolation', 'urgency', 'payment', 'verification_invite')")
    matched_text: str = Field(..., description="Exact snippet from transcript that matched")
    weight: float = Field(..., description="Risk impact weight (-1.0 to 1.0)")
    description: str = Field(..., description="Human-readable description of what this marker signifies")


class RetrievedPlaybook(BaseModel):
    """Scam playbook citation retrieved from the bilingual knowledge corpus."""
    playbook_id: str = Field(..., description="Playbook identifier (e.g. 'PB_DIGITAL_ARREST_01')")
    title: str = Field(..., description="Title of known scam pattern or advisory")
    category: str = Field(..., description="Fraud category (e.g., 'Digital Arrest', 'Kidnapping Extortion', 'Bank KYC')")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="RAG semantic similarity score (BGE-m3)")
    matched_excerpt: str = Field(..., description="Key excerpt matching the caller's pitch")
    source_url: str = Field(..., description="External reference URL (e.g. cybercrime.gov.in, PIB FactCheck)")
    source_agency: str = Field(..., description="Publishing authority (e.g. 'I4C / MHA', 'RBI', 'Delhi Police')")


class ScriptAnalysisResult(BaseModel):
    """Result of conversational intent and script risk analysis."""
    risk: float = Field(0.0, ge=0.0, le=1.0, description="Intent / script risk (0.0 = benign, 1.0 = high scam intent)")
    incriminating_markers: List[MarkerMatch] = Field(default_factory=list, description="Risk-increasing markers")
    exculpatory_markers: List[MarkerMatch] = Field(default_factory=list, description="Risk-decreasing markers")
    playbooks: List[RetrievedPlaybook] = Field(default_factory=list, description="Retrieved scam playbook citations")
    intent_summary: Optional[str] = Field(None, description="High-level intent classification summary")
    details: Dict[str, Any] = Field(default_factory=dict, description="Corpus match statistics")

    @classmethod
    def neutral(cls) -> ScriptAnalysisResult:
        return cls(
            risk=0.0,
            incriminating_markers=[],
            exculpatory_markers=[],
            playbooks=[],
            intent_summary="No significant fraud markers detected",
            details={"fallback": True}
        )


# =====================================================================
# Reason Codes, Citations & Challenge Questions
# =====================================================================

class ReasonCode(BaseModel):
    """Structured, explainable evidence point supporting the trust score."""
    code: str = Field(..., description="Stable code key (e.g., 'RC_SYNTHETIC_PEAK_DETECTED', 'RC_ISOLATION_DEMAND')")
    signal: SignalType = Field(..., description="Originating signal branch")
    value: str = Field(..., description="Observed value formatted for display")
    threshold: Optional[str] = Field(None, description="Reference threshold value formatted for display")
    explanation: str = Field(..., description="Concise explanation for user display")
    citation_title: Optional[str] = Field(None, description="External source title if applicable")
    citation_url: Optional[str] = Field(None, description="Source URL for verifiable external evidence")
    severity: SeverityLevel = Field(SeverityLevel.INFO, description="Visual severity badge")


class ChallengeQuestion(BaseModel):
    """Dynamic challenge question derived from enrolled shared secrets."""
    question_id: str = Field(..., description="Question identifier")
    question_text: str = Field(..., description="Challenge prompt to read to caller (e.g., 'What was the name of our first pet?')")
    relation_context: Optional[str] = Field(None, description="Context (e.g., 'Shared only between Rahul and Mother')")
    expected_answer_hash: Optional[str] = Field(None, description="SHA-256 hash of expected answer for local verification")


# =====================================================================
# Fusion & Final Verdict
# =====================================================================

class FusionWeights(BaseModel):
    """Weights applied across the three branches during fusion."""
    asv_weight: float = Field(..., description="Weight for speaker verification risk")
    cm_weight: float = Field(..., description="Weight for anti-spoof synthetic risk")
    text_weight: float = Field(..., description="Weight for script / intent risk")


class TrustScoreResult(BaseModel):
    """Fused verdict representing overall caller trust and explainable evidence.
    
    Formula:
    intent   = max(script_risk, identity_risk if verdict == 'mismatch' else 0.0)
    r_cm_eff = r_cm * (CM_FLOOR + (1 - CM_FLOOR) * intent)
    combined_risk = w_asv * r_asv + w_cm * r_cm_eff + w_text * r_text (renormalised)
    trust_score = round((1.0 - combined_risk) * 100, 1)
    """
    trust_score: float = Field(..., ge=0.0, le=100.0, description="Trust score (0=Severe Threat, 100=Fully Trusted)")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Fused risk score (0.0 to 1.0)")
    band: TrustBand = Field(..., description="Trust band category")
    mode: OperatingMode = Field(..., description="Active operating mode (identity_check or authority_check)")
    weights_used: FusionWeights = Field(..., description="Weights applied during fusion")
    
    # Effective signal contributions
    identity_risk: float = Field(..., ge=0.0, le=1.0, description="Speaker identity risk (0.5 if unknown)")
    authenticity_risk: float = Field(..., ge=0.0, le=1.0, description="Raw anti-spoof risk")
    authenticity_risk_effective: float = Field(..., ge=0.0, le=1.0, description="Intent-gated anti-spoof risk (r_cm_eff)")
    intent_risk: float = Field(..., ge=0.0, le=1.0, description="Transcript script / intent risk")
    
    # Evidence & Guidance
    reason_codes: List[ReasonCode] = Field(default_factory=list, description="Ordered list of cited evidence points")
    recommended_actions: List[str] = Field(default_factory=list, description="Actionable recommendations for the user/guardian")
    challenge_question: Optional[ChallengeQuestion] = Field(None, description="Challenge question if identity verification recommended")
    vernacular_warning: Optional[str] = Field(None, description="Pre-cached spoken warning text in regional language")

    @classmethod
    def insufficient(cls, reason: str = "Audio sample insufficient or too noisy to evaluate") -> TrustScoreResult:
        return cls(
            trust_score=50.0,
            risk_score=0.5,
            band=TrustBand.INSUFFICIENT,
            mode=OperatingMode.AUTHORITY_CHECK,
            weights_used=FusionWeights(asv_weight=0.0, cm_weight=0.0, text_weight=0.0),
            identity_risk=0.5,
            authenticity_risk=0.0,
            authenticity_risk_effective=0.0,
            intent_risk=0.0,
            reason_codes=[
                ReasonCode(
                    code="RC_QUALITY_INSUFFICIENT",
                    signal=SignalType.QUALITY,
                    value="Below minimum duration/SNR",
                    threshold="1.5s speech, 5.0 dB SNR",
                    explanation=reason,
                    severity=SeverityLevel.INFO
                )
            ],
            recommended_actions=["Ask caller to speak clearly on speakerphone for at least 3 seconds."],
            challenge_question=None,
            vernacular_warning=None
        )


# =====================================================================
# Enrollment & Voiceprint Models
# =====================================================================

class VoiceprintRecord(BaseModel):
    """Enrolled voiceprint vector stored per acoustic condition."""
    voiceprint_id: str = Field(..., description="Unique voiceprint identifier")
    person_id: str = Field(..., description="Foreign key to EnrolledPerson")
    condition: AcousticCondition = Field(..., description="Acoustic condition (wideband vs 8k codec)")
    embedding: List[float] = Field(..., description="192-d or 512-d speaker embedding vector")
    duration_s: float = Field(..., description="Duration of enrollment audio used")
    snr_db: float = Field(..., description="SNR of enrollment audio")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SharedSecret(BaseModel):
    """Shared secret used to generate out-of-band challenge questions."""
    secret_id: str = Field(..., description="Secret identifier")
    question: str = Field(..., description="Prompt question")
    answer_hash: str = Field(..., description="SHA-256 hash of expected answer")
    category: str = Field("personal", description="Category (family_memory, pet, milestone)")


class EnrolledPerson(BaseModel):
    """Profile of an enrolled family member or trusted contact."""
    person_id: str = Field(..., description="Unique person identifier")
    name: str = Field(..., description="Full name of contact")
    relation: str = Field(..., description="Relationship (e.g. 'Son', 'Mother', 'Accountant')")
    phone_number: Optional[str] = Field(None, description="Expected caller phone number")
    avatar_url: Optional[str] = Field(None, description="Optional avatar icon URL")
    voiceprints: List[VoiceprintRecord] = Field(default_factory=list, description="Condition-matched voiceprints")
    shared_secrets: List[SharedSecret] = Field(default_factory=list, description="Configured challenge questions")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EnrollmentRequest(BaseModel):
    """Request payload to enroll a new contact."""
    name: str = Field(..., min_length=1, description="Contact name")
    relation: str = Field(..., min_length=1, description="Relationship to user")
    phone_number: Optional[str] = Field(None, description="Optional phone number")
    audio_base64: Optional[str] = Field(None, description="Base64 encoded enrollment audio (min 30s)")
    audio_file_path: Optional[str] = Field(None, description="Local path to enrollment audio file")
    shared_secrets: List[Dict[str, str]] = Field(default_factory=list, description="List of {question, answer} pairs")


class FlaggedVoiceRecord(BaseModel):
    """Negative voiceprint vector for previously confirmed scam callers (FR-15)."""
    flagged_id: str = Field(..., description="Identifier")
    embedding: List[float] = Field(..., description="Speaker embedding")
    incident_category: str = Field(..., description="Scam category associated with this voice")
    first_reported_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_case_id: Optional[str] = Field(None, description="Reference 1930/Chakshu incident ID")


# =====================================================================
# Server & Screening API Contracts
# =====================================================================

class CallerMetadata(BaseModel):
    """Optional caller ID metadata (FR-17).
    
    CRITICAL RULE:
    Enriches explanation and UI only; never factored into the mathematical trust score.
    """
    claimed_number: Optional[str] = Field(None, description="Caller ID number displayed on phone")
    claimed_name: Optional[str] = Field(None, description="Truecaller / Telco CNAM displayed name")
    claimed_identity: Optional[str] = Field(None, description="Enrolled contact ID caller claims to be")
    channel_type: Literal["speakerphone", "voicemail", "upload", "whatsapp"] = Field("speakerphone")


class ScreeningRequest(BaseModel):
    """Incoming request to screen an audio stream or file."""
    session_id: Optional[str] = Field(None, description="Active session ID for rolling analysis")
    audio_base64: Optional[str] = Field(None, description="Base64 encoded audio payload")
    audio_file_path: Optional[str] = Field(None, description="Server-accessible audio file path")
    caller_metadata: Optional[CallerMetadata] = Field(default_factory=CallerMetadata)


class ScreeningResponse(BaseModel):
    """Complete multi-branch screening result returned by the backend."""
    session_id: str = Field(..., description="Screening session identifier")
    audio_sha256: str = Field(..., description="Cryptographic SHA-256 digest of analyzed audio")
    quality: QualityGateResult = Field(..., description="Quality gate output")
    speaker: SpeakerVerificationResult = Field(..., description="Speaker identity branch output")
    spoof: AntiSpoofResult = Field(..., description="Anti-spoof authenticity branch output")
    transcript: TranscriptResult = Field(..., description="ASR transcription output")
    script: ScriptAnalysisResult = Field(..., description="Intent and RAG script analysis output")
    fusion: TrustScoreResult = Field(..., description="Final fused trust score and evidence")
    processing_time_ms: float = Field(..., description="Total server processing latency in milliseconds")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# =====================================================================
# Guardian & Incident Reporting Contracts (FR-12, FR-14)
# =====================================================================

class GuardianAlert(BaseModel):
    """Real-time push notification payload dispatched to subscribed guardian devices."""
    alert_id: str = Field(..., description="Unique alert ID")
    session_id: str = Field(..., description="Associated screening session ID")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    trust_score: float = Field(..., description="Current trust score")
    band: TrustBand = Field(..., description="Alert band level")
    caller_name_or_number: str = Field("Unknown Caller", description="Display label for caller")
    summary: str = Field(..., description="Actionable headline (e.g. 'Potential synthetic voice impersonating Rahul')")
    key_reasons: List[str] = Field(default_factory=list, description="Top bullet reasons")
    audio_sha256: str = Field(..., description="Audio fingerprint")


class IncidentReportPacket(BaseModel):
    """Pre-filled, structured evidence packet formatted for national cybercrime portals (1930 / Chakshu)."""
    report_id: str = Field(..., description="Unique incident report ID")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    audio_sha256: str = Field(..., description="SHA-256 hash of original audio recording")
    trust_score: float = Field(..., description="Final trust score")
    band: TrustBand = Field(..., description="Classification band")
    caller_metadata: CallerMetadata = Field(..., description="Caller details and channel")
    transcript_full: str = Field(..., description="Complete verbatim transcript")
    evidence_reason_codes: List[ReasonCode] = Field(..., description="Full list of cited reason codes")
    matched_playbooks: List[RetrievedPlaybook] = Field(default_factory=list, description="Referenced official fraud advisories")
    recommended_complaint_category: str = Field("Financial Fraud / Impersonation", description="Portal category")
    pdf_report_path: Optional[str] = Field(None, description="Path to generated downloadable PDF")


# =====================================================================
# WebSocket Streaming Contracts (FR-13)
# =====================================================================

class StreamClientMessageType(str, Enum):
    AUDIO_CHUNK = "audio_chunk"
    CLAIM_IDENTITY = "claim_identity"
    RESET_SESSION = "reset_session"


class StreamServerMessageType(str, Enum):
    SCREENING_UPDATE = "screening_update"
    QUALITY_WARNING = "quality_warning"
    GUARDIAN_ALERT = "guardian_alert"
    ERROR = "error"


class StreamAudioChunkMessage(BaseModel):
    """Client streaming message carrying an audio slice."""
    type: Literal[StreamClientMessageType.AUDIO_CHUNK] = StreamClientMessageType.AUDIO_CHUNK
    session_id: str = Field(...)
    chunk_index: int = Field(...)
    audio_base64: str = Field(...)
    is_final: bool = Field(False)


class StreamScreeningUpdateMessage(BaseModel):
    """Server streaming update with current trust score and evidence."""
    type: Literal[StreamServerMessageType.SCREENING_UPDATE] = StreamServerMessageType.SCREENING_UPDATE
    session_id: str = Field(...)
    chunk_index: int = Field(...)
    response: ScreeningResponse = Field(...)


# =====================================================================
# Mock Fixture Factories (Block 0 Deliverable)
# =====================================================================

def create_mock_fixture(scenario_type: Literal["green", "red", "unverified", "insufficient"]) -> ScreeningResponse:
    """Generates standard frozen mock fixtures for frontend development and testing."""
    now_iso = datetime.now(timezone.utc).isoformat()
    dummy_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    if scenario_type == "green":
        # Scenario 1: Genuine enrolled family member calling normally
        quality = QualityGateResult.passed_default(speech_duration_s=8.5, snr_db=24.0)
        speaker = SpeakerVerificationResult(
            verdict=SpeakerVerdict.MATCH,
            matched_person_id="p_rahul_01",
            matched_person_name="Rahul (Son)",
            raw_score=0.78,
            norm_score=2.15,
            risk=0.08,
            is_replay=False,
            confidence=0.94,
            details={"margin": 0.45}
        )
        spoof = AntiSpoofResult(
            median_score=0.02,
            peak_score=0.06,
            max_synth_run_s=0.0,
            raw_score=0.02,
            norm_score=-1.8,
            risk=0.02,
            is_synthetic=False,
            timeline=[
                SpoofSegment(start_s=0.0, end_s=3.0, score=0.02, is_synthetic=False),
                SpoofSegment(start_s=2.0, end_s=5.0, score=0.03, is_synthetic=False),
                SpoofSegment(start_s=4.0, end_s=7.0, score=0.01, is_synthetic=False),
            ]
        )
        transcript = TranscriptResult(
            text="Hi Ma, I just reached the office. Will be home by 7 PM today. Don't worry!",
            segments=[
                TranscriptSegment(start_s=0.0, end_s=4.0, text="Hi Ma, I just reached the office.", language="en"),
                TranscriptSegment(start_s=4.0, end_s=7.5, text="Will be home by 7 PM today. Don't worry!", language="en")
            ],
            detected_language="en",
            confidence=0.98
        )
        script = ScriptAnalysisResult(
            risk=0.05,
            incriminating_markers=[],
            exculpatory_markers=[
                MarkerMatch(
                    marker_id="MK_EXCULPATORY_ROUTINE",
                    marker_type=MarkerType.EXCULPATORY,
                    category="routine_checkin",
                    matched_text="Will be home by 7 PM",
                    weight=-0.3,
                    description="Routine personal update, no financial request"
                )
            ],
            playbooks=[],
            intent_summary="Benign family check-in"
        )
        fusion = TrustScoreResult(
            trust_score=96.0,
            risk_score=0.04,
            band=TrustBand.VERIFIED,
            mode=OperatingMode.IDENTITY_CHECK,
            weights_used=FusionWeights(asv_weight=0.40, cm_weight=0.35, text_weight=0.25),
            identity_risk=0.08,
            authenticity_risk=0.02,
            authenticity_risk_effective=0.02,
            intent_risk=0.05,
            reason_codes=[
                ReasonCode(
                    code="RC_SPEAKER_VERIFIED",
                    signal=SignalType.IDENTITY,
                    value="Cosine 0.78 (s-norm 2.15)",
                    threshold="> 1.20",
                    explanation="Voice closely matches enrolled voiceprint for Rahul (Son).",
                    severity=SeverityLevel.INFO
                ),
                ReasonCode(
                    code="RC_AUDIO_BONAFIDE",
                    signal=SignalType.AUTHENTICITY,
                    value="Synthetic Prob 2%",
                    threshold="< 15%",
                    explanation="Natural acoustic resonance and micro-pitch jitter indicate organic human speech.",
                    severity=SeverityLevel.INFO
                )
            ],
            recommended_actions=["No action required. Call verified as genuine family member."],
            challenge_question=None,
            vernacular_warning=None
        )

    elif scenario_type == "red":
        # Scenario 4: Cloned family emergency extortion call
        quality = QualityGateResult.passed_default(speech_duration_s=12.0, snr_db=18.5)
        speaker = SpeakerVerificationResult(
            verdict=SpeakerVerdict.MATCH,
            matched_person_id="p_rahul_01",
            matched_person_name="Rahul (Son)",
            raw_score=0.72,
            norm_score=1.85,
            risk=0.15,
            is_replay=False,
            confidence=0.88,
            details={"margin": 0.35}
        )
        spoof = AntiSpoofResult(
            median_score=0.86,
            peak_score=0.98,
            max_synth_run_s=6.5,
            raw_score=0.89,
            norm_score=2.8,
            risk=0.92,
            is_synthetic=True,
            timeline=[
                SpoofSegment(start_s=0.0, end_s=3.0, score=0.78, is_synthetic=True),
                SpoofSegment(start_s=2.0, end_s=5.0, score=0.94, is_synthetic=True),
                SpoofSegment(start_s=4.0, end_s=7.0, score=0.98, is_synthetic=True),
                SpoofSegment(start_s=6.0, end_s=9.0, score=0.91, is_synthetic=True),
            ]
        )
        transcript = TranscriptResult(
            text="Papa emergency ho gaya hai, police ne pakad liya hai! Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe!",
            segments=[
                TranscriptSegment(start_s=0.0, end_s=4.5, text="Papa emergency ho gaya hai, police ne pakad liya hai!", language="hi"),
                TranscriptSegment(start_s=4.5, end_s=10.0, text="Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe!", language="hi")
            ],
            detected_language="hi",
            confidence=0.95
        )
        script = ScriptAnalysisResult(
            risk=0.94,
            incriminating_markers=[
                MarkerMatch(
                    marker_id="MK_ISOLATION_DEMAND",
                    marker_type=MarkerType.INCRIMINATING,
                    category="isolation",
                    matched_text="Phone kisi ko mat dena",
                    weight=0.85,
                    description="Caller strictly demands isolation and forbids consulting family members"
                ),
                MarkerMatch(
                    marker_id="MK_URGENT_FINANCIAL_UPI",
                    marker_type=MarkerType.INCRIMINATING,
                    category="urgent_transfer",
                    matched_text="turant 50000 bhejo is UPI ID pe",
                    weight=0.90,
                    description="Demanding immediate irreversible UPI fund transfer under panic"
                )
            ],
            exculpatory_markers=[],
            playbooks=[
                RetrievedPlaybook(
                    playbook_id="PB_DIGITAL_ARREST_POLICE_01",
                    title="Digital Arrest & Fake Police Extortion Advisory",
                    category="Extortion / Impersonation",
                    similarity_score=0.91,
                    matched_excerpt="Scammers clone children's voices claiming arrest and demanding immediate UPI bail money while forbidding contact with anyone.",
                    source_url="https://cybercrime.gov.in/Webform/Crime_Advisory.aspx",
                    source_agency="Indian Cyber Crime Coordination Centre (I4C), MHA"
                )
            ],
            intent_summary="High-severity emergency extortion & isolation demand"
        )
        fusion = TrustScoreResult(
            trust_score=12.0,
            risk_score=0.88,
            band=TrustBand.HIGH_RISK,
            mode=OperatingMode.IDENTITY_CHECK,
            weights_used=FusionWeights(asv_weight=0.40, cm_weight=0.35, text_weight=0.25),
            identity_risk=0.15,
            authenticity_risk=0.92,
            authenticity_risk_effective=0.92,
            intent_risk=0.94,
            reason_codes=[
                ReasonCode(
                    code="RC_SYNTHETIC_VOICE_DETECTED",
                    signal=SignalType.AUTHENTICITY,
                    value="Peak Synth 98% (Run 6.5s)",
                    threshold="> 40%",
                    explanation="Deepfake speech synthesis signatures detected. Spectral artifacts match neural vocoder cloning.",
                    citation_title="Deepfake Voice Fraud Advisory",
                    citation_url="https://cybercrime.gov.in/Webform/Crime_Advisory.aspx",
                    severity=SeverityLevel.CRITICAL
                ),
                ReasonCode(
                    code="RC_ISOLATION_AND_PANIC",
                    signal=SignalType.INTENT,
                    value="Isolation Marker + Urgent UPI",
                    threshold="High Intent Risk",
                    explanation="Demands strict secrecy ('don't tell anyone') and urgent payment. Classical extortion playbook.",
                    citation_title="MHA Advisory on Digital Extortion",
                    citation_url="https://cybercrime.gov.in/Webform/Crime_Advisory.aspx",
                    severity=SeverityLevel.CRITICAL
                )
            ],
            recommended_actions=[
                "DO NOT transfer money via UPI.",
                "Disconnect the call immediately.",
                "Call Rahul back directly on their known saved phone number."
            ],
            challenge_question=ChallengeQuestion(
                question_id="CQ_RAHUL_PET_01",
                question_text="Ask the caller: 'What is the name of our hometown dog?'",
                relation_context="Known only to immediate family",
                expected_answer_hash="5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"
            ),
            vernacular_warning="सावधान! यह कॉल एक क्लोन की हुई नकली आवाज़ हो सकती है। कोई भी पैसा ट्रांसफर न करें।"
        )

    elif scenario_type == "unverified":
        # Scenario: Legitimate Bank IVR / Delivery Agent (Neutral Stranger)
        quality = QualityGateResult.passed_default(speech_duration_s=6.0, snr_db=22.0)
        speaker = SpeakerVerificationResult(
            verdict=SpeakerVerdict.UNKNOWN,
            matched_person_id=None,
            matched_person_name=None,
            raw_score=0.12,
            norm_score=-0.2,
            risk=0.50,
            is_replay=False,
            confidence=0.50,
            details={"note": "No enrolled voiceprint match"}
        )
        spoof = AntiSpoofResult(
            median_score=0.72,
            peak_score=0.85,
            max_synth_run_s=5.0,
            raw_score=0.74,
            norm_score=1.5,
            risk=0.74,
            is_synthetic=True,
            timeline=[
                SpoofSegment(start_s=0.0, end_s=3.0, score=0.70, is_synthetic=True),
                SpoofSegment(start_s=2.0, end_s=5.0, score=0.78, is_synthetic=True),
            ]
        )
        transcript = TranscriptResult(
            text="Dear customer, your HDFC Bank statement for account ending 4402 is ready. Press 1 to receive on WhatsApp.",
            segments=[
                TranscriptSegment(start_s=0.0, end_s=5.5, text="Dear customer, your HDFC Bank statement for account ending 4402 is ready. Press 1 to receive on WhatsApp.", language="en")
            ],
            detected_language="en",
            confidence=0.96
        )
        script = ScriptAnalysisResult(
            risk=0.08,
            incriminating_markers=[],
            exculpatory_markers=[
                MarkerMatch(
                    marker_id="MK_EXCULPATORY_OFFICIAL_NOTIFICATION",
                    marker_type=MarkerType.EXCULPATORY,
                    category="bank_notification",
                    matched_text="statement is ready",
                    weight=-0.2,
                    description="Standard institutional statement notification, no OTP/PIN request"
                )
            ],
            playbooks=[],
            intent_summary="Legitimate automated service notification"
        )
        # Intent gating: r_cm_eff = 0.74 * (0.25 + 0.75 * 0.08) = 0.74 * 0.31 = 0.229
        # Authority check weights: ASV 0.10, CM 0.45, Text 0.45
        fusion = TrustScoreResult(
            trust_score=78.0,
            risk_score=0.22,
            band=TrustBand.UNVERIFIED,
            mode=OperatingMode.AUTHORITY_CHECK,
            weights_used=FusionWeights(asv_weight=0.10, cm_weight=0.45, text_weight=0.45),
            identity_risk=0.50,
            authenticity_risk=0.74,
            authenticity_risk_effective=0.23,
            intent_risk=0.08,
            reason_codes=[
                ReasonCode(
                    code="RC_UNKNOWN_CALLER_UNVERIFIED",
                    signal=SignalType.IDENTITY,
                    value="Unenrolled Caller",
                    threshold="N/A",
                    explanation="Caller is not in enrolled contacts. Operating in authority check mode.",
                    severity=SeverityLevel.INFO
                ),
                ReasonCode(
                    code="RC_LEGIT_AUTOMATED_VOICE",
                    signal=SignalType.AUTHENTICITY,
                    value="Automated IVR Voice (Intent Gated)",
                    threshold="Low Intent Risk",
                    explanation="Synthetic speech detected from institutional service without suspicious financial demands.",
                    severity=SeverityLevel.INFO
                )
            ],
            recommended_actions=["Caller is an unverified automated voice service. Verify directly through official app if in doubt."],
            challenge_question=None,
            vernacular_warning=None
        )

    else:  # insufficient
        quality = QualityGateResult.insufficient(speech_duration_s=0.6, snr_db=3.2, reason="Audio duration below 1.5s threshold")
        speaker = SpeakerVerificationResult.neutral()
        spoof = AntiSpoofResult.neutral()
        transcript = TranscriptResult.empty()
        script = ScriptAnalysisResult.neutral()
        fusion = TrustScoreResult.insufficient(reason="Audio duration (0.6s) below 1.5s minimum required for reliable verification.")

    return ScreeningResponse(
        session_id=f"session_mock_{scenario_type}",
        audio_sha256=dummy_sha,
        quality=quality,
        speaker=speaker,
        spoof=spoof,
        transcript=transcript,
        script=script,
        fusion=fusion,
        processing_time_ms=18.4,
        timestamp=now_iso
    )
