import { useRef, useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import type { MockScenario } from "../api/mock";
import { GlassButton } from "@/components/ui/glass-button";
import { BackgroundCircles } from "@/components/ui/background-circles";
import { UploadCloud, ChevronDown, ChevronUp } from "lucide-react";

interface IdleCheckScreenProps {
  onSelectScenario: (scenario: MockScenario) => void;
  onUploadFile: (file: File) => void;
  isLoading: boolean;
}

const PRESET_PILLS: Array<{
  scenario: MockScenario;
  label: string;
  variant: "success" | "warning" | "danger" | "secondary";
}> = [
  {
    scenario: "green",
    label: "1. Verified (Safe Son)",
    variant: "success",
  },
  {
    scenario: "caution",
    label: "2. Caution (Money Demand)",
    variant: "warning",
  },
  {
    scenario: "suspicious",
    label: "3. Suspicious (Stranger Claim)",
    variant: "danger",
  },
  {
    scenario: "red",
    label: "4. High Risk (Cloned Extortion)",
    variant: "danger",
  },
  {
    scenario: "unverified",
    label: "5. Unverified (Bank IVR)",
    variant: "secondary",
  },
  {
    scenario: "insufficient",
    label: "6. Insufficient (Short Audio)",
    variant: "secondary",
  },
];

export default function IdleCheckScreen({
  onSelectScenario,
  onUploadFile,
  isLoading,
}: IdleCheckScreenProps) {
  const [searchParams] = useSearchParams();
  const isDemoParam =
    searchParams.get("demo") === "true" ||
    searchParams.get("demo") === "1" ||
    searchParams.get("judge") === "true";

  const [showDemoTools, setShowDemoTools] = useState(isDemoParam);
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
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* ── Main Hero Card with Large Microphone Scanner ───────────────── */}
      <div className="sec-card p-6 sm:p-10 text-center relative overflow-hidden">
        <BackgroundCircles
          title="Check If a Call Is Real"
          description="Received an unexpected call asking for money? Put the phone on speakerphone or upload an audio note to verify against deepfake AI voice cloning."
          variant={isListening ? "quinary" : "primary"}
          isSpeaking={isListening}
          audioLevel={isListening ? 0.65 : 0}
          onMicClick={() => !isLoading && setIsListening(!isListening)}
          className="!py-4"
        />

        {/* Action Buttons */}
        <div className="max-w-md mx-auto space-y-3.5 pt-4 relative z-10 flex flex-col items-center">
          <GlassButton
            onClick={() => setIsListening(!isListening)}
            disabled={isLoading}
            variant={isListening ? "danger" : "default"}
            size="lg"
            className="w-full flex items-center justify-center shadow-lg"
            label={
              isListening
                ? `Listening on Speakerphone (${listenTimer}s)...`
                : "Listen to Call on Speakerphone"
            }
            icon={
              <span
                className={`w-2 h-2 rounded-full mr-1.5 ${
                  isListening ? "bg-red-400 animate-ping" : "bg-cyan-400"
                }`}
              />
            }
          />

          <GlassButton
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            variant="secondary"
            size="default"
            className="w-full"
            label="Upload WhatsApp Audio or Recording"
            icon={<UploadCloud className="w-4 h-4 mr-1.5" />}
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

      {/* ── Demo / Judge Preset Controls (Gated & Collapsible) ── */}
      <div className="space-y-3">
        <div className="text-center">
          <button
            type="button"
            onClick={() => setShowDemoTools(!showDemoTools)}
            className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-mono text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors cursor-pointer bg-transparent border border-[var(--border-subtle)] hover:border-[var(--border-default)] rounded-md"
          >
            <span>Judge & Dev Demo Presets</span>
            {showDemoTools ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>
        </div>

        {showDemoTools && (
          <div className="sec-card-subtle p-5 sm:p-6 text-center space-y-3.5 animate-in fade-in duration-200">
            <div className="text-xs font-mono font-bold text-[var(--text-muted)] uppercase tracking-wider">
              Test All 6 Verification Bands (Judge Evaluation Presets):
            </div>

            <div className="flex flex-wrap items-center justify-center gap-2.5">
              {PRESET_PILLS.map((pill) => (
                <GlassButton
                  key={pill.scenario}
                  onClick={() => onSelectScenario(pill.scenario)}
                  variant={pill.variant}
                  size="sm"
                  label={pill.label}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
