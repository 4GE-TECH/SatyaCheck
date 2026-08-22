import { useRef, useState, useEffect } from "react";
import type { MockScenario } from "../api/mock";

interface StreamControlHUDProps {
  activeScenario: MockScenario | null;
  onSelectScenario: (scenario: MockScenario) => void;
  onUploadFile: (file: File) => void;
  isLoading: boolean;
}

const PRESETS: Array<{
  id: MockScenario;
  code: string;
  label: string;
  tag: string;
  tagColor: string;
  desc: string;
}> = [
  {
    id: "red",
    code: "CASE-01",
    label: "Cloned Family Extortion",
    tag: "HIGH THREAT",
    tagColor: "border-rose-500/50 bg-rose-950/40 text-rose-300",
    desc: "AI clone claiming police arrest, demanding 50k UPI",
  },
  {
    id: "green",
    code: "CASE-02",
    label: "Authentic Family Call",
    tag: "GENUINE",
    tagColor: "border-emerald-500/50 bg-emerald-950/40 text-emerald-300",
    desc: "Organic voice match from Rahul (Office check-in)",
  },
  {
    id: "unverified",
    code: "CASE-03",
    label: "Automated Banking Service",
    tag: "NEUTRAL IVR",
    tagColor: "border-zinc-500/50 bg-zinc-900 text-zinc-300",
    desc: "Legitimate automated statement notification",
  },
  {
    id: "insufficient",
    code: "CASE-04",
    label: "Telephony Static Burst",
    tag: "LOW DURATION",
    tagColor: "border-zinc-700 bg-zinc-900 text-zinc-400",
    desc: "0.6s sample safely declined (min 1.5s required)",
  },
];

export default function StreamControlHUD({
  activeScenario,
  onSelectScenario,
  onUploadFile,
  isLoading,
}: StreamControlHUDProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isListening, setIsListening] = useState(false);
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    let timer: number;
    if (isListening) {
      setSeconds(0);
      timer = window.setInterval(() => {
        setSeconds((prev) => {
          if (prev >= 4) {
            setIsListening(false);
            onSelectScenario("red");
            return 0;
          }
          return prev + 1;
        });
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [isListening, onSelectScenario]);

  return (
    <div className="hud-panel p-4 sm:p-5 mb-6">
      {/* Header & Main Ingest Triggers */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></span>
            <span className="font-mono text-[11px] uppercase tracking-widest text-zinc-400">
              AUDIO INGESTION & SPEAKERPHONE CAPTURE
            </span>
          </div>
          <p className="text-xs text-zinc-400 font-mono">
            Analyze live speakerphone audio, WhatsApp voice notes, or recorded calls for deepfake synthesis.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => setIsListening(!isListening)}
            disabled={isLoading}
            className={`px-4 py-2 rounded font-mono text-xs font-semibold tracking-wider transition-all cursor-pointer border flex items-center gap-2 ${
              isListening
                ? "bg-rose-950 border-rose-500 text-rose-200 animate-pulse"
                : "bg-white text-black border-white hover:bg-zinc-200"
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isListening ? "bg-rose-400" : "bg-black"
              }`}
            />
            <span>{isListening ? `CAPTURING ON SPEAKERPHONE [${seconds}s]...` : "START SPEAKERPHONE CAPTURE"}</span>
          </button>

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className="px-4 py-2 rounded font-mono text-xs font-semibold tracking-wider bg-[#121212] hover:bg-[#1C1C1C] text-white border border-white/20 transition-all cursor-pointer flex items-center gap-2"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <span>UPLOAD AUDIO PROBE</span>
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

      {/* Futuristic Case Presets */}
      <div className="pt-3">
        <div className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider mb-2">
          SELECT REPLAY PROBE CASE:
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
          {PRESETS.map((p) => {
            const isSelected = activeScenario === p.id;

            return (
              <button
                key={p.id}
                onClick={() => onSelectScenario(p.id)}
                disabled={isLoading}
                className={`p-3 rounded text-left transition-all font-mono cursor-pointer border ${
                  isSelected
                    ? "bg-[#161616] border-white/50 ring-1 ring-white/30 shadow-[0_0_15px_rgba(255,255,255,0.05)]"
                    : "bg-[#0A0A0A] border-white/10 hover:border-white/25 hover:bg-[#121212]"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-zinc-400 font-bold">{p.code}</span>
                  <span className={`text-[9px] px-1.5 py-0.2 rounded font-bold uppercase border ${p.tagColor}`}>
                    {p.tag}
                  </span>
                </div>
                <div className="text-xs font-semibold text-white truncate font-sans">
                  {p.label}
                </div>
                <div className="text-[11px] text-zinc-400 truncate mt-0.5 font-sans">
                  {p.desc}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
