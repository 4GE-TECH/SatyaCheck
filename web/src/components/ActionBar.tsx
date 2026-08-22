import { useState } from "react";
import { Link } from "react-router-dom";

interface ActionBarProps {
  actions: string[];
  vernacularWarning: string | null;
}

export default function ActionBar({ actions, vernacularWarning }: ActionBarProps) {
  const [completedSteps, setCompletedSteps] = useState<Record<number, boolean>>({});

  const toggleStep = (index: number) => {
    setCompletedSteps((prev) => ({ ...prev, [index]: !prev[index] }));
  };

  if (actions.length === 0 && !vernacularWarning) return null;

  return (
    <div className="panel-card p-4 space-y-3">
      <div className="flex items-center justify-between pb-2 border-b border-[var(--color-border-subtle)]">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-red-400"></span>
          <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
            Incident Response Protocol & Next Steps
          </h3>
        </div>
        <span className="text-[10px] font-mono text-[var(--color-text-muted)]">
          GUARDIAN DIRECTIVES
        </span>
      </div>

      <div className="space-y-2">
        {actions.map((action, i) => {
          const isDone = !!completedSteps[i];

          return (
            <div
              key={i}
              onClick={() => toggleStep(i)}
              className={`p-2.5 rounded-lg border flex items-start gap-3 transition-all cursor-pointer select-none ${
                isDone
                  ? "bg-[var(--color-bg-root)] border-[var(--color-border-subtle)] opacity-60 line-through"
                  : "bg-[var(--color-bg-secondary)] border-[var(--color-border-subtle)] hover:border-[var(--color-border-strong)]"
              }`}
            >
              <div
                className={`w-4 h-4 rounded mt-0.5 flex items-center justify-center text-[10px] font-bold shrink-0 transition-colors ${
                  isDone
                    ? "bg-emerald-500 text-black"
                    : "border border-[var(--color-border-strong)] text-[var(--color-text-muted)]"
                }`}
              >
                {isDone ? "✓" : i + 1}
              </div>

              <div className="text-xs text-[var(--color-text-primary)] font-medium font-sans leading-snug">
                {action}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-[var(--color-border-subtle)] text-[11px] font-mono">
        <span className="text-[var(--color-text-muted)]">
          NATIONAL CYBER HELPLINE: <span className="text-red-400 font-bold">1930</span>
        </span>
        <Link
          to="/report"
          className="text-cyan-400 hover:text-cyan-300 font-semibold no-underline flex items-center gap-1"
        >
          <span>FILE COMPLAINT ON 1930 / CHAKSHU PORTAL →</span>
        </Link>
      </div>
    </div>
  );
}
