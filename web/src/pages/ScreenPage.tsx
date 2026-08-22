import useScreening from "../hooks/useScreening";
import type { MockScenario } from "../api/mock";

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
        <div className="p-12 rounded-2xl bg-[#111827] border border-slate-700 text-center space-y-4 shadow-xl">
          <div className="w-12 h-12 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mx-auto"></div>
          <div className="text-xl font-bold text-white">
            Checking voice authenticity…
          </div>
          <p className="text-sm text-slate-300">
            Listening for AI voice cloning and suspicious emergency patterns.
          </p>
        </div>
      )}

      {/* ── 2. ERROR STATE ───────────────────────────────── */}
      {error && (
        <div className="p-5 rounded-2xl bg-amber-950/60 border border-amber-500/50 text-sm text-amber-200">
          ⚠️ {error}
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
