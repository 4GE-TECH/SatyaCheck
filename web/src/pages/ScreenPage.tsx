import useScreening from "../hooks/useScreening";
import type { MockScenario } from "../api/mock";
import { AlertTriangle, Loader2 } from "lucide-react";

import IdleCheckScreen from "../components/IdleCheckScreen";
import ElderlyVerdictCard from "../components/ElderlyVerdictCard";

export default function ScreenPage() {
  const { data, loading, error, screenFile, screenMock, clear } = useScreening();

  const handleSelectScenario = (scenario: MockScenario) => {
    screenMock(scenario);
  };

  const handleUploadFile = (file: File) => {
    screenFile(file);
  };

  const handleReset = () => {
    clear();
  };

  return (
    <div className="space-y-6 pb-12">
      {/* ── 1. LOADING STATE ─────────────────────────────── */}
      {loading && (
        <div className="sec-card p-12 text-center space-y-4 shadow-xl max-w-xl mx-auto" role="status" aria-live="polite">
          <Loader2 className="w-10 h-10 text-[var(--accent)] animate-spin mx-auto" />
          <div className="text-xl font-bold text-[var(--text-primary)] font-mono">
            Checking voice authenticity…
          </div>
          <p className="text-sm text-[var(--text-secondary)] font-sans">
            Listening for AI voice cloning and suspicious emergency extortion patterns.
          </p>
        </div>
      )}

      {/* ── 2. ERROR STATE ───────────────────────────────── */}
      {error && (
        <div className="p-4 rounded-xl bg-[var(--danger-bg)] border border-[var(--danger-border)] text-xs text-[var(--danger-text)] flex items-center gap-2 max-w-xl mx-auto">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span className="font-mono">{error}</span>
        </div>
      )}

      {/* ── 3. MAIN IDLE OR VERDICT VIEW ─────────────────── */}
      {!loading && !data && (
        <IdleCheckScreen
          onSelectScenario={handleSelectScenario}
          onUploadFile={handleUploadFile}
          isLoading={loading}
        />
      )}

      {!loading && data && (
        <ElderlyVerdictCard
          data={data}
          onReset={handleReset}
        />
      )}
    </div>
  );
}
