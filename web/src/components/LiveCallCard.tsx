import { useEffect, useState } from "react";
import { AlertTriangle, Mic, Phone, ShieldCheck, UserRound } from "lucide-react";
import type { LiveCall } from "../hooks/useLiveFeed";
import type { Authenticity, LiveVerdict } from "../types/liveFeed";
import type { SeverityLevel, SpeakerVerdict, TrustBand } from "../types/contracts";
import { BAND_LABEL, DOT, INK, SURFACE, knownState, windowView } from "./liveFeedDisplay";

/**
 * One call from the live feed, as large as a judge three metres away needs.
 *
 * Rendering rules from docs/LIVE_FEED.md: colour comes from `overlay_state`, never from
 * mapping `band` here; `insufficient` is "listening", not a judgement; a verdict is a
 * level with evidence, never an accusation; an authenticity check that did not run is
 * "not measured", never "genuine".
 */

const HEADLINE: Record<TrustBand, { title: string; detail: string }> = {
  insufficient: {
    title: "Listening…",
    detail: "Not enough clear speech yet to judge this call.",
  },
  unverified: {
    title: "Unverified caller",
    detail: "Not an enrolled voice, which is normal for a stranger. Nothing worrying so far.",
  },
  verified: {
    title: "Verified caller",
    detail: "The voice matches an enrolled family member.",
  },
  caution: {
    title: "Check before you act",
    detail: "Something on this call needs verifying before anyone sends money or shares a code.",
  },
  suspicious: {
    title: "Signs of a scam call",
    detail: "Several warning signs. Do not send money or share any code.",
  },
  high_risk: {
    title: "Likely scam — do not send money",
    detail: "Strong signs of fraud on this call.",
  },
};

const IDENTITY: Record<SpeakerVerdict, string> = {
  match: "Matches an enrolled voice",
  mismatch: "Does not match the enrolled voice",
  unknown: "Not an enrolled voice",
};

const AUTHENTICITY: Record<Authenticity, { text: string; warn: boolean }> = {
  synthetic: { text: "Signs of a cloned voice", warn: true },
  bonafide: { text: "No signs of a cloned voice", warn: false },
  unavailable: { text: "Not measured", warn: false },
};

const SEVERITY: Record<SeverityLevel, string> = {
  critical: "bg-[var(--danger)] text-white",
  high: "bg-[var(--danger-bg)] text-[var(--danger-text)] border border-[var(--danger-border)]",
  medium: "bg-[var(--warning-bg)] text-[var(--warning-text)] border border-[var(--warning-border)]",
  low: "bg-[var(--bg-secondary)] text-[var(--text-secondary)] border border-[var(--border-default)]",
  info: "bg-[var(--bg-secondary)] text-[var(--text-muted)] border border-[var(--border-subtle)]",
};

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

function formatDuration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/**
 * Each window's own trust score as a bar, coloured by its own band. Unlike the session
 * verdict above it, this goes up as well as down: it shows where in the call the risk was.
 */
function WindowChart({ windows }: { windows: LiveVerdict[] }) {
  return (
    <div>
      <div className="text-xs font-semibold text-[var(--text-muted)] mb-2">
        Trust in every 2 seconds of the call, oldest first
      </div>
      <div
        className="flex items-end gap-1 h-16 border-b border-[var(--border-default)] overflow-x-auto"
        role="list"
        aria-label="Trust score per scoring window"
      >
        {windows.map((w) => {
          const win = windowView(w);
          const listening = win.band === "insufficient";
          return (
            <span
              key={`${w.window_index}-${w.is_final}`}
              role="listitem"
              title={`Window ${w.window_index} · ${BAND_LABEL[win.band] ?? win.band} · ${
                listening ? "listening" : `trust ${Math.round(win.score)}`
              }${w.is_final ? " · final" : ""}`}
              style={{ height: listening ? "12%" : `${Math.max(8, Math.min(100, win.score))}%` }}
              className={`w-3 shrink-0 rounded-t-sm ${DOT[win.state]} ${listening ? "opacity-40" : ""} ${
                w.is_final ? "ring-2 ring-[var(--text-primary)]" : ""
              }`}
            />
          );
        })}
      </div>
    </div>
  );
}

/** The current window's own score: the live gauge docs/LIVE_FEED.md asks for. */
function RightNow({ verdict }: { verdict: LiveVerdict }) {
  const win = windowView(verdict);
  const listening = win.band === "insufficient";
  const pct = listening ? 0 : Math.max(0, Math.min(100, win.score));
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-semibold text-[var(--text-secondary)]">Right now</span>
        <span className="font-semibold">
          <span className={`font-mono text-lg ${INK[win.state]}`}>{listening ? "—" : Math.round(win.score)}</span>
          <span className="text-[var(--text-muted)]"> · {BAND_LABEL[win.band] ?? win.band}</span>
        </span>
      </div>
      <div className="h-2.5 rounded-full bg-[var(--bg-secondary)] overflow-hidden" aria-hidden>
        <div className={`h-full transition-all duration-500 ${DOT[win.state]}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs text-[var(--text-muted)]">
        This moment of the call. It moves up and down; the trust score above is the call's
        lowest so far and never goes back up.
      </p>
    </div>
  );
}

export default function LiveCallCard({ call }: { call: LiveCall }) {
  const v = call.latest;
  const ended = v.is_final;
  const now = useNow(!ended);
  const state = knownState(v.overlay_state);
  const headline = HEADLINE[v.band] ?? HEADLINE.insufficient;
  const listening = v.band === "insufficient";
  const caller = v.caller_context?.claimed_number || "Unknown number";
  const viaPhone = v.caller_context?.channel_type === "telephony";
  const authenticity = AUTHENTICITY[v.signals.authenticity] ?? AUTHENTICITY.unavailable;
  const intentPct = Math.round(Math.max(0, Math.min(1, v.signals.intent_risk)) * 100);

  return (
    <div className="space-y-5">
      {/* ── Verdict ─────────────────────────────────────────────── */}
      <section
        className={`rounded-2xl border p-6 sm:p-8 space-y-5 transition-colors ${SURFACE[state]}`}
        aria-live="polite"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
          <div className="flex items-center gap-2 font-semibold text-[var(--text-primary)]">
            <Phone className="w-4 h-4" aria-hidden />
            <span className="font-mono text-base">{caller}</span>
            {viaPhone && <span className="text-[var(--text-muted)] font-normal">· phone call</span>}
          </div>
          <div className="flex items-center gap-2 text-[var(--text-secondary)]">
            {ended ? (
              <span className="px-2.5 py-0.5 rounded-full bg-[var(--bg-secondary)] border border-[var(--border-default)] font-semibold">
                Call ended
              </span>
            ) : (
              <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-[var(--bg-secondary)] border border-[var(--border-default)] font-semibold">
                <span className="w-2 h-2 rounded-full bg-[var(--danger)] animate-pulse" aria-hidden />
                In progress
              </span>
            )}
            <span className="font-mono">
              {formatDuration((ended ? call.lastSeen : now) - call.firstSeen)}
            </span>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div className="space-y-2">
            {v.escalated && !ended && (
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--danger)] text-white text-sm font-bold animate-pulse">
                <AlertTriangle className="w-4 h-4" aria-hidden />
                Warning level raised
              </div>
            )}
            <h2 className={`text-3xl sm:text-5xl font-extrabold leading-tight ${INK[state]}`}>
              {headline.title}
            </h2>
            <p className="text-lg sm:text-xl text-[var(--text-secondary)] font-medium max-w-3xl">
              {headline.detail}
            </p>
            {v.threat_label && (
              <p className="text-base text-[var(--text-primary)]">
                Resembles <strong>{v.threat_label.threat}</strong>
                <span className="text-[var(--text-muted)]"> · {v.threat_label.sector}</span>
              </p>
            )}
          </div>
          <div className="text-right shrink-0">
            <div className="text-xs font-semibold text-[var(--text-muted)]">Trust score</div>
            <div className={`text-5xl sm:text-6xl font-extrabold font-mono ${INK[state]}`}>
              {listening ? "—" : Math.round(v.trust_score)}
            </div>
            <div className="text-xs text-[var(--text-muted)]">out of 100 · lowest so far</div>
          </div>
        </div>

        {v.vernacular_warning && (
          <p lang="hi" className={`text-xl sm:text-2xl font-bold leading-relaxed ${INK[state]}`}>
            {v.vernacular_warning}
          </p>
        )}

        {!ended && <RightNow verdict={v} />}
      </section>

      {/* ── The three signals ──────────────────────────────────── */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="sec-card p-4 space-y-1">
          <div className="flex items-center gap-2 text-xs font-semibold text-[var(--text-muted)]">
            <UserRound className="w-4 h-4" aria-hidden /> Who is speaking
          </div>
          <div className="text-lg font-bold text-[var(--text-primary)]">
            {IDENTITY[v.signals.identity] ?? v.signals.identity}
          </div>
          <div className="text-sm text-[var(--text-secondary)]">
            {v.mode === "identity_check" ? "Checking a known contact" : "Unknown caller: judged on what is asked"}
          </div>
        </div>
        <div className="sec-card p-4 space-y-1">
          <div className="flex items-center gap-2 text-xs font-semibold text-[var(--text-muted)]">
            <Mic className="w-4 h-4" aria-hidden /> Voice
          </div>
          <div
            className={`text-lg font-bold ${authenticity.warn ? "text-[var(--danger)]" : "text-[var(--text-primary)]"}`}
          >
            {authenticity.text}
          </div>
          <div className="text-sm text-[var(--text-secondary)]">
            {v.signals.authenticity === "unavailable"
              ? "The voice check did not run on this call."
              : "From the sound of the voice itself."}
          </div>
        </div>
        <div className="sec-card p-4 space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-[var(--text-muted)]">
            <ShieldCheck className="w-4 h-4" aria-hidden /> What is being asked
          </div>
          <div className="text-lg font-bold text-[var(--text-primary)]">Scam-language risk {intentPct}%</div>
          <div className="h-2 rounded-full bg-[var(--bg-secondary)] overflow-hidden" aria-hidden>
            <div
              className={`h-full ${intentPct >= 60 ? "bg-[var(--danger)]" : intentPct >= 30 ? "bg-[var(--warning)]" : "bg-[var(--text-muted)]"}`}
              style={{ width: `${intentPct}%` }}
            />
          </div>
        </div>
      </section>

      {/* ── Timeline + transcript ──────────────────────────────── */}
      <section className="sec-card p-5 space-y-5">
        <WindowChart windows={call.windows} />
        <div>
          <div className="flex items-center justify-between text-xs font-semibold text-[var(--text-muted)] mb-2">
            <span>What was said</span>
            {v.language && v.language !== "unknown" && <span className="font-mono">{v.language}</span>}
          </div>
          {v.transcript ? (
            <p className="text-lg italic text-[var(--text-primary)] leading-relaxed">“{v.transcript}”</p>
          ) : (
            <p className="text-base text-[var(--text-muted)]">
              {ended
                ? "No speech was understood on this call."
                : "The transcript appears after about 10 seconds of speech."}
            </p>
          )}
        </div>
      </section>

      {/* ── Actions + evidence ─────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {v.recommended_actions.length > 0 && (
          <section className="sec-card p-5 space-y-3">
            <h3 className="text-lg font-bold text-[var(--text-primary)]">What to tell the person on the call</h3>
            <ol className="list-decimal pl-5 space-y-1.5 text-base text-[var(--text-secondary)]">
              {v.recommended_actions.map((action, i) => (
                <li key={`${i}-${action}`}>{action}</li>
              ))}
            </ol>
          </section>
        )}
        {v.reason_codes.length > 0 && (
          <section className="sec-card p-5 space-y-3">
            <h3 className="text-lg font-bold text-[var(--text-primary)]">Why</h3>
            <ul className="space-y-3">
              {v.reason_codes.map((rc) => (
                <li key={`${rc.code}-${rc.signal}`} className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${SEVERITY[rc.severity] ?? SEVERITY.info}`}>
                      {rc.severity}
                    </span>
                    {rc.value && (
                      <span className="text-xs font-mono text-[var(--text-muted)]">
                        {rc.value}
                        {rc.threshold ? ` (threshold ${rc.threshold})` : ""}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-[var(--text-primary)]">{rc.explanation}</p>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
