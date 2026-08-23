/**
 * SatyaCheck — Frontend Type Contracts
 *
 * TypeScript mirrors of every Pydantic model in contracts.py.
 * FROZEN: do not rename, reorder, or "improve" fields.
 */

// ── Enums (const objects + type unions for erasable syntax) ─────

export const SpeakerVerdict = {
  MATCH: "match",
  MISMATCH: "mismatch",
  UNKNOWN: "unknown",
} as const;
export type SpeakerVerdict = (typeof SpeakerVerdict)[keyof typeof SpeakerVerdict];

export const OperatingMode = {
  IDENTITY_CHECK: "identity_check",
  AUTHORITY_CHECK: "authority_check",
} as const;
export type OperatingMode = (typeof OperatingMode)[keyof typeof OperatingMode];

export const TrustBand = {
  VERIFIED: "verified",
  CAUTION: "caution",
  SUSPICIOUS: "suspicious",
  HIGH_RISK: "high_risk",
  UNVERIFIED: "unverified",
  INSUFFICIENT: "insufficient",
} as const;
export type TrustBand = (typeof TrustBand)[keyof typeof TrustBand];

export const SignalType = {
  IDENTITY: "identity",
  AUTHENTICITY: "authenticity",
  INTENT: "intent",
  QUALITY: "quality",
  META: "meta",
} as const;
export type SignalType = (typeof SignalType)[keyof typeof SignalType];

export const MarkerType = {
  INCRIMINATING: "incriminating",
  EXCULPATORY: "exculpatory",
} as const;
export type MarkerType = (typeof MarkerType)[keyof typeof MarkerType];

export const SeverityLevel = {
  INFO: "info",
  LOW: "low",
  MEDIUM: "medium",
  HIGH: "high",
  CRITICAL: "critical",
} as const;
export type SeverityLevel = (typeof SeverityLevel)[keyof typeof SeverityLevel];

export const AcousticCondition = {
  WIDEBAND_16K: "wideband_16k",
  NARROWBAND_8K: "narrowband_8k",
  CODEC_AMR_NB: "codec_amr_nb",
  CODEC_OPUS: "codec_opus",
} as const;
export type AcousticCondition = (typeof AcousticCondition)[keyof typeof AcousticCondition];

// ── Quality Gate ───────────────────────────────────────────────

export interface QualityGateResult {
  passed: boolean;
  speech_duration_s: number;
  snr_db: number;
  min_speech_threshold_s: number;
  min_snr_threshold_db: number;
  reason: string | null;
}

// ── Speaker Identity ───────────────────────────────────────────

export interface SpeakerVerificationResult {
  verdict: SpeakerVerdict;
  matched_person_id: string | null;
  matched_person_name: string | null;
  claimed_person_id: string | null;
  raw_score: number;
  norm_score: number;
  risk: number;
  is_replay: boolean;
  confidence: number;
  details: Record<string, unknown>;
}

// ── Anti-Spoof / Authenticity ──────────────────────────────────

export interface SpoofSegment {
  start_s: number;
  end_s: number;
  score: number;
  is_synthetic: boolean;
}

export interface AntiSpoofResult {
  median_score: number;
  peak_score: number;
  max_synth_run_s: number;
  raw_score: number;
  norm_score: number;
  risk: number;
  is_synthetic: boolean;
  timeline: SpoofSegment[];
  details: Record<string, unknown>;
}

// ── Transcript / ASR ───────────────────────────────────────────

export interface TranscriptSegment {
  start_s: number;
  end_s: number;
  text: string;
  language: string | null;
}

export interface TranscriptResult {
  text: string;
  segments: TranscriptSegment[];
  detected_language: string;
  confidence: number;
}

// ── Intent / Script Analysis ───────────────────────────────────

export interface MarkerMatch {
  marker_id: string;
  marker_type: MarkerType;
  category: string;
  matched_text: string;
  weight: number;
  description: string;
}

export interface RetrievedPlaybook {
  playbook_id: string;
  title: string;
  category: string;
  similarity_score: number;
  matched_excerpt: string;
  source_url: string;
  source_agency: string;
}

export interface ScriptAnalysisResult {
  risk: number;
  incriminating_markers: MarkerMatch[];
  exculpatory_markers: MarkerMatch[];
  playbooks: RetrievedPlaybook[];
  intent_summary: string | null;
  details: Record<string, unknown>;
}

// ── Reason Codes & Citations ───────────────────────────────────

export interface ReasonCode {
  code: string;
  signal: SignalType;
  value: string;
  threshold: string | null;
  explanation: string;
  citation_title: string | null;
  citation_url: string | null;
  severity: SeverityLevel;
}

export interface ChallengeQuestion {
  question_id: string;
  question_text: string;
  relation_context: string | null;
  expected_answer_hash: string | null;
}

// ── Fusion & Final Verdict ─────────────────────────────────────

export interface FusionWeights {
  asv_weight: number;
  cm_weight: number;
  text_weight: number;
}

export interface TrustScoreResult {
  trust_score: number;
  risk_score: number;
  band: TrustBand;
  mode: OperatingMode;
  weights_used: FusionWeights;
  identity_risk: number;
  authenticity_risk: number;
  authenticity_risk_effective: number;
  intent_risk: number;
  reason_codes: ReasonCode[];
  recommended_actions: string[];
  challenge_question: ChallengeQuestion | null;
  vernacular_warning: string | null;
}

// ── Screening API ──────────────────────────────────────────────

export interface ScreeningResponse {
  session_id: string;
  audio_sha256: string;
  quality: QualityGateResult;
  speaker: SpeakerVerificationResult;
  spoof: AntiSpoofResult;
  transcript: TranscriptResult;
  script: ScriptAnalysisResult;
  fusion: TrustScoreResult;
  processing_time_ms: number;
  timestamp: string;
}

// ── Enrollment ─────────────────────────────────────────────────

export interface EnrolledPerson {
  person_id: string;
  name: string;
  relation: string;
  phone_number: string | null;
  avatar_url: string | null;
  created_at: string;
}

export interface EnrollmentRequest {
  name: string;
  relation: string;
  phone_number?: string;
  shared_secrets?: Array<{ question: string; answer: string }>;
}

// ── Band visual config (frontend-only) ─────────────────────────

export interface BandConfig {
  label: string;
  color: string;
  bgColor: string;
  glowColor: string;
  textColor: string;
}

export const BAND_CONFIG: Record<TrustBand, BandConfig> = {
  [TrustBand.VERIFIED]: {
    label: "Verified",
    color: "#059669",
    bgColor: "rgba(5, 150, 105, 0.12)",
    glowColor: "rgba(5, 150, 105, 0.4)",
    textColor: "#34D399",
  },
  [TrustBand.CAUTION]: {
    label: "Caution",
    color: "#D97706",
    bgColor: "rgba(217, 119, 6, 0.12)",
    glowColor: "rgba(217, 119, 6, 0.4)",
    textColor: "#FBBF24",
  },
  [TrustBand.SUSPICIOUS]: {
    label: "Suspicious",
    color: "#EA580C",
    bgColor: "rgba(234, 88, 12, 0.12)",
    glowColor: "rgba(234, 88, 12, 0.4)",
    textColor: "#FB923C",
  },
  [TrustBand.HIGH_RISK]: {
    label: "High risk",
    color: "#DC2626",
    bgColor: "rgba(220, 38, 38, 0.12)",
    glowColor: "rgba(220, 38, 38, 0.4)",
    textColor: "#F87171",
  },
  [TrustBand.UNVERIFIED]: {
    label: "Unverified",
    color: "#64748B",
    bgColor: "rgba(100, 116, 139, 0.12)",
    glowColor: "rgba(100, 116, 139, 0.3)",
    textColor: "#94A3B8",
  },
  [TrustBand.INSUFFICIENT]: {
    label: "Insufficient audio",
    color: "#94A3B8",
    bgColor: "rgba(148, 163, 184, 0.08)",
    glowColor: "rgba(148, 163, 184, 0.15)",
    textColor: "#CBD5E1",
  },
};
