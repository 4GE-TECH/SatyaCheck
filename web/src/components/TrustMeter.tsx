/**
 * TrustMeter — The signature radial SVG gauge.
 *
 * A 270-degree arc that fills from 0 to `score`, with the trust score
 * displayed as a large number at centre and the band label below.
 * Outer glow pulses in the band colour. Respects prefers-reduced-motion.
 */

import { useEffect, useRef, useState } from "react";
import { TrustBand, BAND_CONFIG } from "../types/contracts";

interface TrustMeterProps {
  score: number;         // 0–100
  band: TrustBand;
  matchedName?: string | null;
  className?: string;
}

/* ── Arc geometry ───────────────────────────────────────────── */

const SIZE = 280;
const STROKE_WIDTH = 14;
const RADIUS = (SIZE - STROKE_WIDTH) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const ARC_SPAN = 0.75; // 270° of the circle
const ARC_LENGTH = CIRCUMFERENCE * ARC_SPAN;

// Rotation so the arc starts at 7-o'clock (225°)
const ROTATE = 135;

export default function TrustMeter({
  score,
  band,
  matchedName,
  className = "",
}: TrustMeterProps) {
  const config = BAND_CONFIG[band];
  const fillRef = useRef<SVGCircleElement>(null);
  const [displayed, setDisplayed] = useState(0);

  /* Animate the score counter and arc fill */
  useEffect(() => {
    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    if (prefersReducedMotion) {
      setDisplayed(score);
      if (fillRef.current) {
        const offset = ARC_LENGTH * (1 - score / 100);
        fillRef.current.style.strokeDashoffset = `${offset}`;
      }
      return;
    }

    // Animate counter
    const duration = 800;
    const start = performance.now();
    let raf: number;

    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out cubic
      const ease = 1 - Math.pow(1 - progress, 3);
      const current = Math.round(ease * score);
      setDisplayed(current);

      if (fillRef.current) {
        const offset = ARC_LENGTH * (1 - (ease * score) / 100);
        fillRef.current.style.strokeDashoffset = `${offset}`;
      }

      if (progress < 1) {
        raf = requestAnimationFrame(tick);
      }
    }

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [score]);

  return (
    <div
      className={`flex flex-col items-center ${className}`}
      role="meter"
      aria-valuenow={score}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Trust score ${score} out of 100, ${config.label}`}
    >
      <div className="relative" style={{ width: SIZE, height: SIZE }}>
        {/* Glow background */}
        <div
          className="absolute inset-0 rounded-full"
          style={{
            background: `radial-gradient(circle, ${config.glowColor} 0%, transparent 70%)`,
            animation: "meter-pulse 3s ease-in-out infinite",
          }}
        />

        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="relative"
        >
          {/* Background track */}
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="var(--color-border-subtle)"
            strokeWidth={STROKE_WIDTH}
            strokeDasharray={`${ARC_LENGTH} ${CIRCUMFERENCE - ARC_LENGTH}`}
            strokeLinecap="round"
            transform={`rotate(${ROTATE} ${SIZE / 2} ${SIZE / 2})`}
          />

          {/* Filled arc */}
          <circle
            ref={fillRef}
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke={config.color}
            strokeWidth={STROKE_WIDTH}
            strokeDasharray={`${ARC_LENGTH} ${CIRCUMFERENCE - ARC_LENGTH}`}
            strokeDashoffset={ARC_LENGTH}
            strokeLinecap="round"
            transform={`rotate(${ROTATE} ${SIZE / 2} ${SIZE / 2})`}
            style={{
              filter: `drop-shadow(0 0 8px ${config.glowColor})`,
              transition: "stroke 0.4s ease",
            }}
          />
        </svg>

        {/* Centre text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="font-bold leading-none tracking-tight animate-score-count"
            style={{
              fontSize: "72px",
              color: config.textColor,
            }}
          >
            {displayed}
          </span>
          <span
            className="mt-1 text-sm font-medium uppercase tracking-widest"
            style={{ color: config.textColor, letterSpacing: "0.15em" }}
          >
            {config.label}
          </span>
          {matchedName && (
            <span
              className="mt-2 text-xs px-2.5 py-0.5 rounded-full"
              style={{
                color: config.textColor,
                backgroundColor: config.bgColor,
              }}
            >
              {matchedName}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
