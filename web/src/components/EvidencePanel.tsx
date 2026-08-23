import type { ReasonCode, MarkerMatch, RetrievedPlaybook } from "../types/contracts";
import { SeverityLevel } from "../types/contracts";
import { ExternalLink, ShieldCheck, AlertOctagon } from "lucide-react";

interface EvidencePanelProps {
  reasonCodes: ReasonCode[];
  incriminatingMarkers?: MarkerMatch[];
  exculpatoryMarkers?: MarkerMatch[];
  playbooks: RetrievedPlaybook[];
}

const SEVERITY_BADGES: Record<
  SeverityLevel,
  { label: string; bg: string; text: string; border: string }
> = {
  [SeverityLevel.CRITICAL]: {
    label: "CRITICAL",
    bg: "bg-[var(--danger-bg)]",
    text: "text-[var(--danger-text)]",
    border: "border-[var(--danger-border)]",
  },
  [SeverityLevel.HIGH]: {
    label: "HIGH",
    bg: "bg-[var(--danger-bg)]",
    text: "text-[var(--danger-text)]",
    border: "border-[var(--danger-border)]",
  },
  [SeverityLevel.MEDIUM]: {
    label: "MEDIUM",
    bg: "bg-[var(--warning-bg)]",
    text: "text-[var(--warning-text)]",
    border: "border-[var(--warning-border)]",
  },
  [SeverityLevel.LOW]: {
    label: "LOW",
    bg: "bg-[var(--success-bg)]",
    text: "text-[var(--success-text)]",
    border: "border-[var(--success-border)]",
  },
  [SeverityLevel.INFO]: {
    label: "INFO",
    bg: "bg-[var(--bg-secondary)]",
    text: "text-[var(--text-secondary)]",
    border: "border-[var(--border-default)]",
  },
};

export default function EvidencePanel({
  reasonCodes,
  incriminatingMarkers = [],
  exculpatoryMarkers = [],
  playbooks,
}: EvidencePanelProps) {
  return (
    <div className="sec-card-subtle p-4 space-y-4 font-mono text-xs">
      <div className="flex items-center justify-between pb-2 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[var(--accent)]"></span>
          <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--text-primary)]">
            CITABLE EVIDENCE CODES & ADVISORY REASONING
          </h3>
        </div>
        <span className="text-[10px] text-[var(--text-muted)]">
          {reasonCodes.length} CODES · {playbooks.length} PLAYBOOKS
        </span>
      </div>

      {/* ── 1. Structured Reason Codes ─────────────────── */}
      <div className="space-y-2">
        {reasonCodes.map((rc) => {
          const badge = SEVERITY_BADGES[rc.severity] || SEVERITY_BADGES[SeverityLevel.INFO];
          const isExculpatory =
            rc.code.includes("BONAFIDE") ||
            rc.code.includes("VERIFIED") ||
            rc.code.includes("LEGIT");

          return (
            <div
              key={rc.code}
              className="p-3 rounded bg-[var(--bg-primary)] border border-[var(--border-default)] transition-colors space-y-1.5"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase border ${badge.bg} ${badge.text} ${badge.border}`}
                  >
                    {badge.label}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-secondary)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
                    {rc.signal.toUpperCase()}
                  </span>
                  <span
                    className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase border ${
                      isExculpatory
                        ? "bg-emerald-950/40 text-emerald-400 border-emerald-500/30"
                        : "bg-red-950/40 text-red-400 border-red-500/30"
                    }`}
                  >
                    {isExculpatory ? "[+] LOWERS RISK" : "[-] RAISES RISK"}
                  </span>
                  <span className="text-xs font-bold text-[var(--text-primary)]">
                    {rc.code}
                  </span>
                </div>

                <div className="flex items-center gap-2 text-[10px] text-[var(--text-muted)]">
                  <span>
                    OBSERVED: <span className="text-[var(--text-primary)] font-bold">{rc.value}</span>
                  </span>
                  {rc.threshold && (
                    <span>
                      / THRESHOLD: <span className="text-[var(--text-secondary)]">{rc.threshold}</span>
                    </span>
                  )}
                </div>
              </div>

              <p className="text-xs text-[var(--text-secondary)] leading-relaxed font-sans">
                {rc.explanation}
              </p>

              {rc.citation_url && (
                <div className="flex items-center justify-between pt-1.5 border-t border-[var(--border-subtle)] text-[10px]">
                  <span className="text-[var(--text-muted)]">OFFICIAL CITATION:</span>
                  <a
                    href={rc.citation_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[var(--accent)] hover:underline font-bold no-underline inline-flex items-center gap-1"
                  >
                    <span>{rc.citation_title || "Official Crime Advisory"}</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── 2. NLP Linguistic Markers (Incriminating vs Exculpatory) ── */}
      {(incriminatingMarkers.length > 0 || exculpatoryMarkers.length > 0) && (
        <div className="pt-2 border-t border-[var(--border-subtle)] space-y-2">
          <div className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider">
            NLP SCRIPT LINGUISTIC PATTERN DISCOVERY:
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {/* Incriminating Markers */}
            {incriminatingMarkers.map((m) => (
              <div
                key={m.marker_id}
                className="p-2.5 rounded bg-[var(--danger-bg)] border border-[var(--danger-border)] space-y-1 text-xs"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-[var(--danger-text)] font-bold">
                    <AlertOctagon className="w-3.5 h-3.5 shrink-0" />
                    <span>[-] {m.category.toUpperCase()}</span>
                  </div>
                  <span className="text-[10px] font-bold text-[var(--danger-text)] font-mono">
                    WT: +{(m.weight * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="text-[11px] text-[var(--text-primary)] font-mono italic">
                  "{m.matched_text}"
                </div>
                <p className="text-[10px] text-[var(--text-secondary)] font-sans">
                  {m.description}
                </p>
              </div>
            ))}

            {/* Exculpatory Markers */}
            {exculpatoryMarkers.map((m) => (
              <div
                key={m.marker_id}
                className="p-2.5 rounded bg-[var(--success-bg)] border border-[var(--success-border)] space-y-1 text-xs"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-[var(--success-text)] font-bold">
                    <ShieldCheck className="w-3.5 h-3.5 shrink-0" />
                    <span>[+] {m.category.toUpperCase()}</span>
                  </div>
                  <span className="text-[10px] font-bold text-[var(--success-text)] font-mono">
                    WT: {(m.weight * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="text-[11px] text-[var(--text-primary)] font-mono italic">
                  "{m.matched_text}"
                </div>
                <p className="text-[10px] text-[var(--text-secondary)] font-sans">
                  {m.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 3. Matched Playbooks (RAG Citations) ──────── */}
      {playbooks.length > 0 && (
        <div className="pt-2 border-t border-[var(--border-subtle)] space-y-2">
          <div className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider">
            RAG RETRIEVED ADVISORY PLAYBOOKS (I4C / MHA):
          </div>

          {playbooks.map((pb) => (
            <div
              key={pb.playbook_id}
              className="p-3 rounded bg-[var(--bg-primary)] border border-[var(--border-default)] space-y-1"
            >
              <div className="flex items-start justify-between gap-2">
                <h4 className="text-xs font-bold text-[var(--text-primary)] font-sans">
                  {pb.title}
                </h4>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--bg-secondary)] text-[var(--text-secondary)] border border-[var(--border-default)] font-bold shrink-0">
                  {(pb.similarity_score * 100).toFixed(0)}% MATCH
                </span>
              </div>

              <p className="text-[11px] text-[var(--text-muted)] font-sans italic leading-relaxed">
                "{pb.matched_excerpt}"
              </p>

              <div className="flex items-center justify-between text-[10px] pt-1 text-[var(--text-muted)]">
                <span>AUTHORITY: {pb.source_agency}</span>
                <a
                  href={pb.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[var(--accent)] hover:underline font-bold no-underline inline-flex items-center gap-1"
                >
                  <span>VERIFY ADVISORY</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
