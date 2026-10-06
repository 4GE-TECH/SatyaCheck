import type { LiveVerdict, OverlayState } from "../types/liveFeed";
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

/**
 * Band to colour, as the backend maps it for `overlay_state` (server/ws_router.py,
 * _OVERLAY_STATE). Needed only for `window_band`, which comes without a colour of its own;
 * session verdicts still take `overlay_state` as sent.
 */
const BAND_STATE: Record<TrustBand, OverlayState> = {
  verified: "green",
  caution: "amber",
  suspicious: "red",
  high_risk: "red",
  unverified: "grey",
  insufficient: "grey",
};

/**
 * This window's own score, band and colour, for the live gauge and the per-window chart.
 * Falls back to the session values when the backend predates `window_trust_score`, which
 * is what the backend itself does when it has no window view.
 */
export function windowView(v: LiveVerdict): { score: number; band: TrustBand; state: OverlayState } {
  const band = v.window_band ?? v.band;
  return {
    score: v.window_trust_score ?? v.trust_score,
    band,
    state: BAND_STATE[band] ?? "grey",
  };
}
