import { useRef, useState, useEffect } from "react";
import type { MockScenario } from "../api/mock";

interface CallCheckerHeroProps {
  activeScenario: MockScenario | null;
  onSelectScenario: (scenario: MockScenario) => void;
  onUploadFile: (file: File) => void;
  isLoading: boolean;
}

export default function CallCheckerHero({
  activeScenario,
  onSelectScenario,
  onUploadFile,
  isLoading,
}: CallCheckerHeroProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isListening, setIsListening] = useState(false);
  const [listenTimer, setListenTimer] = useState(0);

  // Simulated live speakerphone microphone listening
  useEffect(() => {
    let interval: number;
    if (isListening) {
      setListenTimer(0);
      interval = window.setInterval(() => {
        setListenTimer((prev) => {
          if (prev >= 4) {
            setIsListening(false);
            onSelectScenario("red"); // simulates analysis completion
            return 0;
          }
          return prev + 1;
        });
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isListening, onSelectScenario]);

  return (
    <div className="clean-card p-5 sm:p-6 mb-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-5 pb-4 border-b border-[var(--color-border-subtle)]">
        <div>
          <h1 className="text-lg sm:text-xl font-bold text-[var(--color-text-primary)]">
            Check Suspicious Call or Voice Note
          </h1>
          <p className="text-sm text-[var(--color-text-secondary)] mt-0.5">
            Put the caller on speakerphone or upload an audio clip to detect AI voice cloning & scam patterns.
          </p>
        </div>

        {/* Big Friendly Actions */}
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => setIsListening(!isListening)}
            disabled={isLoading}
            className={`px-4 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 transition-all cursor-pointer shadow-sm ${
              isListening
                ? "bg-red-600 text-white animate-pulse"
                : "bg-blue-600 hover:bg-blue-500 text-white"
            }`}
          >
            <span>{isListening ? "⏹️" : "🎙️"}</span>
            <span>{isListening ? `Listening on Speakerphone (${listenTimer}s)...` : "Listen to Call (Speakerphone)"}</span>
          </button>

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className="px-4 py-2.5 rounded-xl text-sm font-medium bg-[var(--color-bg-secondary)] hover:bg-[var(--color-bg-surface)] text-[var(--color-text-primary)] border border-[var(--color-border-default)] transition-all cursor-pointer flex items-center gap-2"
          >
            <span>📁</span>
            <span>Upload Audio / Voice Note</span>
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
        </div>
      </div>

      {/* Demo Scenario Buttons (Clear Human Labels) */}
      <div>
        <div className="text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2.5">
          Try Example Scenarios:
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
          <button
            onClick={() => onSelectScenario("red")}
            className={`p-3 rounded-xl text-left border transition-all cursor-pointer ${
              activeScenario === "red"
                ? "bg-red-950/30 border-red-500/60 ring-1 ring-red-500/30"
                : "bg-[var(--color-bg-secondary)] border-[var(--color-border-subtle)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-bg-surface)]"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-bold text-red-400">🚨 Cloned Extortion Call</span>
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-red-950/60 text-red-300 border border-red-800/40">
                SCAM
              </span>
            </div>
            <p className="text-xs text-[var(--color-text-secondary)] leading-snug">
              Fake son claiming police arrest, demanding 50k UPI
            </p>
          </button>

          <button
            onClick={() => onSelectScenario("green")}
            className={`p-3 rounded-xl text-left border transition-all cursor-pointer ${
              activeScenario === "green"
                ? "bg-emerald-950/30 border-emerald-500/60 ring-1 ring-emerald-500/30"
                : "bg-[var(--color-bg-secondary)] border-[var(--color-border-subtle)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-bg-surface)]"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-bold text-emerald-400">🟢 Real Family Member</span>
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/40">
                SAFE
              </span>
            </div>
            <p className="text-xs text-[var(--color-text-secondary)] leading-snug">
              Authentic call from Rahul: "Reached office, see you at 7"
            </p>
          </button>

          <button
            onClick={() => onSelectScenario("unverified")}
            className={`p-3 rounded-xl text-left border transition-all cursor-pointer ${
              activeScenario === "unverified"
                ? "bg-slate-800/40 border-slate-400/60 ring-1 ring-slate-400/30"
                : "bg-[var(--color-bg-secondary)] border-[var(--color-border-subtle)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-bg-surface)]"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-bold text-slate-300">⚪ Automated Bank Call</span>
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                IVR
              </span>
            </div>
            <p className="text-xs text-[var(--color-text-secondary)] leading-snug">
              Legitimate HDFC bank statement notification
            </p>
          </button>

          <button
            onClick={() => onSelectScenario("insufficient")}
            className={`p-3 rounded-xl text-left border transition-all cursor-pointer ${
              activeScenario === "insufficient"
                ? "bg-zinc-800/40 border-zinc-500/60 ring-1 ring-zinc-500/30"
                : "bg-[var(--color-bg-secondary)] border-[var(--color-border-subtle)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-bg-surface)]"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-bold text-[var(--color-text-muted)]">⚠️ Short / Unclear Audio</span>
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                NOISE
              </span>
            </div>
            <p className="text-xs text-[var(--color-text-secondary)] leading-snug">
              0.6s static burst (safely declines to score)
            </p>
          </button>
        </div>
      </div>
    </div>
  );
}
