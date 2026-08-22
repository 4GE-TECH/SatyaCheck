import { useRef, useState, useEffect } from "react";
import { type MockScenario, SCENARIO_LABELS } from "../api/mock";

interface SessionTriageBarProps {
  activeScenario: MockScenario | null;
  onSelectScenario: (scenario: MockScenario) => void;
  onUploadFile: (file: File) => void;
  isLoading: boolean;
  onReset: () => void;
}

const CASE_METADATA: Record<
  MockScenario,
  {
    id: string;
    caller: string;
    type: string;
    status: "pass" | "threat" | "neutral" | "refused";
    tag: string;
  }
> = {
  green: {
    id: "CASE-0841",
    caller: "+91 98112 04829",
    type: "Enrolled Contact (Rahul)",
    status: "pass",
    tag: "Genuine Family",
  },
  red: {
    id: "CASE-0842",
    caller: "+91 70428 19043",
    type: "Deepfake Impersonation",
    status: "threat",
    tag: "Cloned Voice Extortion",
  },
  unverified: {
    id: "CASE-0843",
    caller: "1800-202-6161 (IVR)",
    type: "Automated Banking Service",
    status: "neutral",
    tag: "Legitimate Automated",
  },
  insufficient: {
    id: "CASE-0844",
    caller: "+91 88001 92831",
    type: "Burst / Telephony Static",
    status: "refused",
    tag: "Quality Gate Refusal",
  },
};

export default function SessionTriageBar({
  activeScenario,
  onSelectScenario,
  onUploadFile,
  isLoading,
  onReset,
}: SessionTriageBarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isLiveListening, setIsLiveListening] = useState(false);
  const [liveDuration, setLiveDuration] = useState(0);

  // Simulated live microphone recording
  useEffect(() => {
    let timer: number;
    if (isLiveListening) {
      setLiveDuration(0);
      timer = window.setInterval(() => {
        setLiveDuration((prev) => {
          if (prev >= 4) {
            setIsLiveListening(false);
            onSelectScenario("red"); // triggers live analysis of simulated speech
            return 0;
          }
          return prev + 1;
        });
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [isLiveListening, onSelectScenario]);

  return (
    <div className="panel-card p-3 sm:p-4 mb-5">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pb-3 border-b border-[var(--color-border-subtle)]">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
          <h2 className="text-xs font-mono font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
            Inbound Call Triage & Evidence Ingestion
          </h2>
        </div>

        <div className="flex items-center gap-2">
          {/* Live Speakerphone Mic Toggle */}
          <button
            onClick={() => setIsLiveListening(!isLiveListening)}
            disabled={isLoading}
            className={`px-3 py-1.5 rounded text-xs font-mono font-medium flex items-center gap-2 transition-all cursor-pointer border ${
              isLiveListening
                ? "bg-red-950/60 border-red-600 text-red-300 animate-pulse"
                : "bg-[var(--color-bg-surface)] border-[var(--color-border-default)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-elevated)]"
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isLiveListening ? "bg-red-500" : "bg-zinc-500"
              }`}
            ></span>
            {isLiveListening
              ? `LISTENING ON SPEAKERPHONE (${liveDuration}s)...`
              : "SPEAKERPHONE CAPTURE"}
          </button>

          {/* Upload Button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className="px-3 py-1.5 rounded text-xs font-mono font-medium bg-[var(--color-bg-surface)] border border-[var(--color-border-default)] text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-elevated)] hover:text-white flex items-center gap-1.5 transition-all cursor-pointer"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            UPLOAD PROBE (.WAV/MP3)
          </button>

          <input
            ref={fileInputRef}
            type="file"
            accept="audio/*,.wav,.mp3,.ogg,.webm,.m4a,.flac"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onUploadFile(file);
            }}
          />

          {activeScenario && (
            <button
              onClick={onReset}
              className="px-2.5 py-1.5 rounded text-xs font-mono text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-surface)] transition-all cursor-pointer"
              title="Reset View"
            >
              CLEAR
            </button>
          )}
        </div>
      </div>

      {/* Case Selector Grid */}
      <div className="pt-3">
        <div className="text-[11px] font-mono text-[var(--color-text-muted)] mb-2 flex items-center justify-between">
          <span>SELECT TEST CASE / LIVE REPLAY FEED:</span>
          <span>PROTOCOL: 16k/8k AMR-NB</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
          {(Object.keys(CASE_METADATA) as MockScenario[]).map((key) => {
            const meta = CASE_METADATA[key];
            const isSelected = activeScenario === key;

            return (
              <button
                key={key}
                onClick={() => onSelectScenario(key)}
                disabled={isLoading}
                className={`p-2.5 rounded-md text-left transition-all border font-mono cursor-pointer relative overflow-hidden ${
                  isSelected
                    ? "bg-[var(--color-bg-elevated)] border-cyan-500/60 shadow-[0_0_15px_rgba(6,182,212,0.12)] ring-1 ring-cyan-500/40"
                    : "bg-[var(--color-bg-surface)] border-[var(--color-border-subtle)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-bg-elevated)]"
                }`}
              >
                {/* Status bar */}
                <div
                  className={`absolute top-0 left-0 bottom-0 w-1 ${
                    meta.status === "pass"
                      ? "bg-emerald-500"
                      : meta.status === "threat"
                      ? "bg-red-500"
                      : meta.status === "neutral"
                      ? "bg-slate-400"
                      : "bg-zinc-600"
                  }`}
                />

                <div className="pl-2">
                  <div className="flex items-center justify-between gap-1 mb-1">
                    <span className="text-[10px] text-[var(--color-text-muted)] tracking-wider">
                      {meta.id}
                    </span>
                    <span
                      className={`text-[9px] px-1.5 py-0.2 rounded font-semibold uppercase ${
                        meta.status === "pass"
                          ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60"
                          : meta.status === "threat"
                          ? "bg-red-950/80 text-red-300 border border-red-800/60"
                          : meta.status === "neutral"
                          ? "bg-slate-800 text-slate-300 border border-slate-700"
                          : "bg-zinc-800 text-zinc-400 border border-zinc-700"
                      }`}
                    >
                      {meta.tag}
                    </span>
                  </div>

                  <div className="text-xs font-sans font-semibold text-[var(--color-text-primary)] truncate">
                    {meta.caller}
                  </div>
                  <div className="text-[11px] font-sans text-[var(--color-text-muted)] truncate">
                    {SCENARIO_LABELS[key]}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
