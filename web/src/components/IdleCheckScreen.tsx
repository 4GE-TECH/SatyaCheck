import { useRef, useState, useEffect } from "react";
import type { MockScenario } from "../api/mock";
import { PearlButton } from "@/components/ui/pearl-button";

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
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* ── Main Hero Card ──────────────────────────────── */}
      <div className="sec-card p-8 sm:p-14 text-center space-y-8 relative overflow-hidden">
        {/* Glow behind the hero */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 h-80 bg-sky-500/5 rounded-full blur-3xl pointer-events-none" />

        {/* Pulsing Audio Radar Icon */}
        <div className="flex justify-center relative">
          <div className="relative flex items-center justify-center">
            {isListening && (
              <>
                <div className="absolute w-28 h-28 rounded-full border border-red-500/50 animate-ping pointer-events-none" />
                <div className="absolute w-36 h-36 rounded-full border border-red-500/30 animate-pulse pointer-events-none" />
              </>
            )}
            <div
              className={`w-20 h-20 rounded-2xl flex items-center justify-center shadow-2xl border transition-all ${
                isListening
                  ? "bg-red-950/80 border-red-500 text-red-400"
                  : "bg-[var(--bg-secondary)] border-[var(--border-default)] text-[var(--accent)]"
              }`}
            >
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="22" />
              </svg>
            </div>
          </div>
        </div>

        <div className="max-w-2xl mx-auto space-y-3 relative z-10">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[var(--bg-secondary)] text-[var(--text-secondary)] text-xs font-mono font-semibold border border-[var(--border-default)]">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-pulse" />
            <span>INSTANT VOICE VERIFICATION SYSTEM</span>
          </div>

          <h1 className="text-3xl sm:text-4xl font-extrabold text-[var(--text-primary)] tracking-tight leading-tight">
            Check If a Call Is Real
          </h1>
          <p className="text-base sm:text-lg text-[var(--text-secondary)] leading-relaxed max-w-xl mx-auto font-sans">
            Received an unexpected call asking for money? Put the phone on speakerphone or upload an audio note to verify against deepfake AI voice cloning.
          </p>
        </div>

        {/* Big Pearl Buttons */}
        <div className="max-w-md mx-auto space-y-3.5 pt-2 relative z-10 flex flex-col items-center">
          <PearlButton
            onClick={() => setIsListening(!isListening)}
            disabled={isLoading}
            variant={isListening ? "danger" : "default"}
            size="lg"
            className="w-full flex items-center justify-center font-mono shadow-lg"
            label={
              isListening
                ? `Listening on Speakerphone (${listenTimer}s)...`
                : "Listen to Call on Speakerphone"
            }
            icon={
              <span className={`w-2 h-2 rounded-full mr-1 ${isListening ? "bg-red-400 animate-ping" : "bg-sky-400"}`} />
            }
          />

          <PearlButton
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            variant="secondary"
            size="md"
            className="w-full font-mono"
            label="Upload WhatsApp Audio or Recording"
            icon={<span>📁</span>}
          />

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
      <div className="sec-card-subtle p-5 sm:p-6 text-center space-y-3.5">
        <div className="text-xs font-mono font-bold text-[var(--text-muted)] uppercase tracking-wider">
          Or Test with an Example Incident Probe:
        </div>

        <div className="flex flex-wrap items-center justify-center gap-2.5">
          <PearlButton
            onClick={() => onSelectScenario("red")}
            variant="danger"
            size="sm"
            label="Test: Fake Son Extortion Call"
          />

          <PearlButton
            onClick={() => onSelectScenario("green")}
            variant="success"
            size="sm"
            label="Test: Real Son Calling"
          />

          <PearlButton
            onClick={() => onSelectScenario("unverified")}
            variant="secondary"
            size="sm"
            label="Test: Automated Bank Call"
          />

          <PearlButton
            onClick={() => onSelectScenario("insufficient")}
            variant="secondary"
            size="sm"
            label="Test: Short / Unclear Audio"
          />
        </div>
      </div>
    </div>
  );
}
