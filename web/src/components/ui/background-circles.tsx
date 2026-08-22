"use client";

import { motion } from "framer-motion";
import clsx from "clsx";
import { useState, useEffect } from "react";
import { Mic } from "lucide-react";

interface BackgroundCirclesProps {
  title?: string;
  description?: string;
  className?: string;
  variant?: keyof typeof COLOR_VARIANTS;
  isSpeaking?: boolean;
  audioLevel?: number;
  onMicClick?: () => void;
}

const COLOR_VARIANTS = {
  primary: {
    border: "border-cyan-500/40",
    glow: "rgba(6, 182, 212, 0.35)",
    text: "text-cyan-600 dark:text-cyan-400",
    dot: "bg-cyan-500 dark:bg-cyan-400",
  },
  quinary: {
    border: "border-red-500/40",
    glow: "rgba(239, 68, 68, 0.35)",
    text: "text-red-600 dark:text-red-400",
    dot: "bg-red-500 dark:bg-red-400",
  },
} as const;

const AnimatedGrid = () => (
  <motion.div
    className="absolute inset-0 [mask-image:radial-gradient(ellipse_at_center,transparent_20%,black)] pointer-events-none"
    animate={{
      backgroundPosition: ["0% 0%", "100% 100%"],
    }}
    transition={{
      duration: 40,
      repeat: Number.POSITIVE_INFINITY,
      ease: "linear",
    }}
  >
    <div className="h-full w-full [background-image:repeating-linear-gradient(100deg,#64748B_0%,#64748B_1px,transparent_1px,transparent_4%)] opacity-10" />
  </motion.div>
);

export function BackgroundCircles({
  title = "Check If a Call Is Real",
  description = "Received an unexpected call asking for money? Put the phone on speakerphone or upload an audio note to verify against deepfake AI voice cloning.",
  className,
  variant = "primary",
  isSpeaking = false,
  audioLevel,
  onMicClick,
}: BackgroundCirclesProps) {
  const [reducedMotion, setReducedMotion] = useState(false);
  const [simulatedLevel, setSimulatedLevel] = useState(0.4);

  useEffect(() => {
    if (typeof window !== "undefined") {
      setReducedMotion(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    }
  }, []);

  const activeAudioLevel = audioLevel !== undefined ? audioLevel : simulatedLevel;
  const variantStyles = COLOR_VARIANTS[variant] || COLOR_VARIANTS.primary;

  useEffect(() => {
    if (!isSpeaking) return;
    const interval = setInterval(() => {
      setSimulatedLevel(0.35 + Math.random() * 0.45);
    }, 200);
    return () => clearInterval(interval);
  }, [isSpeaking]);

  const scaleMultiplier = isSpeaking ? 1 + (activeAudioLevel || 0.4) * 0.12 : 1;

  return (
    <div
      className={clsx(
        "relative flex flex-col items-center justify-center overflow-hidden py-8 px-4 select-none w-full",
        className
      )}
      aria-label="SatyaCheck voice analysis"
    >
      <AnimatedGrid />

      {/* Atmospheric Background Ambient Radial Glow */}
      <div className="absolute inset-0 [mask-image:radial-gradient(90%_60%_at_50%_50%,#000_40%,transparent)] pointer-events-none">
        <div
          className="absolute inset-0 transition-opacity duration-700 blur-[120px]"
          style={{
            background: `radial-gradient(ellipse at center, ${variantStyles.glow}, transparent 70%)`,
            opacity: isSpeaking ? 0.6 : 0.2,
          }}
        />
      </div>

      {/* ── CENTRAL MICROPHONE & EXPANDING AUDIO WAVES ── */}
      <div className="relative flex items-center justify-center my-4 h-52 w-52 sm:h-60 sm:w-60">
        {/* 4 Expanding Circular Audio Waves (Active when isSpeaking) */}
        {!reducedMotion &&
          isSpeaking &&
          [0, 1, 2, 3].map((index) => (
            <motion.div
              key={index}
              className={clsx(
                "absolute rounded-full border pointer-events-none",
                variantStyles.border
              )}
              initial={{ scale: 0.9, opacity: 0.6 }}
              animate={{
                scale: [0.95, 1.8 + index * 0.4 + (activeAudioLevel || 0.4) * 0.3],
                opacity: [0.7, 0.3, 0],
              }}
              transition={{
                duration: 2.4,
                repeat: Number.POSITIVE_INFINITY,
                delay: index * 0.55,
                ease: "easeOut",
              }}
              style={{
                width: "100%",
                height: "100%",
              }}
            />
          ))}

        {/* Soft Radial Ambient Glow behind the Microphone */}
        <motion.div
          className="absolute rounded-full pointer-events-none"
          animate={{
            scale: isSpeaking ? [1, 1.25, 1] : [1, 1.05, 1],
            opacity: isSpeaking ? [0.6, 0.9, 0.6] : [0.25, 0.35, 0.25],
          }}
          transition={{
            duration: isSpeaking ? 1.2 : 3,
            repeat: Number.POSITIVE_INFINITY,
            ease: "easeInOut",
          }}
          style={{
            width: "160px",
            height: "160px",
            background: `radial-gradient(circle, ${variantStyles.glow} 0%, transparent 70%)`,
            filter: "blur(24px)",
          }}
        />

        {/* Main Microphone Enclosure Button */}
        <motion.button
          onClick={onMicClick}
          type="button"
          aria-label={isSpeaking ? "Analyzing voice on speakerphone" : "Click to start voice analysis"}
          className={clsx(
            "relative z-20 flex items-center justify-center rounded-3xl transition-all cursor-pointer",
            "w-28 h-28 sm:w-32 sm:h-32 shadow-2xl border",
            "bg-[var(--bg-secondary)] text-[var(--text-primary)] border-[var(--border-default)] hover:border-[var(--accent)]",
            isSpeaking && "border-cyan-400 shadow-[0_0_40px_-5px_rgba(6,182,212,0.6)]"
          )}
          animate={
            reducedMotion
              ? {}
              : {
                  scale: scaleMultiplier,
                }
          }
          transition={{
            duration: 0.2,
            ease: "easeInOut",
          }}
        >
          {/* Subtle Top Glass Rim */}
          <div className="absolute top-0 left-1/4 right-1/4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent pointer-events-none" />

          <Mic
            className={clsx(
              "w-12 h-12 sm:w-16 sm:h-16 transition-colors drop-shadow-md",
              isSpeaking
                ? variantStyles.text
                : "text-[var(--text-primary)]"
            )}
            strokeWidth={1.75}
          />
        </motion.button>
      </div>

      {/* ── REAL-TIME STATUS INDICATOR (Below Microphone) ── */}
      <motion.div
        className="relative z-10 flex flex-col items-center gap-1.5 text-center mt-2 mb-5"
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[var(--bg-secondary)] border border-[var(--border-default)] text-xs font-mono font-bold tracking-wider uppercase shadow-sm">
          <span
            className={clsx(
              "w-2 h-2 rounded-full",
              variantStyles.dot,
              isSpeaking && "animate-ping"
            )}
          />
          <span className={clsx(isSpeaking ? variantStyles.text : "text-[var(--text-primary)]")}>
            {isSpeaking ? "LISTENING & ANALYZING" : "READY"}
          </span>
        </div>

        <span className="text-xs font-mono text-[var(--text-muted)] font-medium">
          {isSpeaking ? "Analyzing speech in real time..." : "Waiting for caller voice input..."}
        </span>
      </motion.div>

      {/* ── HERO TITLE & DESCRIPTION (Theme-Aware Contrast) ── */}
      <motion.div
        className="relative z-10 text-center max-w-2xl mx-auto space-y-3"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
      >
        <h1 className="text-3xl sm:text-5xl font-black tracking-tight font-mono text-[var(--text-primary)] leading-tight">
          {title}
        </h1>

        <motion.p
          className="text-base sm:text-lg text-[var(--text-secondary)] font-sans leading-relaxed font-normal"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
        >
          {description}
        </motion.p>
      </motion.div>
    </div>
  );
}

export default BackgroundCircles;
