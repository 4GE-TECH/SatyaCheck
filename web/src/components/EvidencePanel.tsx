import type { ReasonCode, MarkerMatch, RetrievedPlaybook } from "../types/contracts";
import { SeverityLevel } from "../types/contracts";

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

      {/* Reason Codes Stream */}
      <div className="space-y-2">
        {reasonCodes.map((rc) => {
          const badge = SEVERITY_BADGES[rc.severity] || SEVERITY_BADGES[SeverityLevel.INFO];

          return (
            <div
              key={rc.code}
              className="p-3 rounded bg-[var(--bg-primary)] border border-[var(--border-default)] transition-colors space-y-1.5"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-[9px] px-1.5 py-0.2 rounded font-bold uppercase border ${badge.bg} ${badge.text} ${badge.border}`}
                  >
                    {badge.label}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-[var(--bg-secondary)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
                    {rc.signal.toUpperCase()}
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
                    className="text-[var(--accent)] hover:underline font-bold no-underline"
                  >
                    <span>{rc.citation_title || "Official Crime Advisory"} →</span>
                  </a>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Matched Playbooks */}
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
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[var(--bg-secondary)] text-[var(--text-secondary)] border border-[var(--border-default)] font-bold shrink-0">
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
                  className="text-[var(--accent)] hover:underline font-bold no-underline"
                >
                  VERIFY ADVISORY →
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
