import { useState, useEffect } from "react";
import type { ScreeningResponse } from "../types/contracts";

interface AudioInspectorProps {
  data: ScreeningResponse;
}

export default function AudioInspector({ data }: AudioInspectorProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const totalDuration = Math.max(data.quality.speech_duration_s, 6.0);

  useEffect(() => {
    let interval: number;
    if (isPlaying) {
      interval = window.setInterval(() => {
        setCurrentTime((prev) => {
          if (prev >= totalDuration) {
            setIsPlaying(false);
            return 0;
          }
          return prev + 0.1;
        });
      }, 100);
    }
    return () => clearInterval(interval);
  }, [isPlaying, totalDuration]);

  return (
    <div className="hud-panel p-4">
      <div className="flex items-center justify-between mb-3 font-mono">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-white"></span>
          <h3 className="text-xs font-bold uppercase tracking-wider text-white">
            AUDIO PROBE WAVEFORM & TIME-SERIES SCRUBBER
          </h3>
        </div>

        <div className="text-[11px] text-zinc-400">
          <span>CHANNEL: 16 kHz Mono (SPEAKERPHONE)</span>
        </div>
      </div>

      {/* Futuristic Audio Waveform Player */}
      <div className="p-3 rounded bg-[#050505] border border-white/10">
        <div className="flex items-center gap-4 mb-2">
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className="w-8 h-8 rounded bg-white text-black flex items-center justify-center font-bold text-xs font-mono transition-all hover:bg-zinc-200 cursor-pointer shrink-0"
            title={isPlaying ? "Pause Probe" : "Play Probe"}
          >
            {isPlaying ? "❚❚" : "▶"}
          </button>

          <div className="flex-1">
            <div className="flex items-center justify-between text-[11px] font-mono text-zinc-400 mb-1">
              <span>AUDIO PROBE PLAYBACK</span>
              <span className="text-white font-bold">
                {currentTime.toFixed(1)}s / {totalDuration.toFixed(1)}s
              </span>
            </div>

            {/* Interactive Progress Bar with Waveform */}
            <div
              className="h-8 rounded bg-[#000000] border border-white/10 relative overflow-hidden flex items-center px-1 cursor-pointer select-none"
              onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const pct = clickX / rect.width;
                setCurrentTime(pct * totalDuration);
              }}
            >
              {/* Playback progress background */}
              <div
                className="absolute top-0 bottom-0 left-0 bg-white/10 border-r border-white"
                style={{ width: `${(currentTime / totalDuration) * 100}%` }}
              />

              {/* Waveform Bars */}
              <div className="w-full flex items-center justify-between gap-[2px] h-5 z-10 px-1">
                {Array.from({ length: 48 }).map((_, i) => {
                  const progressPct = i / 48;
                  const isCurrent = progressPct <= currentTime / totalDuration;
                  const pseudoHeight = 30 + Math.sin(i * 0.7) * 25 + Math.cos(i * 1.3) * 35;

                  return (
                    <div
                      key={i}
                      className="flex-1 rounded-none transition-all"
                      style={{
                        height: `${Math.max(15, Math.min(95, pseudoHeight))}%`,
                        backgroundColor: isCurrent ? "#FFFFFF" : "rgba(255, 255, 255, 0.2)",
                      }}
                    />
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Telephony Specs */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-white/10 text-[10px] font-mono text-zinc-400">
          <div>
            <span>CODEC: </span>
            <span className="text-white font-bold">PCM 16-bit / Opus</span>
          </div>
          <div>
            <span>ACTIVE SPEECH: </span>
            <span className="text-white font-bold">{data.quality.speech_duration_s.toFixed(2)}s</span>
          </div>
          <div>
            <span>SNR ESTIMATE: </span>
            <span className="text-white font-bold">+{data.quality.snr_db.toFixed(1)} dB</span>
          </div>
          <div>
            <span>QUALITY GATE: </span>
            <span className={data.quality.passed ? "text-emerald-400 font-bold" : "text-amber-400 font-bold"}>
              {data.quality.passed ? "PASSED" : "FAILED"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
