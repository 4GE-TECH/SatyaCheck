/**
 * SatyaCheck — `/api/ws/live` message types, schema version 1.
 *
 * Mirrors docs/LIVE_FEED.md and server/live_feed.py (`verdict_message`). Not part of
 * contracts.ts: this is the flattened feed message, not a ScreeningResponse.
 */

import type {
  OperatingMode,
  SeverityLevel,
  SignalType,
  SpeakerVerdict,
  TrustBand,
} from "./contracts";

export const LIVE_FEED_SCHEMA_VERSION = 1;

/** The colour to render. Use this rather than mapping `band` yourself. */
export type OverlayState = "green" | "amber" | "red" | "grey";

/** `unavailable` means the voice check did not run: say "not measured", never "genuine". */
export type Authenticity = "synthetic" | "bonafide" | "unavailable";

export interface LiveHello {
  type: "hello";
  schema_version: number;
  server_time: string;
}

export interface LiveReasonCode {
  code: string;
  signal: SignalType;
  value: string;
  threshold: string | null;
  explanation: string;
  severity: SeverityLevel;
}

export interface LiveCallerContext {
  claimed_number: string | null;
  claimed_name: string | null;
  claimed_identity: string | null;
  channel_type: string | null;
}

export interface LiveThreatLabel {
  sector: string;
  threat: string;
  family: string;
}

export interface LiveVerdict {
  type: "verdict";
  schema_version: number;
  session_id: string;
  window_index: number;
  /** True exactly once per call, on its last verdict. */
  is_final: boolean;
  /** True when this verdict raised the call's warning level. */
  escalated: boolean;
  timestamp: string;
  band: TrustBand;
  overlay_state: OverlayState;
  /** 0–100, higher is more trusted. Never goes up during a call. */
  trust_score: number;
  risk_score: number;
  mode: OperatingMode;
  signals: {
    identity: SpeakerVerdict;
    authenticity: Authenticity;
    intent_risk: number;
  };
  reason_codes: LiveReasonCode[];
  /** Empty for roughly the first 9–14 seconds of a call. */
  transcript: string;
  language: string;
  caller_context: LiveCallerContext | null;
  threat_label: LiveThreatLabel | null;
  recommended_actions: string[];
  vernacular_warning: string | null;
}
