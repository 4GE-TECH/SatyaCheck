import type { OverlayState } from "../types/liveFeed";
import type { TrustBand } from "../types/contracts";

/**
 * Colours and labels shared by the live page and its call card. Colour is keyed by the
 * feed's `overlay_state`, never by `band` (docs/LIVE_FEED.md).
 */

export const SURFACE: Record<OverlayState, string> = {
  red: "bg-[var(--danger-bg)] border-[var(--danger-border)]",
  amber: "bg-[var(--warning-bg)] border-[var(--warning-border)]",
  green: "bg-[var(--success-bg)] border-[var(--success-border)]",
  grey: "bg-[var(--bg-primary)] border-[var(--border-default)]",
};

export const INK: Record<OverlayState, string> = {
  red: "text-[var(--danger)]",
  amber: "text-[var(--warning-text)]",
  green: "text-[var(--success)]",
  grey: "text-[var(--text-primary)]",
};

export const DOT: Record<OverlayState, string> = {
  red: "bg-[var(--danger)]",
  amber: "bg-[var(--warning)]",
  green: "bg-[var(--success)]",
  grey: "bg-[var(--text-muted)]",
};

export const BAND_LABEL: Record<TrustBand, string> = {
  insufficient: "Listening",
  unverified: "Unverified",
  verified: "Verified",
  caution: "Caution",
  suspicious: "Suspicious",
  high_risk: "High risk",
};

/** A state the backend sent that this dashboard does not know renders as grey. */
export function knownState(state: string): OverlayState {
  return state in SURFACE ? (state as OverlayState) : "grey";
}
