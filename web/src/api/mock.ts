/**
 * Mock fixtures ported from contracts.py create_mock_fixture().
 * Four scenarios: green, red, unverified, insufficient.
 */

import {
  type ScreeningResponse,
  SpeakerVerdict,
  OperatingMode,
  TrustBand,
  SignalType,
  MarkerType,
  SeverityLevel,
} from "../types/contracts";

const NOW_ISO = new Date().toISOString();
const DUMMY_SHA =
  "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

// ── Scenario 1: Genuine enrolled family member ─────────────────

const GREEN_FIXTURE: ScreeningResponse = {
  session_id: "session_mock_green",
  audio_sha256: DUMMY_SHA,
  quality: {
    passed: true,
    speech_duration_s: 8.5,
    snr_db: 24.0,
    min_speech_threshold_s: 1.5,
    min_snr_threshold_db: 5.0,
    reason: null,
  },
  speaker: {
    verdict: SpeakerVerdict.MATCH,
    matched_person_id: "p_rahul_01",
    matched_person_name: "Rahul (Son)",
    claimed_person_id: null,
    raw_score: 0.78,
    norm_score: 2.15,
    risk: 0.08,
    is_replay: false,
    confidence: 0.94,
    details: { margin: 0.45 },
  },
  spoof: {
    median_score: 0.02,
    peak_score: 0.06,
    max_synth_run_s: 0.0,
    raw_score: 0.02,
    norm_score: -1.8,
    risk: 0.02,
    is_synthetic: false,
    timeline: [
      { start_s: 0.0, end_s: 3.0, score: 0.02, is_synthetic: false },
      { start_s: 2.0, end_s: 5.0, score: 0.03, is_synthetic: false },
      { start_s: 4.0, end_s: 7.0, score: 0.01, is_synthetic: false },
    ],
    details: {},
  },
  transcript: {
    text: "Hi Ma, I just reached the office. Will be home by 7 PM today. Don't worry!",
    segments: [
      {
        start_s: 0.0,
        end_s: 4.0,
        text: "Hi Ma, I just reached the office.",
        language: "en",
      },
      {
        start_s: 4.0,
        end_s: 7.5,
        text: "Will be home by 7 PM today. Don't worry!",
        language: "en",
      },
    ],
    detected_language: "en",
    confidence: 0.98,
  },
  script: {
    risk: 0.05,
    incriminating_markers: [],
    exculpatory_markers: [
      {
        marker_id: "MK_EXCULPATORY_ROUTINE",
        marker_type: MarkerType.EXCULPATORY,
        category: "routine_checkin",
        matched_text: "Will be home by 7 PM",
        weight: -0.3,
        description: "Routine personal update, no financial request",
      },
    ],
    playbooks: [],
    intent_summary: "Benign family check-in",
    details: {},
  },
  fusion: {
    trust_score: 96.0,
    risk_score: 0.04,
    band: TrustBand.VERIFIED,
    mode: OperatingMode.IDENTITY_CHECK,
    weights_used: { asv_weight: 0.4, cm_weight: 0.35, text_weight: 0.25 },
    identity_risk: 0.08,
    authenticity_risk: 0.02,
    authenticity_risk_effective: 0.02,
    intent_risk: 0.05,
    reason_codes: [
      {
        code: "RC_SPEAKER_VERIFIED",
        signal: SignalType.IDENTITY,
        value: "Cosine 0.78 (s-norm 2.15)",
        threshold: "> 1.20",
        explanation:
          "Voice closely matches enrolled voiceprint for Rahul (Son).",
        citation_title: null,
        citation_url: null,
        severity: SeverityLevel.INFO,
      },
      {
        code: "RC_AUDIO_BONAFIDE",
        signal: SignalType.AUTHENTICITY,
        value: "Synthetic Prob 2%",
        threshold: "< 15%",
        explanation:
          "Natural acoustic resonance and micro-pitch jitter indicate organic human speech.",
        citation_title: null,
        citation_url: null,
        severity: SeverityLevel.INFO,
      },
    ],
    recommended_actions: [
      "No action required. Call verified as genuine family member.",
    ],
    challenge_question: null,
    vernacular_warning: null,
  },
  processing_time_ms: 18.4,
  timestamp: NOW_ISO,
};

// ── Scenario 4: Cloned family emergency extortion ──────────────

const RED_FIXTURE: ScreeningResponse = {
  session_id: "session_mock_red",
  audio_sha256: DUMMY_SHA,
  quality: {
    passed: true,
    speech_duration_s: 12.0,
    snr_db: 18.5,
    min_speech_threshold_s: 1.5,
    min_snr_threshold_db: 5.0,
    reason: null,
  },
  speaker: {
    verdict: SpeakerVerdict.MATCH,
    matched_person_id: "p_rahul_01",
    matched_person_name: "Rahul (Son)",
    claimed_person_id: null,
    raw_score: 0.72,
    norm_score: 1.85,
    risk: 0.15,
    is_replay: false,
    confidence: 0.88,
    details: { margin: 0.35 },
  },
  spoof: {
    median_score: 0.86,
    peak_score: 0.98,
    max_synth_run_s: 6.5,
    raw_score: 0.89,
    norm_score: 2.8,
    risk: 0.92,
    is_synthetic: true,
    timeline: [
      { start_s: 0.0, end_s: 3.0, score: 0.78, is_synthetic: true },
      { start_s: 2.0, end_s: 5.0, score: 0.94, is_synthetic: true },
      { start_s: 4.0, end_s: 7.0, score: 0.98, is_synthetic: true },
      { start_s: 6.0, end_s: 9.0, score: 0.91, is_synthetic: true },
    ],
    details: {},
  },
  transcript: {
    text: "Papa emergency ho gaya hai, police ne pakad liya hai! Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe!",
    segments: [
      {
        start_s: 0.0,
        end_s: 4.5,
        text: "Papa emergency ho gaya hai, police ne pakad liya hai!",
        language: "hi",
      },
      {
        start_s: 4.5,
        end_s: 10.0,
        text: "Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe!",
        language: "hi",
      },
    ],
    detected_language: "hi",
    confidence: 0.95,
  },
  script: {
    risk: 0.94,
    incriminating_markers: [
      {
        marker_id: "MK_ISOLATION_DEMAND",
        marker_type: MarkerType.INCRIMINATING,
        category: "isolation",
        matched_text: "Phone kisi ko mat dena",
        weight: 0.85,
        description:
          "Caller strictly demands isolation and forbids consulting family members",
      },
      {
        marker_id: "MK_URGENT_FINANCIAL_UPI",
        marker_type: MarkerType.INCRIMINATING,
        category: "urgent_transfer",
        matched_text: "turant 50000 bhejo is UPI ID pe",
        weight: 0.9,
        description:
          "Demanding immediate irreversible UPI fund transfer under panic",
      },
    ],
    exculpatory_markers: [],
    playbooks: [
      {
        playbook_id: "PB_DIGITAL_ARREST_POLICE_01",
        title: "Digital Arrest & Fake Police Extortion Advisory",
        category: "Extortion / Impersonation",
        similarity_score: 0.91,
        matched_excerpt:
          "Scammers clone children's voices claiming arrest and demanding immediate UPI bail money while forbidding contact with anyone.",
        source_url: "https://cybercrime.gov.in/Webform/Crime_Advisory.aspx",
        source_agency:
          "Indian Cyber Crime Coordination Centre (I4C), MHA",
      },
    ],
    intent_summary: "High-severity emergency extortion & isolation demand",
    details: {},
  },
  fusion: {
    trust_score: 12.0,
    risk_score: 0.88,
    band: TrustBand.HIGH_RISK,
    mode: OperatingMode.IDENTITY_CHECK,
    weights_used: { asv_weight: 0.4, cm_weight: 0.35, text_weight: 0.25 },
    identity_risk: 0.15,
    authenticity_risk: 0.92,
    authenticity_risk_effective: 0.92,
    intent_risk: 0.94,
    reason_codes: [
      {
        code: "RC_SYNTHETIC_VOICE_DETECTED",
        signal: SignalType.AUTHENTICITY,
        value: "Peak Synth 98% (Run 6.5s)",
        threshold: "> 40%",
        explanation:
          "Deepfake speech synthesis signatures detected. Spectral artifacts match neural vocoder cloning.",
        citation_title: "Deepfake Voice Fraud Advisory",
        citation_url:
          "https://cybercrime.gov.in/Webform/Crime_Advisory.aspx",
        severity: SeverityLevel.CRITICAL,
      },
      {
        code: "RC_ISOLATION_AND_PANIC",
        signal: SignalType.INTENT,
        value: "Isolation Marker + Urgent UPI",
        threshold: "High Intent Risk",
        explanation:
          "Demands strict secrecy ('don't tell anyone') and urgent payment. Classical extortion playbook.",
        citation_title: "MHA Advisory on Digital Extortion",
        citation_url:
          "https://cybercrime.gov.in/Webform/Crime_Advisory.aspx",
        severity: SeverityLevel.CRITICAL,
      },
    ],
    recommended_actions: [
      "DO NOT transfer money via UPI.",
      "Disconnect the call immediately.",
      "Call Rahul back directly on their known saved phone number.",
    ],
    challenge_question: {
      question_id: "CQ_RAHUL_PET_01",
      question_text:
        "Ask the caller: 'What is the name of our hometown dog?'",
      relation_context: "Known only to immediate family",
      expected_answer_hash:
        "5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",
    },
    vernacular_warning:
      "सावधान! यह कॉल एक क्लोन की हुई नकली आवाज़ हो सकती है। कोई भी पैसा ट्रांसफर न करें।",
  },
  processing_time_ms: 18.4,
  timestamp: NOW_ISO,
};

// ── Scenario: Legitimate Bank IVR (unverified stranger) ────────

const UNVERIFIED_FIXTURE: ScreeningResponse = {
  session_id: "session_mock_unverified",
  audio_sha256: DUMMY_SHA,
  quality: {
    passed: true,
    speech_duration_s: 6.0,
    snr_db: 22.0,
    min_speech_threshold_s: 1.5,
    min_snr_threshold_db: 5.0,
    reason: null,
  },
  speaker: {
    verdict: SpeakerVerdict.UNKNOWN,
    matched_person_id: null,
    matched_person_name: null,
    claimed_person_id: null,
    raw_score: 0.12,
    norm_score: -0.2,
    risk: 0.5,
    is_replay: false,
    confidence: 0.5,
    details: { note: "No enrolled voiceprint match" },
  },
  spoof: {
    median_score: 0.72,
    peak_score: 0.85,
    max_synth_run_s: 5.0,
    raw_score: 0.74,
    norm_score: 1.5,
    risk: 0.74,
    is_synthetic: true,
    timeline: [
      { start_s: 0.0, end_s: 3.0, score: 0.7, is_synthetic: true },
      { start_s: 2.0, end_s: 5.0, score: 0.78, is_synthetic: true },
    ],
    details: {},
  },
  transcript: {
    text: "Dear customer, your HDFC Bank statement for account ending 4402 is ready. Press 1 to receive on WhatsApp.",
    segments: [
      {
        start_s: 0.0,
        end_s: 5.5,
        text: "Dear customer, your HDFC Bank statement for account ending 4402 is ready. Press 1 to receive on WhatsApp.",
        language: "en",
      },
    ],
    detected_language: "en",
    confidence: 0.96,
  },
  script: {
    risk: 0.08,
    incriminating_markers: [],
    exculpatory_markers: [
      {
        marker_id: "MK_EXCULPATORY_OFFICIAL_NOTIFICATION",
        marker_type: MarkerType.EXCULPATORY,
        category: "bank_notification",
        matched_text: "statement is ready",
        weight: -0.2,
        description:
          "Standard institutional statement notification, no OTP/PIN request",
      },
    ],
    playbooks: [],
    intent_summary: "Legitimate automated service notification",
    details: {},
  },
  fusion: {
    trust_score: 78.0,
    risk_score: 0.22,
    band: TrustBand.UNVERIFIED,
    mode: OperatingMode.AUTHORITY_CHECK,
    weights_used: { asv_weight: 0.1, cm_weight: 0.45, text_weight: 0.45 },
    identity_risk: 0.5,
    authenticity_risk: 0.74,
    authenticity_risk_effective: 0.23,
    intent_risk: 0.08,
    reason_codes: [
      {
        code: "RC_UNKNOWN_CALLER_UNVERIFIED",
        signal: SignalType.IDENTITY,
        value: "Unenrolled Caller",
        threshold: "N/A",
        explanation:
          "Caller is not in enrolled contacts. Operating in authority check mode.",
        citation_title: null,
        citation_url: null,
        severity: SeverityLevel.INFO,
      },
      {
        code: "RC_LEGIT_AUTOMATED_VOICE",
        signal: SignalType.AUTHENTICITY,
        value: "Automated IVR Voice (Intent Gated)",
        threshold: "Low Intent Risk",
        explanation:
          "Synthetic speech detected from institutional service without suspicious financial demands.",
        citation_title: null,
        citation_url: null,
        severity: SeverityLevel.INFO,
      },
    ],
    recommended_actions: [
      "Caller is an unverified automated voice service. Verify directly through official app if in doubt.",
    ],
    challenge_question: null,
    vernacular_warning: null,
  },
  processing_time_ms: 18.4,
  timestamp: NOW_ISO,
};

// ── Scenario: Insufficient audio ───────────────────────────────

const INSUFFICIENT_FIXTURE: ScreeningResponse = {
  session_id: "session_mock_insufficient",
  audio_sha256: DUMMY_SHA,
  quality: {
    passed: false,
    speech_duration_s: 0.6,
    snr_db: 3.2,
    min_speech_threshold_s: 1.5,
    min_snr_threshold_db: 5.0,
    reason: "Audio duration below 1.5s threshold",
  },
  speaker: {
    verdict: SpeakerVerdict.UNKNOWN,
    matched_person_id: null,
    matched_person_name: null,
    claimed_person_id: null,
    raw_score: 0.0,
    norm_score: 0.0,
    risk: 0.5,
    is_replay: false,
    confidence: 0.5,
    details: { fallback: true },
  },
  spoof: {
    median_score: 0.0,
    peak_score: 0.0,
    max_synth_run_s: 0.0,
    raw_score: 0.0,
    norm_score: 0.0,
    risk: 0.0,
    is_synthetic: false,
    timeline: [],
    details: { fallback: true },
  },
  transcript: {
    text: "",
    segments: [],
    detected_language: "unknown",
    confidence: 0.0,
  },
  script: {
    risk: 0.0,
    incriminating_markers: [],
    exculpatory_markers: [],
    playbooks: [],
    intent_summary: "No significant fraud markers detected",
    details: { fallback: true },
  },
  fusion: {
    trust_score: 50.0,
    risk_score: 0.5,
    band: TrustBand.INSUFFICIENT,
    mode: OperatingMode.AUTHORITY_CHECK,
    weights_used: { asv_weight: 0.0, cm_weight: 0.0, text_weight: 0.0 },
    identity_risk: 0.5,
    authenticity_risk: 0.0,
    authenticity_risk_effective: 0.0,
    intent_risk: 0.0,
    reason_codes: [
      {
        code: "RC_QUALITY_INSUFFICIENT",
        signal: SignalType.QUALITY,
        value: "Below minimum duration/SNR",
        threshold: "1.5s speech, 5.0 dB SNR",
        explanation:
          "Audio duration (0.6s) below 1.5s minimum required for reliable verification.",
        citation_title: null,
        citation_url: null,
        severity: SeverityLevel.INFO,
      },
    ],
    recommended_actions: [
      "Ask caller to speak clearly on speakerphone for at least 3 seconds.",
    ],
    challenge_question: null,
    vernacular_warning: null,
  },
  processing_time_ms: 18.4,
  timestamp: NOW_ISO,
};

// ── Public API ─────────────────────────────────────────────────

export type MockScenario = "green" | "red" | "unverified" | "insufficient";

const FIXTURES: Record<MockScenario, ScreeningResponse> = {
  green: GREEN_FIXTURE,
  red: RED_FIXTURE,
  unverified: UNVERIFIED_FIXTURE,
  insufficient: INSUFFICIENT_FIXTURE,
};

export function getMockFixture(scenario: MockScenario): ScreeningResponse {
  return structuredClone(FIXTURES[scenario]);
}

export const SCENARIO_LABELS: Record<MockScenario, string> = {
  green: "Genuine call — Rahul (Son)",
  red: "Cloned voice — Emergency extortion",
  unverified: "Bank IVR — Legitimate stranger",
  insufficient: "Insufficient audio",
};
