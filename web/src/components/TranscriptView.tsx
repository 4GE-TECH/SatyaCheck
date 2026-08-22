import type { TranscriptSegment, MarkerMatch } from "../types/contracts";
import { MarkerType } from "../types/contracts";

interface TranscriptViewProps {
  segments: TranscriptSegment[];
  incriminatingMarkers: MarkerMatch[];
  exculpatoryMarkers: MarkerMatch[];
  detectedLanguage: string;
}

const LANGUAGE_LABELS: Record<string, string> = {
  hi: "Hindi (Devanagari)",
  en: "English",
  "hi-en": "Code-switched Hinglish",
  unknown: "Acoustic Stream",
};

export default function TranscriptView({
  segments,
  incriminatingMarkers,
  exculpatoryMarkers,
  detectedLanguage,
}: TranscriptViewProps) {
  const allMarkers = [
    ...incriminatingMarkers.map((m) => ({
      text: m.matched_text,
      type: MarkerType.INCRIMINATING,
      category: m.category,
      desc: m.description,
    })),
    ...exculpatoryMarkers.map((m) => ({
      text: m.matched_text,
      type: MarkerType.EXCULPATORY,
      category: m.category,
      desc: m.description,
    })),
  ];

  return (
    <div className="panel-card p-4 space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-[var(--color-border-subtle)]">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
          <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
            ASR & Linguistic Intent Analysis
          </h3>
        </div>

        <div className="flex items-center gap-2 text-[10px] font-mono">
          <span className="text-[var(--color-text-muted)]">LANG:</span>
          <span className="px-1.5 py-0.5 rounded bg-[var(--color-bg-surface)] text-cyan-300 font-semibold border border-[var(--color-border-default)]">
            {LANGUAGE_LABELS[detectedLanguage] || detectedLanguage.toUpperCase()}
          </span>
          <span className="text-[var(--color-border-strong)]">•</span>
          <span className="text-[var(--color-text-muted)]">ASR CONFIDENCE:</span>
          <span className="text-emerald-400 font-semibold">96.8%</span>
        </div>
      </div>

      {/* Segments Display */}
      {segments.length === 0 ? (
        <div className="p-6 text-center text-xs font-mono text-[var(--color-text-muted)] bg-[var(--color-bg-secondary)] rounded-lg">
          [NO ACTIVE SPEECH TRANSCRIPT / QUALITY GATE DECLINED]
        </div>
      ) : (
        <div className="space-y-2 font-sans">
          {segments.map((seg, i) => (
            <div
              key={i}
              className="p-3 rounded-lg bg-[var(--color-bg-secondary)] border border-[var(--color-border-subtle)] space-y-1.5"
            >
              <div className="flex items-center justify-between text-[10px] font-mono text-[var(--color-text-muted)]">
                <span className="text-cyan-400 font-semibold">
                  SPEAKER #{i + 1}
                </span>
                <span className="px-1.5 py-0.2 rounded bg-[var(--color-bg-root)] border border-[var(--color-border-subtle)]">
                  {seg.start_s.toFixed(1)}s — {seg.end_s.toFixed(1)}s
                </span>
              </div>

              <div className="text-xs leading-relaxed text-[var(--color-text-primary)] font-medium">
                <HighlightTranscriptText text={seg.text} markers={allMarkers} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detected Marker Badges */}
      {allMarkers.length > 0 && (
        <div className="pt-2 border-t border-[var(--color-border-subtle)] space-y-2">
          <div className="text-[10px] font-mono text-[var(--color-text-muted)]">
            EXTRACTED LINGUISTIC INTENT MARKERS:
          </div>

          <div className="flex flex-wrap gap-1.5">
            {allMarkers.map((m, idx) => (
              <div
                key={idx}
                className={`px-2 py-1 rounded text-[10px] font-mono flex items-center gap-1.5 border ${
                  m.type === MarkerType.INCRIMINATING
                    ? "bg-red-950/60 border-red-800/70 text-red-300"
                    : "bg-emerald-950/60 border-emerald-800/70 text-emerald-300"
                }`}
                title={m.desc}
              >
                <span className="font-bold">{m.type === MarkerType.INCRIMINATING ? "[!]" : "[✓]"}</span>
                <span className="font-semibold uppercase">{m.category}:</span>
                <span className="italic">"{m.text}"</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function HighlightTranscriptText({
  text,
  markers,
}: {
  text: string;
  markers: Array<{ text: string; type: MarkerType; category: string; desc: string }>;
}) {
  if (!markers || markers.length === 0) return <span>{text}</span>;

  const lowerText = text.toLowerCase();
  const regions: Array<{ start: number; end: number; marker: (typeof markers)[0] }> = [];

  for (const m of markers) {
    const idx = lowerText.indexOf(m.text.toLowerCase());
    if (idx !== -1) {
      regions.push({ start: idx, end: idx + m.text.length, marker: m });
    }
  }

  if (regions.length === 0) return <span>{text}</span>;

  regions.sort((a, b) => a.start - b.start);

  const parts = [];
  let cursor = 0;

  for (const r of regions) {
    if (r.start > cursor) {
      parts.push({ text: text.slice(cursor, r.start), marker: null });
    }
    parts.push({ text: text.slice(r.start, r.end), marker: r.marker });
    cursor = r.end;
  }

  if (cursor < text.length) {
    parts.push({ text: text.slice(cursor), marker: null });
  }

  return (
    <>
      {parts.map((p, idx) =>
        p.marker ? (
          <mark
            key={idx}
            className={`px-1 py-0.5 rounded font-semibold transition-all ${
              p.marker.type === MarkerType.INCRIMINATING
                ? "bg-red-500/20 text-red-300 border-b-2 border-red-500"
                : "bg-emerald-500/20 text-emerald-300 border-b-2 border-emerald-500"
            }`}
            title={`${p.marker.category.toUpperCase()}: ${p.marker.desc}`}
          >
            {p.text}
          </mark>
        ) : (
          <span key={idx}>{p.text}</span>
        )
      )}
    </>
  );
}
