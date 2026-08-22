import { useState } from "react";
import { type ScreeningResponse, TrustBand } from "../types/contracts";
import { Link } from "react-router-dom";
import SignalForensics from "./SignalForensics";
import SpoofTimeline from "./SpoofTimeline";
import EvidencePanel from "./EvidencePanel";
import AudioInspector from "./AudioInspector";

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
      utterance.rate = 0.9;
      utterance.onend = () => setIsSpeaking(false);
      utterance.onerror = () => setIsSpeaking(false);
      setIsSpeaking(true);
      window.speechSynthesis.speak(utterance);
    }
  };

  return (
    <div className="space-y-6">
      {/* ── 1. GIANT UNAMBIGUOUS VERDICT CARD (MAIN FOCUS) ── */}
      <div
        className={`p-6 sm:p-8 rounded-xl border text-center space-y-5 transition-colors ${
          isHighRisk
            ? "bg-[var(--danger-bg)] border-[var(--danger-border)] text-[var(--text-primary)]"
            : isVerified
            ? "bg-[var(--success-bg)] border-[var(--success-border)] text-[var(--text-primary)]"
            : isUnverified
            ? "bg-[var(--bg-primary)] border-[var(--border-default)] text-[var(--text-primary)]"
            : "bg-[var(--bg-secondary)] border-[var(--border-default)] text-[var(--text-primary)]"
        }`}
      >
        {/* Giant Status Icon */}
        <div className="flex justify-center">
          <div
            className={`w-16 h-16 sm:w-20 sm:h-20 rounded-full flex items-center justify-center font-extrabold text-3xl sm:text-4xl shadow-sm border-2 ${
              isHighRisk
                ? "bg-[var(--danger)] border-[var(--danger-border)] text-white"
                : isVerified
                ? "bg-[var(--success)] border-[var(--success-border)] text-white"
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

        {/* Huge Unambiguous Headline (Max 6-8 Words) */}
        <div className="space-y-2 max-w-2xl mx-auto">
          <h1
            className={`text-2xl sm:text-3xl font-extrabold tracking-tight leading-tight ${
              isHighRisk
                ? "text-[var(--danger)]"
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
          <p className="text-base sm:text-lg text-[var(--text-secondary)] leading-relaxed font-medium">
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
          <div className="pt-2">
            <button
              onClick={handlePlayVoiceWarning}
              className="w-full max-w-md mx-auto py-3.5 px-6 rounded-lg bg-[var(--danger)] hover:opacity-90 text-white font-bold text-base shadow-sm flex items-center justify-center gap-2.5 transition-opacity cursor-pointer border border-[var(--danger-border)]"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
              </svg>
              <span>
                {isSpeaking ? "Stop Hindi Warning" : "Listen to Warning in Hindi (चेतावनी सुनिए)"}
              </span>
            </button>
            <p className="text-xs text-[var(--danger-text)] mt-2 font-medium">
              "{fusion.vernacular_warning}"
            </p>
          </div>
        )}
      </div>

      {/* ── 3. STEP-BY-STEP ACTION WIZARD (ONE CLEAR STEP AT A TIME) ── */}
      {isHighRisk && (
        <div className="sec-card p-6 sm:p-7 space-y-4">
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-3">
            <h2 className="text-base sm:text-lg font-bold text-[var(--text-primary)]">
              What to Do Right Now
            </h2>
            <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-[var(--danger-bg)] text-[var(--danger-text)] border border-[var(--danger-border)]">
              Step {currentStep} of 3
            </span>
          </div>

          {/* Wizard Step 1: Hang Up */}
          {currentStep === 1 && (
            <div className="space-y-4">
              <div className="sec-card-subtle p-4 space-y-1.5">
                <div className="text-xs font-bold text-[var(--danger)] uppercase tracking-wider">
                  Step 1 of 3:
                </div>
                <div className="text-lg sm:text-xl font-bold text-[var(--text-primary)]">
                  Hang up the call immediately.
                </div>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
                  Do not argue, do not send any money, and do not enter any UPI PIN. Simply disconnect the call.
                </p>
              </div>

              <button
                onClick={() => setCurrentStep(2)}
                className="w-full py-3.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-text)] font-bold text-sm transition-colors shadow-sm cursor-pointer"
              >
                I Have Hung Up → Next Step
              </button>
            </div>
          )}

          {/* Wizard Step 2: Call Back on Saved Number */}
          {currentStep === 2 && (
            <div className="space-y-4">
              <div className="sec-card-subtle p-4 space-y-1.5">
                <div className="text-xs font-bold text-[var(--accent)] uppercase tracking-wider">
                  Step 2 of 3:
                </div>
                <div className="text-lg sm:text-xl font-bold text-[var(--text-primary)]">
                  Call {speaker.matched_person_name || "your family member"} on your regular phone.
                </div>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
                  Dial their saved number directly from your contacts list. You will find they are safe and this call was a scam.
                </p>
              </div>

              <div className="flex gap-2.5">
                <button
                  onClick={() => setCurrentStep(1)}
                  className="w-1/3 py-2.5 rounded-lg bg-[var(--bg-secondary)] hover:bg-[var(--bg-hover)] text-[var(--text-primary)] border border-[var(--border-default)] font-semibold text-xs cursor-pointer"
                >
                  ← Back
                </button>
                <button
                  onClick={() => setCurrentStep(3)}
                  className="w-2/3 py-2.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[var(--accent-text)] font-bold text-sm cursor-pointer"
                >
                  Next: Challenge Question →
                </button>
              </div>
            </div>
          )}

          {/* Wizard Step 3: Ask Challenge Question */}
          {currentStep === 3 && (
            <div className="space-y-4">
              <div className="p-4 rounded-lg bg-[var(--warning-bg)] border border-[var(--warning-border)] space-y-1.5">
                <div className="text-xs font-bold text-[var(--warning-text)] uppercase tracking-wider">
                  Step 3 of 3 (If They Call Again):
                </div>
                <div className="text-base font-bold text-[var(--warning-text)]">
                  Ask them this secret question:
                </div>
                <div className="text-lg font-extrabold text-[var(--text-primary)] p-3 rounded bg-[var(--bg-primary)] border border-[var(--warning-border)]">
                  "{fusion.challenge_question?.question_text || "What was our first pet's name?"}"
                </div>
                <p className="text-xs text-[var(--warning-text)] leading-relaxed">
                  Your real family member will know the answer instantly. A scammer or AI system will not know.
                </p>
              </div>

              <div className="flex gap-2.5">
                <button
                  onClick={() => setCurrentStep(2)}
                  className="w-1/3 py-2.5 rounded-lg bg-[var(--bg-secondary)] hover:bg-[var(--bg-hover)] text-[var(--text-primary)] border border-[var(--border-default)] font-semibold text-xs cursor-pointer"
                >
                  ← Back
                </button>
                <Link
                  to="/report"
                  className="w-2/3 py-2.5 rounded-lg bg-[var(--danger)] hover:opacity-90 text-white font-bold text-sm flex items-center justify-center no-underline cursor-pointer"
                >
                  File Complaint on 1930 Portal →
                </Link>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── 4. CHECK ANOTHER CALL BUTTON ── */}
      <div className="text-center pt-1">
        <button
          onClick={onReset}
          className="py-2.5 px-6 rounded-lg bg-[var(--bg-secondary)] hover:bg-[var(--bg-hover)] text-[var(--text-primary)] font-semibold text-sm border border-[var(--border-default)] transition-colors cursor-pointer"
        >
          ← Check Another Call
        </button>
      </div>

      {/* ── 5. OPTIONAL: SHOW TECHNICAL FORENSICS TOGGLE ── */}
      <div className="pt-3 border-t border-[var(--border-subtle)]">
        <div className="text-center">
          <button
            onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
            className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] font-mono underline cursor-pointer bg-transparent border-none py-1.5 px-3"
          >
            {showTechnicalDetails
              ? "▲ Hide Technical & Forensic Data"
              : "▼ Show Technical & Forensic Details (For Family Guardian / Cyber Officers)"}
          </button>
        </div>

        {showTechnicalDetails && (
          <div className="mt-4 p-5 rounded-lg sec-card space-y-5">
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
