import { useState } from "react";
import { type ScreeningResponse, TrustBand } from "../types/contracts";
import { Link } from "react-router-dom";

interface VerdictCardProps {
  data: ScreeningResponse;
}

export default function VerdictCard({ data }: VerdictCardProps) {
  const { fusion, speaker, transcript } = data;
  const isHighRisk = fusion.band === TrustBand.HIGH_RISK;
  const isVerified = fusion.band === TrustBand.VERIFIED;
  const isUnverified = fusion.band === TrustBand.UNVERIFIED;
  const isInsufficient = fusion.band === TrustBand.INSUFFICIENT;

  const [isSpeaking, setIsSpeaking] = useState(false);

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
      utterance.onend = () => setIsSpeaking(false);
      utterance.onerror = () => setIsSpeaking(false);
      setIsSpeaking(true);
      window.speechSynthesis.speak(utterance);
    }
  };

  return (
    <div className="space-y-5">
      {/* ── Main Verdict Box ──────────────────────────────── */}
      <div
        className={`clean-card p-6 border transition-all ${
          isHighRisk
            ? "border-red-600/40 bg-gradient-to-b from-red-950/30 via-[var(--color-bg-primary)] to-[var(--color-bg-primary)]"
            : isVerified
            ? "border-emerald-600/30 bg-gradient-to-b from-emerald-950/20 via-[var(--color-bg-primary)] to-[var(--color-bg-primary)]"
            : "border-[var(--color-border-default)]"
        }`}
      >
        {/* Vernacular Spoken Warning Banner (Hindi / Regional) */}
        {fusion.vernacular_warning && (
          <div className="mb-5 p-4 rounded-xl bg-red-950/50 border border-red-800/60 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-red-200">
            <div className="flex items-start gap-3">
              <span className="text-xl">⚠️</span>
              <div>
                <div className="text-xs font-bold uppercase tracking-wider text-red-300 mb-0.5">
                  चेतावनी (Spoken Warning)
                </div>
                <div className="text-sm font-semibold text-white leading-relaxed">
                  "{fusion.vernacular_warning}"
                </div>
              </div>
            </div>

            <button
              onClick={handlePlayVoiceWarning}
              className="px-3 py-1.5 rounded-lg bg-red-800/60 hover:bg-red-700/60 border border-red-600 text-xs font-medium text-white flex items-center gap-1.5 transition-colors cursor-pointer shrink-0"
            >
              <span>{isSpeaking ? "⏹️ Stop" : "🔊 Speak Out Loud"}</span>
            </button>
          </div>
        )}

        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
          {/* Status Headline & Explanation */}
          <div className="space-y-3 flex-1">
            <div className="flex flex-wrap items-center gap-2.5">
              <span
                className={`text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider ${
                  isHighRisk
                    ? "bg-red-500/20 text-red-400 border border-red-500/30"
                    : isVerified
                    ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    : isUnverified
                    ? "bg-slate-500/20 text-slate-300 border border-slate-500/30"
                    : "bg-zinc-500/20 text-zinc-300 border border-zinc-500/30"
                }`}
              >
                {isHighRisk && "🚨 High Risk Scam Call"}
                {isVerified && "🟢 Genuine Family Member"}
                {isUnverified && "⚪ Unverified Automated Call"}
                {isInsufficient && "⚠️ Audio Too Short"}
              </span>

              {speaker.matched_person_name && (
                <span className="text-xs px-2.5 py-1 rounded-full bg-[var(--color-bg-surface)] text-[var(--color-text-secondary)] font-medium border border-[var(--color-border-subtle)]">
                  Voice Target: {speaker.matched_person_name}
                </span>
              )}
            </div>

            <h2 className="text-xl sm:text-2xl font-bold text-[var(--color-text-primary)]">
              {isHighRisk && "Do Not Send Money — Suspected AI Voice Clone"}
              {isVerified && "This Call is Verified as Rahul"}
              {isUnverified && "Automated Service Call (No Scam Detected)"}
              {isInsufficient && "Could Not Verify — Please Ask Caller to Speak Again"}
            </h2>

            <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">
              {isHighRisk &&
                "The caller claims to be your family member in an emergency, but audio analysis detected deepfake speech synthesis (synthetic voice). They are demanding immediate UPI money while telling you not to inform anyone."}
              {isVerified &&
                `The voice closely matches your enrolled voiceprint for ${speaker.matched_person_name || "Rahul"}. Natural speech patterns confirm this is a real human call with no fraud indicators.`}
              {isUnverified &&
                "This caller is not in your family contacts. It appears to be an automated institutional service (like bank IVR). No emergency or financial extortion patterns were detected."}
              {isInsufficient &&
                "The audio recording was under 1.5 seconds or had high background noise. SatyaCheck safely declines to guess on insufficient data."}
            </p>
          </div>

          {/* Trust Score Badge */}
          <div className="flex flex-row md:flex-col items-center justify-center p-4 rounded-xl bg-[var(--color-bg-secondary)] border border-[var(--color-border-default)] shrink-0 min-w-[140px] text-center">
            <div className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-1">
              Safety Score
            </div>
            <div
              className={`text-3xl sm:text-4xl font-extrabold ${
                isHighRisk
                  ? "text-red-400"
                  : isVerified
                  ? "text-emerald-400"
                  : isUnverified
                  ? "text-slate-300"
                  : "text-zinc-400"
              }`}
            >
              {fusion.trust_score.toFixed(0)}
              <span className="text-sm font-normal text-[var(--color-text-muted)]">/100</span>
            </div>
            <div className="text-xs font-medium text-[var(--color-text-secondary)] mt-1">
              {isHighRisk ? "Severe Danger" : isVerified ? "Safe & Verified" : "Neutral Stranger"}
            </div>
          </div>
        </div>

        {/* ── Key Findings Bullets (Plain English) ─────────── */}
        <div className="mt-6 pt-5 border-t border-[var(--color-border-subtle)] grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="p-3 rounded-lg bg-[var(--color-bg-secondary)] border border-[var(--color-border-subtle)]">
            <div className="text-xs font-semibold text-[var(--color-text-muted)] uppercase mb-1">
              1. Voice Match
            </div>
            <div className="text-sm font-medium text-[var(--color-text-primary)]">
              {speaker.matched_person_name
                ? `Sounds like ${speaker.matched_person_name}`
                : "Unknown caller"}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-[var(--color-bg-secondary)] border border-[var(--color-border-subtle)]">
            <div className="text-xs font-semibold text-[var(--color-text-muted)] uppercase mb-1">
              2. Voice Authenticity
            </div>
            <div
              className={`text-sm font-medium ${
                data.spoof.is_synthetic ? "text-red-400 font-semibold" : "text-emerald-400"
              }`}
            >
              {data.spoof.is_synthetic
                ? `AI Cloned Voice (Peak: ${(data.spoof.peak_score * 100).toFixed(0)}%)`
                : "Natural Human Voice"}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-[var(--color-bg-secondary)] border border-[var(--color-border-subtle)]">
            <div className="text-xs font-semibold text-[var(--color-text-muted)] uppercase mb-1">
              3. Call Intent
            </div>
            <div
              className={`text-sm font-medium ${
                data.script.risk > 0.5 ? "text-red-400 font-semibold" : "text-[var(--color-text-primary)]"
              }`}
            >
              {data.script.intent_summary || "Routine conversation"}
            </div>
          </div>
        </div>
      </div>

      {/* ── What to do right now (Action Checklist) ────────── */}
      {fusion.recommended_actions.length > 0 && (
        <div className="clean-card p-5 border border-blue-500/20 bg-[var(--color-bg-primary)]">
          <h3 className="text-sm font-bold text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
            <span>🛡️</span>
            <span>Recommended Actions For You Right Now:</span>
          </h3>

          <div className="space-y-2.5">
            {fusion.recommended_actions.map((action, idx) => (
              <div
                key={idx}
                className="p-3 rounded-lg bg-[var(--color-bg-secondary)] border border-[var(--color-border-subtle)] flex items-start gap-3"
              >
                <span className="w-5 h-5 rounded-full bg-blue-600/20 text-blue-400 font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">
                  {idx + 1}
                </span>
                <span className="text-sm text-[var(--color-text-primary)] font-medium leading-snug">
                  {action}
                </span>
              </div>
            ))}
          </div>

          {/* Quick Helpline Links */}
          <div className="mt-4 pt-3 border-t border-[var(--color-border-subtle)] flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="text-[var(--color-text-secondary)]">
              Need help? National Cyber Helpline: <strong className="text-red-400">1930</strong>
            </div>
            <Link
              to="/report"
              className="text-blue-400 hover:text-blue-300 font-semibold no-underline flex items-center gap-1"
            >
              <span>Download Official Incident Report for Police / Bank →</span>
            </Link>
          </div>
        </div>
      )}

      {/* ── Challenge Question Box (For Family Verification) ── */}
      {fusion.challenge_question && (
        <div className="clean-card p-5 border border-amber-500/30 bg-amber-950/10">
          <div className="flex items-start gap-3">
            <span className="text-2xl">❓</span>
            <div className="space-y-1.5 flex-1">
              <div className="text-xs font-bold uppercase tracking-wider text-amber-400">
                Ask This Challenge Question to Verify Identity:
              </div>
              <div className="text-base font-bold text-amber-200">
                "{fusion.challenge_question.question_text}"
              </div>
              <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
                If this is really your family member, they will know the answer immediately. An AI clone or scammer will hesitate or make excuses.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ── What the Caller Said (Transcript) ──────────────── */}
      {transcript.text && (
        <div className="clean-card p-5">
          <h3 className="text-sm font-bold text-[var(--color-text-primary)] mb-2 flex items-center gap-2">
            <span>📝</span>
            <span>What Was Said on the Call:</span>
          </h3>
          <div className="p-3.5 rounded-lg bg-[var(--color-bg-secondary)] border border-[var(--color-border-subtle)] text-sm text-[var(--color-text-primary)] leading-relaxed italic">
            "{transcript.text}"
          </div>
        </div>
      )}
    </div>
  );
}
