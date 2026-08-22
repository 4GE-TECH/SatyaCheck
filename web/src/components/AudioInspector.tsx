import { useState, useEffect } from "react";
import type { ScreeningResponse } from "../types/contracts";
import { PearlButton } from "@/components/ui/pearl-button";

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
    <div className="sec-card-subtle p-4 font-mono text-xs">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[var(--accent)]"></span>
          <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--text-primary)]">
            AUDIO PROBE WAVEFORM & TIME-SERIES SCRUBBER
          </h3>
        </div>

        <div className="text-[11px] text-[var(--text-muted)]">
          <span>CHANNEL: 16 kHz Mono (SPEAKERPHONE)</span>
        </div>
      </div>

      {/* Audio Waveform Player */}
      <div className="p-3 rounded bg-[var(--bg-primary)] border border-[var(--border-default)]">
        <div className="flex items-center gap-3.5 mb-3">
          <PearlButton
            onClick={() => setIsPlaying(!isPlaying)}
            variant="default"
            size="sm"
            className="!p-0 w-9 h-9 !rounded-full shrink-0 font-bold"
            title={isPlaying ? "Pause Probe" : "Play Probe"}
          >
            {isPlaying ? "❚❚" : "▶"}
          </PearlButton>

          <div className="flex-1">
            <div className="flex items-center justify-between text-[11px] text-[var(--text-muted)] mb-1">
              <span>AUDIO PROBE PLAYBACK</span>
              <span className="text-[var(--text-primary)] font-bold">
                {currentTime.toFixed(1)}s / {totalDuration.toFixed(1)}s
              </span>
            </div>

            {/* Interactive Progress Bar with Waveform */}
            <div
              className="h-8 rounded bg-[var(--bg-secondary)] border border-[var(--border-default)] relative overflow-hidden flex items-center px-1 cursor-pointer select-none"
              onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const pct = clickX / rect.width;
                setCurrentTime(pct * totalDuration);
              }}
            >
              <div
                className="absolute top-0 bottom-0 left-0 bg-[var(--accent)] opacity-20 border-r border-[var(--accent)]"
                style={{ width: `${(currentTime / totalDuration) * 100}%` }}
              />

              <div className="w-full flex items-center justify-between gap-[2px] h-5 z-10 px-1">
                {Array.from({ length: 48 }).map((_, i) => {
                  const progressPct = i / 48;
                  const isCurrent = progressPct <= currentTime / totalDuration;
                  const pseudoHeight = 30 + Math.sin(i * 0.7) * 25 + Math.cos(i * 1.3) * 35;

                  return (
                    <div
                      key={i}
                      className="flex-1 transition-all"
                      style={{
                        height: `${Math.max(15, Math.min(95, pseudoHeight))}%`,
                        backgroundColor: isCurrent ? "var(--accent)" : "var(--border-strong)",
                      }}
                    />
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Telephony Specs */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-3 border-t border-[var(--border-subtle)] text-[10px] text-[var(--text-secondary)]">
          <div>
            <div className="flex justify-between">
              <span>CODEC:</span>
              <span className="text-[var(--text-primary)] font-bold">PCM 16-bit / Opus</span>
            </div>
            <div className="text-[9px] text-[var(--text-muted)] mt-0.5">
              ⓘ Audio compression type used by caller's telephone network.
            </div>
          </div>

          <div>
            <div className="flex justify-between">
              <span>ACTIVE SPEECH:</span>
              <span className="text-[var(--text-primary)] font-bold">{data.quality.speech_duration_s.toFixed(2)}s</span>
            </div>
            <div className="text-[9px] text-[var(--text-muted)] mt-0.5">
              ⓘ Total duration of active human speech (excluding silence).
            </div>
          </div>

          <div>
            <div className="flex justify-between">
              <span>SNR ESTIMATE:</span>
              <span className="text-[var(--text-primary)] font-bold">+{data.quality.snr_db.toFixed(1)} dB</span>
            </div>
            <div className="text-[9px] text-[var(--text-muted)] mt-0.5">
              ⓘ Signal-to-Noise Ratio (higher SNR means cleaner audio for checks).
            </div>
          </div>

          <div>
            <div className="flex justify-between">
              <span>QUALITY GATE:</span>
              <span className={data.quality.passed ? "text-[var(--success-text)] font-bold" : "text-[var(--warning-text)] font-bold"}>
                {data.quality.passed ? "PASSED" : "FAILED"}
              </span>
            </div>
            <div className="text-[9px] text-[var(--text-muted)] mt-0.5">
              ⓘ Audio check verification quality gate status.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
