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
      utterance.rate = 0.9; // slightly slower for elderly clarity
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
        className={`p-6 sm:p-8 rounded-2xl border-2 shadow-2xl text-center space-y-6 transition-all ${
          isHighRisk
            ? "bg-[#7F1D1D]/30 border-red-500 text-white"
            : isVerified
            ? "bg-[#14532D]/30 border-emerald-500 text-white"
            : isUnverified
            ? "bg-[#1E293B] border-slate-600 text-white"
            : "bg-[#1F2937] border-zinc-600 text-white"
        }`}
      >
        {/* Giant Status Icon */}
        <div className="flex justify-center">
          <div
            className={`w-20 h-20 sm:w-24 sm:h-24 rounded-full flex items-center justify-center font-extrabold text-4xl sm:text-5xl shadow-lg border-4 ${
              isHighRisk
                ? "bg-red-600 border-red-300 text-white animate-bounce"
                : isVerified
                ? "bg-emerald-600 border-emerald-300 text-white"
                : isUnverified
                ? "bg-slate-600 border-slate-400 text-white"
                : "bg-zinc-600 border-zinc-400 text-white"
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
            className={`text-2xl sm:text-4xl font-extrabold tracking-tight leading-tight ${
              isHighRisk
                ? "text-red-400"
                : isVerified
                ? "text-emerald-400"
                : isUnverified
                ? "text-slate-200"
                : "text-zinc-300"
            }`}
          >
            {isHighRisk && "FAKE VOICE DETECTED — DO NOT SEND MONEY"}
            {isVerified && "SAFE CALL — VERIFIED AS RAHUL"}
            {isUnverified && "AUTOMATED CALL — NO SCAM DETECTED"}
            {isInsufficient && "COULD NOT VERIFY — PLEASE TRY AGAIN"}
          </h1>

          {/* Plain Single-Sentence Explanation (Zero Jargon) */}
          <p className="text-lg sm:text-xl text-slate-200 leading-relaxed font-medium">
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
              className="w-full max-w-md mx-auto py-4 px-6 rounded-2xl bg-red-700 hover:bg-red-600 text-white font-bold text-lg shadow-lg flex items-center justify-center gap-3 transition-all cursor-pointer border-2 border-red-400"
            >
              <span className="text-2xl">{isSpeaking ? "⏹" : "🔊"}</span>
              <span>
                {isSpeaking ? "Stop Hindi Warning" : "Listen to Warning in Hindi (चेतावनी सुनिए)"}
              </span>
            </button>
            <p className="text-xs text-slate-300 mt-2 italic">
              "{fusion.vernacular_warning}"
            </p>
          </div>
        )}
      </div>

      {/* ── 3. STEP-BY-STEP ACTION WIZARD (ONE CLEAR STEP AT A TIME) ── */}
      {isHighRisk && (
        <div className="p-6 sm:p-8 rounded-2xl bg-[#111827] border border-red-500/40 shadow-xl space-y-5">
          <div className="flex items-center justify-between border-b border-slate-700 pb-3">
            <h2 className="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
              <span>What to Do Right Now</span>
            </h2>
            <span className="text-xs font-bold px-3 py-1 rounded-full bg-red-950 text-red-300 border border-red-800">
              Step {currentStep} of 3
            </span>
          </div>

          {/* Wizard Step 1: Hang Up */}
          {currentStep === 1 && (
            <div className="space-y-4">
              <div className="p-5 rounded-xl bg-[#1F2937] border border-slate-600 space-y-2">
                <div className="text-xs font-bold text-red-400 uppercase tracking-wider">
                  Step 1 of 3:
                </div>
                <div className="text-xl sm:text-2xl font-bold text-white">
                  Hang up the call immediately.
                </div>
                <p className="text-base text-slate-300 leading-relaxed">
                  Do not argue, do not send any money, and do not enter any UPI PIN. Simply disconnect the call.
                </p>
              </div>

              <button
                onClick={() => setCurrentStep(2)}
                className="w-full py-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-base transition-colors shadow cursor-pointer"
              >
                I Have Hung Up → Next Step
              </button>
            </div>
          )}

          {/* Wizard Step 2: Call Back on Saved Number */}
          {currentStep === 2 && (
            <div className="space-y-4">
              <div className="p-5 rounded-xl bg-[#1F2937] border border-slate-600 space-y-2">
                <div className="text-xs font-bold text-blue-400 uppercase tracking-wider">
                  Step 2 of 3:
                </div>
                <div className="text-xl sm:text-2xl font-bold text-white">
                  Call {speaker.matched_person_name || "your family member"} on your regular phone.
                </div>
                <p className="text-base text-slate-300 leading-relaxed">
                  Dial their saved number directly from your contacts list. You will find they are safe and this call was a scam.
                </p>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setCurrentStep(1)}
                  className="w-1/3 py-3 rounded-xl bg-slate-700 hover:bg-slate-600 text-white font-semibold text-sm cursor-pointer"
                >
                  ← Back
                </button>
                <button
                  onClick={() => setCurrentStep(3)}
                  className="w-2/3 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold text-base cursor-pointer"
                >
                  Next: Challenge Question →
                </button>
              </div>
            </div>
          )}

          {/* Wizard Step 3: Ask Challenge Question */}
          {currentStep === 3 && (
            <div className="space-y-4">
              <div className="p-5 rounded-xl bg-amber-950/40 border border-amber-500/50 space-y-2">
                <div className="text-xs font-bold text-amber-400 uppercase tracking-wider">
                  Step 3 of 3 (If They Call Again):
                </div>
                <div className="text-lg sm:text-xl font-bold text-amber-200">
                  Ask them this secret question:
                </div>
                <div className="text-xl sm:text-2xl font-extrabold text-white p-3 rounded-lg bg-black/40 border border-amber-500/30">
                  "{fusion.challenge_question?.question_text || "What was our first pet's name?"}"
                </div>
                <p className="text-sm text-slate-300 leading-relaxed">
                  Your real family member will know the answer instantly. A scammer or AI system will not know.
                </p>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setCurrentStep(2)}
                  className="w-1/3 py-3 rounded-xl bg-slate-700 hover:bg-slate-600 text-white font-semibold text-sm cursor-pointer"
                >
                  ← Back
                </button>
                <Link
                  to="/report"
                  className="w-2/3 py-3 rounded-xl bg-red-700 hover:bg-red-600 text-white font-bold text-base flex items-center justify-center no-underline cursor-pointer"
                >
                  File Complaint on 1930 Portal →
                </Link>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── 4. CHECK ANOTHER CALL BUTTON ── */}
      <div className="text-center pt-2">
        <button
          onClick={onReset}
          className="py-3 px-8 rounded-xl bg-[#1F2937] hover:bg-[#374151] text-white font-semibold text-base border border-slate-600 transition-colors cursor-pointer"
        >
          ← Check Another Call
        </button>
      </div>

      {/* ── 5. OPTIONAL: SHOW TECHNICAL FORENSICS TOGGLE (COLLAPSED BY DEFAULT) ── */}
      <div className="pt-4 border-t border-slate-800">
        <div className="text-center">
          <button
            onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
            className="text-xs text-slate-400 hover:text-slate-200 font-mono underline cursor-pointer bg-transparent border-none py-2 px-4"
          >
            {showTechnicalDetails
              ? "▲ Hide Technical & Forensic Data"
              : "▼ Show Technical & Forensic Details (For Family Guardian / Cyber Officers)"}
          </button>
        </div>

        {showTechnicalDetails && (
          <div className="mt-5 p-6 rounded-2xl bg-[#0F172A] border border-slate-700 space-y-6">
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
