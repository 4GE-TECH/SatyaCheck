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

  useEffect(() => {
    let interval: number;
    if (isListening) {
      setListenTimer(0);
      interval = window.setInterval(() => {
        setListenTimer((prev) => {
          if (prev >= 4) {
            setIsListening(false);
            onSelectScenario("red");
            return 0;
          }
          return prev + 1;
        });
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isListening, onSelectScenario]);

  return (
    <div className="space-y-5">
      {/* ── Main Inviting Card ──────────────────────────────── */}
      <div className="sec-card p-6 sm:p-10 text-center space-y-6">
        <div className="max-w-xl mx-auto space-y-2.5">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[var(--bg-secondary)] text-[var(--text-secondary)] text-xs font-semibold border border-[var(--border-default)]">
            Instant Voice Verification
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-[var(--text-primary)] tracking-tight leading-tight">
            Check If a Call Is Real
          </h1>
          <p className="text-sm sm:text-base text-[var(--text-secondary)] leading-relaxed">
            Received an unexpected call asking for money? Put the phone on speakerphone or upload an audio note to check for AI voice cloning.
          </p>
        </div>

        {/* Big Touch-Friendly Buttons */}
        <div className="max-w-md mx-auto space-y-3 pt-1">
          <button
            onClick={() => setIsListening(!isListening)}
            disabled={isLoading}
            className={`w-full py-3.5 px-6 rounded-lg text-base font-bold transition-all cursor-pointer shadow-sm flex items-center justify-center gap-2.5 ${
              isListening
                ? "bg-[var(--danger)] text-white animate-pulse"
                : "bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-text)]"
            }`}
          >
            <span>
              {isListening
                ? `Listening on Speakerphone (${listenTimer}s)...`
                : "Listen to Call on Speakerphone"}
            </span>
          </button>

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className="w-full py-3 px-6 rounded-lg text-sm font-semibold bg-[var(--bg-secondary)] hover:bg-[var(--bg-hover)] text-[var(--text-primary)] border border-[var(--border-default)] transition-colors cursor-pointer flex items-center justify-center gap-2"
          >
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
      <div className="sec-card-subtle p-4 sm:p-5 text-center space-y-3">
        <div className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider">
          Or Test with an Example Call:
        </div>

        <div className="flex flex-wrap items-center justify-center gap-2">
          <button
            onClick={() => onSelectScenario("red")}
            className="px-3 py-2 rounded-md text-xs font-semibold bg-[var(--danger-bg)] text-[var(--danger-text)] border border-[var(--danger-border)] hover:opacity-90 transition-opacity cursor-pointer"
          >
            Test: Fake Son Extortion Call
          </button>

          <button
            onClick={() => onSelectScenario("green")}
            className="px-3 py-2 rounded-md text-xs font-semibold bg-[var(--success-bg)] text-[var(--success-text)] border border-[var(--success-border)] hover:opacity-90 transition-opacity cursor-pointer"
          >
            Test: Real Son Calling
          </button>

          <button
            onClick={() => onSelectScenario("unverified")}
            className="px-3 py-2 rounded-md text-xs font-semibold bg-[var(--bg-primary)] text-[var(--text-secondary)] border border-[var(--border-default)] hover:bg-[var(--bg-hover)] transition-colors cursor-pointer"
          >
            Test: Automated Bank Call
          </button>

          <button
            onClick={() => onSelectScenario("insufficient")}
            className="px-3 py-2 rounded-md text-xs font-semibold bg-[var(--bg-primary)] text-[var(--text-muted)] border border-[var(--border-default)] hover:bg-[var(--bg-hover)] transition-colors cursor-pointer"
          >
            Test: Short / Unclear Audio
          </button>
        </div>
      </div>
    </div>
  );
}
