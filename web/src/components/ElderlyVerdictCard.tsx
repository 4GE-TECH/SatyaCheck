import { useState } from "react";
import { type ScreeningResponse, TrustBand } from "../types/contracts";
import { Link } from "react-router-dom";
import SignalForensics from "./SignalForensics";
import SpoofTimeline from "./SpoofTimeline";
import EvidencePanel from "./EvidencePanel";
import AudioInspector from "./AudioInspector";
import { PearlButton } from "@/components/ui/pearl-button";

interface ElderlyVerdictCardProps {
  data: ScreeningResponse;
  onReset: () => void;
}

export default function ElderlyVerdictCard({ data, onReset }: ElderlyVerdictCardProps) {
  const { fusion, speaker } = data;
  const isHighRisk = fusion.band === TrustBand.HIGH_RISK;
  const isVerified = fusion.band === TrustBand.VERIFIED;
  const isUnverified = fusion.band === TrustBand.UNVERIFIED;
  const isInsufficient = fusion.band === TrustBand.INSUFFICIENT;

  const [isSpeaking, setIsSpeaking] = useState(false);
  const [currentStep, setCurrentStep] = useState(1);
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);

  const handlePlayVoiceWarning = () => {
    if (!fusion.vernacular_warning) return;
    if ("speechSynthesis" in window) {
      if (isSpeaking) {
        window.speechSynthesis.cancel();
        setIsSpeaking(false);
        return;
      }
      const utterance = new SpeechSynthesisUtterance(fusion.vernacular_warning);
      utterance.lang = "hi-IN";
      utterance.rate = 0.88;
      utterance.onend = () => setIsSpeaking(false);
      utterance.onerror = () => setIsSpeaking(false);
      setIsSpeaking(true);
      window.speechSynthesis.speak(utterance);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* ── 1. GIANT UNAMBIGUOUS VERDICT CARD (MAIN FOCUS) ── */}
      <div
        className={`relative overflow-hidden p-6 sm:p-10 rounded-2xl border text-center space-y-6 transition-all shadow-2xl ${
          isHighRisk
            ? "bg-[var(--danger-bg)] border-[var(--danger-border)] shadow-[0_0_50px_-12px_rgba(255,59,48,0.25)]"
            : isVerified
            ? "bg-[var(--success-bg)] border-[var(--success-border)] shadow-[0_0_50px_-12px_rgba(48,209,88,0.2)]"
            : isUnverified
            ? "bg-[var(--bg-primary)] border-[var(--border-default)]"
            : "bg-[var(--bg-secondary)] border-[var(--border-default)]"
        }`}
      >
        {/* Subtle Top Shine Highlight */}
        <div className="absolute top-0 left-1/4 right-1/4 h-[1px] bg-gradient-to-r from-transparent via-white/20 to-transparent pointer-events-none" />

        {/* Giant Status Icon with Pulsing Halo */}
        <div className="flex justify-center">
          <div className="relative">
            {isHighRisk && (
              <div className="absolute inset-0 rounded-full bg-red-600 blur-xl opacity-40 animate-pulse pointer-events-none" />
            )}
            <div
              className={`relative w-20 h-20 sm:w-24 sm:h-24 rounded-full flex items-center justify-center font-black text-4xl sm:text-5xl shadow-2xl border-2 ${
                isHighRisk
                  ? "bg-gradient-to-b from-red-500 to-red-700 border-red-300 text-white"
                  : isVerified
                  ? "bg-gradient-to-b from-emerald-500 to-emerald-700 border-emerald-300 text-white"
                  : isUnverified
                  ? "bg-[var(--bg-surface)] border-[var(--border-default)] text-[var(--text-primary)]"
                  : "bg-[var(--bg-surface)] border-[var(--border-default)] text-[var(--text-muted)]"
              }`}
            >
              {isHighRisk && "✕"}
              {isVerified && "✓"}
              {isUnverified && "ℹ"}
              {isInsufficient && "!"}
            </div>
          </div>
        </div>

        {/* Huge Unambiguous Headline (Max 6-8 Words) */}
        <div className="space-y-3 max-w-3xl mx-auto">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-black/40 border border-white/10 text-xs font-mono font-bold tracking-wider uppercase text-[var(--text-secondary)]">
            <span>REAL-TIME THREAT VERDICT</span>
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--danger)] animate-ping" />
          </div>

          <h1
            className={`text-2xl sm:text-4xl font-black tracking-tight leading-tight uppercase font-mono ${
              isHighRisk
                ? "text-[var(--danger)] drop-shadow-sm"
                : isVerified
                ? "text-[var(--success)]"
                : isUnverified
                ? "text-[var(--text-primary)]"
                : "text-[var(--text-muted)]"
            }`}
          >
            {isHighRisk && "FAKE VOICE DETECTED — DO NOT SEND MONEY"}
            {isVerified && "SAFE CALL — VERIFIED AS RAHUL"}
            {isUnverified && "AUTOMATED CALL — NO SCAM DETECTED"}
            {isInsufficient && "COULD NOT VERIFY — PLEASE TRY AGAIN"}
          </h1>

          {/* Plain Single-Sentence Explanation (Zero Jargon) */}
          <p className="text-base sm:text-xl text-[var(--text-secondary)] leading-relaxed font-medium max-w-2xl mx-auto">
            {isHighRisk &&
              "The voice sounds like Rahul, but our AI detected it was artificially created to trick you into transferring money."}
            {isVerified &&
              "The voice matches your enrolled family voiceprint for Rahul. It is safe to talk."}
            {isUnverified &&
              "This caller is an automated service (like a bank IVR). No scam or emergency demands were detected."}
            {isInsufficient &&
              "The audio was too short to check reliably. Ask the caller to speak for a few seconds and try again."}
          </p>
        </div>

        {/* ── 2. VOICE-FIRST PRIMARY AUDIO WARNING BUTTON ── */}
        {fusion.vernacular_warning && (
          <div className="pt-2 max-w-md mx-auto">
            <PearlButton
              onClick={handlePlayVoiceWarning}
              variant="danger"
              size="lg"
              className="w-full flex items-center justify-center font-mono shadow-2xl"
              label={isSpeaking ? "Stop Hindi Warning" : "Listen to Warning in Hindi (चेतावनी सुनिए)"}
              icon={
                isSpeaking ? (
                  <div className="flex items-center gap-1 mr-2">
                    <span className="w-1.5 h-4 bg-white rounded-full animate-bounce" />
                    <span className="w-1.5 h-6 bg-white rounded-full animate-bounce [animation-delay:0.15s]" />
                    <span className="w-1.5 h-3 bg-white rounded-full animate-bounce [animation-delay:0.3s]" />
                  </div>
                ) : (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="mr-2">
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                    <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
                  </svg>
                )
              }
            />
            <p className="text-xs text-[var(--danger-text)] mt-2.5 font-medium italic">
              "{fusion.vernacular_warning}"
            </p>
          </div>
        )}
      </div>

      {/* ── 3. STEP-BY-STEP ACTION WIZARD (ONE CLEAR STEP AT A TIME) ── */}
      {isHighRisk && (
        <div className="sec-card p-6 sm:p-8 space-y-5">
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-4">
            <div>
              <h2 className="text-lg sm:text-xl font-black text-[var(--text-primary)] font-mono uppercase tracking-tight">
                Recommended Actions
              </h2>
              <p className="text-xs text-[var(--text-muted)] font-sans">
                Follow these simple steps in order to safeguard yourself.
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              {[1, 2, 3].map((step) => (
                <div
                  key={step}
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-mono font-bold transition-all ${
                    currentStep === step
                      ? "bg-[var(--danger)] text-white ring-2 ring-red-500/40"
                      : currentStep > step
                      ? "bg-[var(--success)] text-white"
                      : "bg-[var(--bg-secondary)] text-[var(--text-muted)] border border-[var(--border-default)]"
                  }`}
                >
                  {currentStep > step ? "✓" : step}
                </div>
              ))}
            </div>
          </div>

          {/* Wizard Step 1: Hang Up */}
          {currentStep === 1 && (
            <div className="space-y-4">
              <div className="sec-card-subtle p-5 space-y-2 border border-red-500/20 bg-red-950/20">
                <div className="text-xs font-bold text-[var(--danger)] uppercase font-mono tracking-wider">
                  Step 1 of 3:
                </div>
                <div className="text-xl sm:text-2xl font-bold text-[var(--text-primary)]">
                  Hang up the call immediately.
                </div>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
                  Do not argue, do not send any money, and do not enter any UPI PIN. Simply disconnect the call.
                </p>
              </div>

              <PearlButton
                onClick={() => setCurrentStep(2)}
                variant="default"
                size="lg"
                className="w-full font-mono font-bold"
                label="I Have Hung Up → Next Step"
              />
            </div>
          )}

          {/* Wizard Step 2: Call Back on Saved Number */}
          {currentStep === 2 && (
            <div className="space-y-4">
              <div className="sec-card-subtle p-5 space-y-2 border border-sky-500/20 bg-sky-950/20">
                <div className="text-xs font-bold text-[var(--accent)] uppercase font-mono tracking-wider">
                  Step 2 of 3:
                </div>
                <div className="text-xl sm:text-2xl font-bold text-[var(--text-primary)]">
                  Call {speaker.matched_person_name || "your family member"} on your regular phone.
                </div>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
                  Dial their saved number directly from your contacts list. You will find they are safe and this call was an AI scam.
                </p>
              </div>

              <div className="flex gap-3">
                <PearlButton
                  onClick={() => setCurrentStep(1)}
                  variant="secondary"
                  size="md"
                  className="w-1/3 font-mono font-semibold"
                  label="← Back"
                />
                <PearlButton
                  onClick={() => setCurrentStep(3)}
                  variant="default"
                  size="md"
                  className="w-2/3 font-mono font-bold"
                  label="Next: Challenge Question →"
                />
              </div>
            </div>
          )}

          {/* Wizard Step 3: Ask Challenge Question */}
          {currentStep === 3 && (
            <div className="space-y-4">
              <div className="p-5 rounded-xl bg-[var(--warning-bg)] border border-[var(--warning-border)] space-y-2">
                <div className="text-xs font-bold text-[var(--warning-text)] uppercase font-mono tracking-wider">
                  Step 3 of 3 (If They Call Again):
                </div>
                <div className="text-base font-bold text-[var(--warning-text)]">
                  Ask them this secret question:
                </div>
                <div className="text-xl font-extrabold text-[var(--text-primary)] p-4 rounded-lg bg-[var(--bg-primary)] border border-[var(--warning-border)] font-mono">
                  "{fusion.challenge_question?.question_text || "What was our first pet's name?"}"
                </div>
                <p className="text-xs text-[var(--warning-text)] leading-relaxed">
                  Your real family member will know the answer instantly. A scammer or AI system will not know.
                </p>
              </div>

              <div className="flex gap-3">
                <PearlButton
                  onClick={() => setCurrentStep(2)}
                  variant="secondary"
                  size="md"
                  className="w-1/3 font-mono font-semibold"
                  label="← Back"
                />
                <Link to="/report" className="w-2/3 no-underline">
                  <PearlButton
                    variant="danger"
                    size="md"
                    className="w-full font-mono font-bold"
                    label="File Complaint on 1930 Portal →"
                  />
                </Link>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── 4. CHECK ANOTHER CALL BUTTON ── */}
      <div className="text-center pt-2">
        <PearlButton
          onClick={onReset}
          variant="secondary"
          size="md"
          className="font-mono font-semibold px-8"
          label="← Check Another Call"
        />
      </div>

      {/* ── 5. OPTIONAL: SHOW TECHNICAL FORENSICS TOGGLE ── */}
      <div className="pt-4 border-t border-[var(--border-subtle)]">
        <div className="text-center">
          <button
            onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
            className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] font-mono underline cursor-pointer bg-transparent border-none py-2 px-4"
          >
            {showTechnicalDetails
              ? "▲ Hide Technical & Forensic Data"
              : "▼ Show Technical & Forensic Details (For Family Guardian / Cyber Officers)"}
          </button>
        </div>

        {showTechnicalDetails && (
          <div className="mt-4 p-6 rounded-2xl sec-card space-y-6 border border-white/10">
            <AudioInspector data={data} />
            <SignalForensics data={data} />
            <SpoofTimeline timeline={data.spoof.timeline} />
            <EvidencePanel
              reasonCodes={data.fusion.reason_codes}
              playbooks={data.script.playbooks}
            />
          </div>
        )}
      </div>
    </div>
  );
}
