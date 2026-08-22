/**
 * SignalBars — Three horizontal bars showing identity, authenticity, and intent risk.
 */

interface SignalBarProps {
  identityRisk: number;
  authenticityRiskEffective: number;
  intentRisk: number;
}

interface BarRowProps {
  label: string;
  value: number;
  color: string;
  description: string;
}

function BarRow({ label, value, color, description }: BarRowProps) {
  const pct = Math.round(value * 100);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color }}>
          {label}
        </span>
        <span
          className="text-xs font-mono tabular-nums"
          style={{ color: "var(--color-text-secondary)" }}
        >
          {pct}%
        </span>
      </div>
      <div
        className="h-2 rounded-full overflow-hidden"
        style={{ backgroundColor: "var(--color-bg-primary)" }}
      >
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{
            width: `${Math.max(pct, 2)}%`,
            backgroundColor: color,
            boxShadow: `0 0 8px ${color}66`,
          }}
        />
      </div>
      <p
        className="text-xs leading-snug"
        style={{ color: "var(--color-text-muted)" }}
      >
        {description}
      </p>
    </div>
  );
}

export default function SignalBars({
  identityRisk,
  authenticityRiskEffective,
  intentRisk,
}: SignalBarProps) {
  return (
    <div
      className="rounded-xl p-4 space-y-4"
      style={{
        backgroundColor: "var(--color-bg-card)",
        border: "1px solid var(--color-border-subtle)",
      }}
    >
      <h3
        className="text-xs font-semibold uppercase tracking-wider"
        style={{ color: "var(--color-text-muted)" }}
      >
        Signal breakdown
      </h3>

      <BarRow
        label="Identity"
        value={identityRisk}
        color="var(--color-signal-identity)"
        description="Speaker voiceprint match confidence"
      />

      <BarRow
        label="Authenticity"
        value={authenticityRiskEffective}
        color="var(--color-signal-authenticity)"
        description="Synthetic speech risk (intent-gated)"
      />

      <BarRow
        label="Intent"
        value={intentRisk}
        color="var(--color-signal-intent)"
        description="Scam script and marker analysis"
      />
    </div>
  );
}
