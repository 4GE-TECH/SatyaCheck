import { useRef, useState, useEffect } from "react";
import type { MockScenario } from "../api/mock";

interface IdleCheckScreenProps {
  onSelectScenario: (scenario: MockScenario) => void;
  onUploadFile: (file: File) => void;
  isLoading: boolean;
}

export default function IdleCheckScreen({
  onSelectScenario,
  onUploadFile,
  isLoading,
}: IdleCheckScreenProps) {
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
            onSelectScenario("red"); // simulates analysis of extortion call
            return 0;
          }
          return prev + 1;
        });
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isListening, onSelectScenario]);

  return (
    <div className="space-y-6">
      {/* ── Main Inviting Card ──────────────────────────────── */}
      <div className="p-8 sm:p-10 rounded-2xl bg-[#111827] border border-slate-700 shadow-xl text-center space-y-6">
        <div className="max-w-xl mx-auto space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-900/40 text-blue-300 text-xs font-semibold border border-blue-700/50">
            Instant Voice Verification
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight leading-tight">
            Check If a Call Is Real
          </h1>
          <p className="text-base sm:text-lg text-slate-300 leading-relaxed">
            Received a frightening or unexpected call asking for money? Put the phone on speakerphone or upload an audio note to check for AI voice cloning.
          </p>
        </div>

        {/* Big Touch-Friendly Buttons */}
        <div className="max-w-md mx-auto space-y-3 pt-2">
          <button
            onClick={() => setIsListening(!isListening)}
            disabled={isLoading}
            className={`w-full py-4 px-6 rounded-2xl text-lg font-bold transition-all cursor-pointer shadow-lg flex items-center justify-center gap-3 ${
              isListening
                ? "bg-red-600 text-white animate-pulse border-2 border-white"
                : "bg-blue-600 hover:bg-blue-500 text-white border-2 border-blue-400"
            }`}
          >
            <span className="text-2xl">{isListening ? "⏹" : "🎙"}</span>
            <span>
              {isListening
                ? `Listening on Speakerphone (${listenTimer}s)...`
                : "Listen to Call on Speakerphone"}
            </span>
          </button>

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className="w-full py-3.5 px-6 rounded-2xl text-base font-semibold bg-[#1F2937] hover:bg-[#374151] text-white border border-slate-600 transition-all cursor-pointer flex items-center justify-center gap-2"
          >
            <span>📁</span>
            <span>Upload WhatsApp Audio or Recording</span>
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

      {/* ── Discrete Demo Case Selector for Testing ─────────── */}
      <div className="p-5 rounded-2xl bg-[#0F172A] border border-slate-800 text-center space-y-3">
        <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          Or Test with an Example Call:
        </div>

        <div className="flex flex-wrap items-center justify-center gap-2.5">
          <button
            onClick={() => onSelectScenario("red")}
            className="px-4 py-2.5 rounded-xl text-sm font-semibold bg-red-950/40 text-red-300 border border-red-800/60 hover:bg-red-900/50 transition-colors cursor-pointer"
          >
            Test: Fake Son Extortion Call
          </button>

          <button
            onClick={() => onSelectScenario("green")}
            className="px-4 py-2.5 rounded-xl text-sm font-semibold bg-emerald-950/40 text-emerald-300 border border-emerald-800/60 hover:bg-emerald-900/50 transition-colors cursor-pointer"
          >
            Test: Real Son Calling
          </button>

          <button
            onClick={() => onSelectScenario("unverified")}
            className="px-4 py-2.5 rounded-xl text-sm font-semibold bg-slate-800 text-slate-300 border border-slate-700 hover:bg-slate-700 transition-colors cursor-pointer"
          >
            Test: Automated Bank Call
          </button>

          <button
            onClick={() => onSelectScenario("insufficient")}
            className="px-4 py-2.5 rounded-xl text-sm font-semibold bg-zinc-800 text-zinc-300 border border-zinc-700 hover:bg-zinc-700 transition-colors cursor-pointer"
          >
            Test: Short / Unclear Audio
          </button>
        </div>
      </div>
    </div>
  );
}
