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
  const { fusion, speaker, script } = data;
  const isHighRisk = fusion.band === TrustBand.HIGH_RISK;
  const isSuspicious = fusion.band === TrustBand.SUSPICIOUS;
  const isCaution = fusion.band === TrustBand.CAUTION;
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

  const getMatchedName = () => {
    return speaker.matched_person_name || "Rahul";
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* ── 1. GIANT UNAMBIGUOUS VERDICT CARD (MAIN FOCUS) ── */}
      <div
        className={`relative overflow-hidden p-6 sm:p-10 rounded-2xl border text-center space-y-6 transition-all shadow-2xl ${
          isHighRisk || isSuspicious
            ? "bg-[var(--danger-bg)] border-[var(--danger-border)] shadow-[0_0_50px_-12px_rgba(255,59,48,0.25)]"
            : isCaution
            ? "bg-[var(--warning-bg)] border-[var(--warning-border)] shadow-[0_0_50px_-12px_rgba(255,159,10,0.2)]"
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
            {(isHighRisk || isSuspicious) && (
              <div className="absolute inset-0 rounded-full bg-red-600 blur-xl opacity-40 animate-pulse pointer-events-none" />
            )}
            {isCaution && (
              <div className="absolute inset-0 rounded-full bg-amber-500 blur-xl opacity-35 animate-pulse pointer-events-none" />
            )}
            <div
              className={`relative w-20 h-20 sm:w-24 sm:h-24 rounded-full flex items-center justify-center font-black text-4xl sm:text-5xl shadow-2xl border-2 ${
                isHighRisk
                  ? "bg-gradient-to-b from-red-500 to-red-700 border-red-300 text-white"
                  : isSuspicious
                  ? "bg-gradient-to-b from-orange-500 to-red-600 border-orange-300 text-white"
                  : isCaution
                  ? "bg-gradient-to-b from-amber-500 to-yellow-600 border-amber-300 text-black"
                  : isVerified
                  ? "bg-gradient-to-b from-emerald-500 to-emerald-700 border-emerald-300 text-white"
                  : isUnverified
                  ? "bg-[var(--bg-surface)] border-[var(--border-default)] text-[var(--text-primary)]"
                  : "bg-[var(--bg-surface)] border-[var(--border-default)] text-[var(--text-muted)]"
              }`}
            >
              {isHighRisk && "✕"}
              {isSuspicious && "▲"}
              {isCaution && "!"}
              {isVerified && "✓"}
              {isUnverified && "ℹ"}
              {isInsufficient && "…"}
            </div>
          </div>
        </div>

        {/* Huge Unambiguous Headline (Max 6-8 Words) */}
        <div className="space-y-3 max-w-3xl mx-auto">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-black/40 border border-white/10 text-xs font-mono font-bold tracking-wider uppercase text-[var(--text-secondary)]">
            <span>REAL-TIME THREAT VERDICT</span>
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                isHighRisk || isSuspicious
                  ? "bg-[var(--danger)] animate-ping"
                  : isCaution
                  ? "bg-[var(--warning-text)] animate-ping"
                  : isVerified
                  ? "bg-[var(--success)]"
                  : "bg-slate-400"
              }`}
            />
          </div>

          <h1
            className={`text-2xl sm:text-4xl font-black tracking-tight leading-tight uppercase font-mono ${
              isHighRisk
                ? "text-[var(--danger)] drop-shadow-sm"
                : isSuspicious
                ? "text-[var(--danger)]"
                : isCaution
                ? "text-[var(--warning-text)]"
                : isVerified
                ? "text-[var(--success)]"
                : isUnverified
                ? "text-[var(--text-primary)]"
                : "text-[var(--text-muted)]"
            }`}
          >
            {isHighRisk && "FAKE VOICE DETECTED — DO NOT SEND MONEY"}
            {isSuspicious && "SUSPICIOUS CALL — HIGH PROBABILITY OF AI SCAM"}
            {isCaution && "EXERCISE CAUTION — UNUSUAL MONEY DEMAND"}
            {isVerified && `SAFE CALL — VERIFIED AS ${getMatchedName().toUpperCase()}`}
            {isUnverified && "AUTOMATED CALL — NO SCAM DETECTED"}
            {isInsufficient && "COULD NOT VERIFY — PLEASE TRY AGAIN"}
          </h1>

          {/* Plain Single-Sentence Explanation (Zero Jargon) */}
          <p className="text-base sm:text-xl text-[var(--text-secondary)] leading-relaxed font-medium max-w-2xl mx-auto">
            {isHighRisk &&
              `The voice sounds like ${getMatchedName()}, but our AI detected it was artificially created to trick you into transferring money.`}
            {isSuspicious &&
              "Caller is claiming an emergency or deposit demand from an unverified synthetic voice. Do not transfer funds."}
            {isCaution &&
              `The voice matches ${getMatchedName()}, but an unexpected urgent money demand was detected. Double check with a secret question.`}
            {isVerified &&
              `The voice matches your enrolled family voiceprint for ${getMatchedName()}. It is safe to talk.`}
            {isUnverified &&
              "This caller is an automated service (like a bank notification). No emergency scam demands were detected."}
            {isInsufficient &&
              "The audio was too short or noisy to evaluate reliably. Ask the caller to speak clearly for a few seconds and try again."}
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
      {(isHighRisk || isSuspicious || isCaution) && (
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
                      ? isCaution
                        ? "bg-[var(--warning-text)] text-black ring-2 ring-amber-500/40"
                        : "bg-[var(--danger)] text-white ring-2 ring-red-500/40"
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

          {/* Wizard Step 1: Hang Up or Pause */}
          {currentStep === 1 && (
            <div className="space-y-4">
              <div
                className={`sec-card-subtle p-5 space-y-2 border ${
                  isCaution
                    ? "border-amber-500/30 bg-amber-950/20"
                    : "border-red-500/20 bg-red-950/20"
                }`}
              >
                <div
                  className={`text-xs font-bold uppercase font-mono tracking-wider ${
                    isCaution ? "text-[var(--warning-text)]" : "text-[var(--danger)]"
                  }`}
                >
                  Step 1 of 3:
                </div>
                <div className="text-xl sm:text-2xl font-bold text-[var(--text-primary)]">
                  {isCaution
                    ? "Do not rush to transfer any money."
                    : "Hang up the call immediately."}
                </div>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
                  {isCaution
                    ? "Never send money immediately under pressure. Take a moment to verify before clicking any payment link or entering a UPI PIN."
                    : "Do not argue, do not send any money, and do not enter any UPI PIN. Simply disconnect the call."}
                </p>
              </div>

              <PearlButton
                onClick={() => setCurrentStep(2)}
                variant="default"
                size="lg"
                className="w-full font-mono font-bold"
                label={isCaution ? "I Paused Payment → Next Step" : "I Have Hung Up → Next Step"}
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
                  Call {getMatchedName()} directly from your contacts list.
                </div>
                <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
                  Dial their saved number directly from your phone's contact book to confirm if they actually requested funds.
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

          {/* Wizard Step 3: Ask Challenge Question or File Report */}
          {currentStep === 3 && (
            <div className="space-y-4">
              <div className="p-5 rounded-xl bg-[var(--warning-bg)] border border-[var(--warning-border)] space-y-2">
                <div className="text-xs font-bold text-[var(--warning-text)] uppercase font-mono tracking-wider">
                  Step 3 of 3:
                </div>
                <div className="text-base font-bold text-[var(--warning-text)]">
                  Ask them your secret family question:
                </div>
                <div className="text-xl font-extrabold text-[var(--text-primary)] p-4 rounded-lg bg-[var(--bg-primary)] border border-[var(--warning-border)] font-mono">
                  "{fusion.challenge_question?.question_text || "What was our first pet's name?"}"
                </div>
                <p className="text-xs text-[var(--warning-text)] leading-relaxed">
                  Your real family member will know the answer instantly. A scammer or AI system will fail.
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
                    variant={isCaution ? "default" : "danger"}
                    size="md"
                    className="w-full font-mono font-bold"
                    label="View 1930 Cybercrime Dossier →"
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
              incriminatingMarkers={script.incriminating_markers}
              exculpatoryMarkers={script.exculpatory_markers}
              playbooks={script.playbooks}
            />
          </div>
        )}
      </div>
    </div>
  );
}
