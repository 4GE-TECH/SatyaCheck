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
    bg: "bg-rose-950/80",
    text: "text-rose-300",
    border: "border-rose-700/60",
  },
  [SeverityLevel.HIGH]: {
    label: "HIGH",
    bg: "bg-orange-950/80",
    text: "text-orange-300",
    border: "border-orange-700/60",
  },
  [SeverityLevel.MEDIUM]: {
    label: "MEDIUM",
    bg: "bg-amber-950/80",
    text: "text-amber-300",
    border: "border-amber-700/60",
  },
  [SeverityLevel.LOW]: {
    label: "LOW",
    bg: "bg-emerald-950/80",
    text: "text-emerald-300",
    border: "border-emerald-700/60",
  },
  [SeverityLevel.INFO]: {
    label: "INFO",
    bg: "bg-zinc-900",
    text: "text-zinc-300",
    border: "border-zinc-700",
  },
};

export default function EvidencePanel({
  reasonCodes,
  playbooks,
}: EvidencePanelProps) {
  return (
    <div className="hud-panel p-4 space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-white/10 font-mono">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-white"></span>
          <h3 className="text-xs font-bold uppercase tracking-wider text-white">
            CITABLE EVIDENCE CODES & ADVISORY REASONING
          </h3>
        </div>
        <span className="text-[10px] text-zinc-500">
          {reasonCodes.length} CODES · {playbooks.length} PLAYBOOKS
        </span>
      </div>

      {/* Reason Codes Stream */}
      <div className="space-y-2.5">
        {reasonCodes.map((rc) => {
          const badge = SEVERITY_BADGES[rc.severity] || SEVERITY_BADGES[SeverityLevel.INFO];

          return (
            <div
              key={rc.code}
              className="p-3 rounded bg-[#050505] border border-white/10 hover:border-white/20 transition-all font-mono"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-[9px] px-1.5 py-0.2 rounded font-bold uppercase border ${badge.bg} ${badge.text} ${badge.border}`}
                  >
                    {badge.label}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-white/5 text-zinc-400 border border-white/10">
                    {rc.signal.toUpperCase()}
                  </span>
                  <span className="text-xs font-bold text-white">
                    {rc.code}
                  </span>
                </div>

                <div className="flex items-center gap-2 text-[10px] text-zinc-500">
                  <span>
                    OBSERVED: <span className="text-white font-bold">{rc.value}</span>
                  </span>
                  {rc.threshold && (
                    <span>
                      / THRESHOLD: <span className="text-zinc-400">{rc.threshold}</span>
                    </span>
                  )}
                </div>
              </div>

              <p className="text-xs text-zinc-300 leading-relaxed mb-2 font-sans">
                {rc.explanation}
              </p>

              {rc.citation_url && (
                <div className="flex items-center justify-between pt-1.5 border-t border-white/10 text-[10px] font-mono">
                  <span className="text-zinc-500">OFFICIAL CITATION:</span>
                  <a
                    href={rc.citation_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-white hover:text-zinc-300 font-bold no-underline"
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
        <div className="pt-2 border-t border-white/10 space-y-2 font-mono">
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider">
            RAG RETRIEVED ADVISORY PLAYBOOKS (I4C / MHA):
          </div>

          {playbooks.map((pb) => (
            <div
              key={pb.playbook_id}
              className="p-3 rounded bg-[#030303] border border-white/10 space-y-1.5"
            >
              <div className="flex items-start justify-between gap-2">
                <h4 className="text-xs font-bold text-white font-sans">
                  {pb.title}
                </h4>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-white/10 text-white border border-white/20 font-bold shrink-0">
                  {(pb.similarity_score * 100).toFixed(0)}% MATCH
                </span>
              </div>

              <p className="text-[11px] text-zinc-400 font-sans italic leading-relaxed">
                "{pb.matched_excerpt}"
              </p>

              <div className="flex items-center justify-between text-[10px] font-mono pt-1 text-zinc-500">
                <span>AUTHORITY: {pb.source_agency}</span>
                <a
                  href={pb.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-white hover:text-zinc-300 font-bold no-underline"
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
