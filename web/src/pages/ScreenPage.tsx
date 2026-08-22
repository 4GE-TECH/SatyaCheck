import { useState } from "react";
import useScreening from "../hooks/useScreening";
import type { MockScenario } from "../api/mock";

import StreamControlHUD from "../components/StreamControlHUD";
import MonolithicVerdictHUD from "../components/MonolithicVerdictHUD";
import TechnicalForensicsAccordion from "../components/TechnicalForensicsAccordion";

export default function ScreenPage() {
  const { data, loading, error, screenFile, screenMock } = useScreening();
  const [selectedScenario, setSelectedScenario] = useState<MockScenario | null>("red");

  // Initial load default to "red" so the user immediately sees the focal verdict
  useState(() => {
    screenMock("red");
  });

  const handleSelectScenario = (scenario: MockScenario) => {
    setSelectedScenario(scenario);
    screenMock(scenario);
  };

  const handleUploadFile = (file: File) => {
    setSelectedScenario(null);
    screenFile(file);
  };

  return (
    <div className="space-y-6 pb-12">
      {/* 1. Stream Control & Case Ingest */}
      <StreamControlHUD
        activeScenario={selectedScenario}
        onSelectScenario={handleSelectScenario}
        onUploadFile={handleUploadFile}
        isLoading={loading}
      />

      {/* 2. Loading State */}
      {loading && (
        <div className="hud-panel p-12 flex flex-col items-center justify-center gap-3 text-center">
          <div className="w-8 h-8 border-2 border-white/20 border-t-white rounded-full animate-spin"></div>
          <div className="text-xs font-mono font-bold tracking-wider text-white">
            COMPUTING ACOUSTIC EMBEDDINGS & SPEECH SYNTHESIS SIGNATURES...
          </div>
          <div className="text-[11px] font-mono text-zinc-500">
            ECAPA-TDNN / AASIST-CM / BGE-M3 / INTENT GATING
          </div>
        </div>
      )}

      {/* 3. System Advisory Error */}
      {error && (
        <div className="p-4 rounded bg-rose-950/40 border border-rose-600/60 text-xs font-mono text-rose-200">
          SYSTEM ADVISORY: {error}
        </div>
      )}

      {/* 4. Monolithic Focus Verdict & Action Directives */}
      {!loading && data && (
        <div className="space-y-6">
          <MonolithicVerdictHUD data={data} />
          <TechnicalForensicsAccordion data={data} />
        </div>
      )}
    </div>
  );
}
