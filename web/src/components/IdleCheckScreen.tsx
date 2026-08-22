import { useRef, useState, useEffect } from "react";
import type { MockScenario } from "../api/mock";
import { PearlButton } from "@/components/ui/pearl-button";
import { BackgroundCircles } from "@/components/ui/background-circles";

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
              <span
                className={`w-2 h-2 rounded-full mr-1.5 ${
                  isListening ? "bg-red-400 animate-ping" : "bg-cyan-400"
                }`}
              />
            }
          />

          <PearlButton
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            variant="secondary"
            size="md"
            className="w-full font-mono"
            label="Upload WhatsApp Audio or Recording"
            icon={<span className="mr-1">📁</span>}
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
