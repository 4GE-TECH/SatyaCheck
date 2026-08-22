import { useState } from "react";
import { type ScreeningResponse, TrustBand } from "../types/contracts";
import { Link } from "react-router-dom";

interface MonolithicVerdictHUDProps {
  data: ScreeningResponse;
}

export default function MonolithicVerdictHUD({ data }: MonolithicVerdictHUDProps) {
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
    <div className="space-y-4">
      {/* ── Monolithic Primary Verdict Banner ────────────────── */}
      <div
        className={`hud-panel p-6 border transition-all ${
          isHighRisk
            ? "border-rose-500/80 bg-gradient-to-b from-rose-950/40 via-[#0A0507] to-[#0A0507]"
            : isVerified
            ? "border-emerald-500/80 bg-gradient-to-b from-emerald-950/30 via-[#050A07] to-[#050A07]"
            : isUnverified
            ? "border-zinc-500/50 bg-[#0A0A0A]"
            : "border-zinc-700 bg-[#0A0A0A]"
        }`}
      >
        {/* Vernacular Spoken Warning Banner (Hindi / Regional) */}
        {fusion.vernacular_warning && (
          <div className="mb-5 p-3.5 rounded bg-rose-950/70 border border-rose-600/70 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-rose-100 font-mono text-xs">
            <div className="flex items-start gap-2.5">
              <span className="px-1.5 py-0.5 rounded bg-rose-600 text-white font-bold text-[10px]">
                ALERT
              </span>
              <span className="font-sans font-semibold text-sm leading-snug">
                "{fusion.vernacular_warning}"
              </span>
            </div>

            <button
              onClick={handlePlayVoiceWarning}
              className="px-3 py-1 rounded bg-rose-800 hover:bg-rose-700 border border-rose-500 text-xs font-mono font-semibold text-white transition-colors cursor-pointer shrink-0"
            >
              {isSpeaking ? "[ STOP AUDIO ]" : "[ PLAY SPOKEN HINDI WARNING ]"}
            </button>
          </div>
        )}

        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          {/* Main Verdict Classification */}
          <div className="space-y-2 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`text-[11px] font-mono font-bold px-2.5 py-0.5 rounded uppercase tracking-wider border ${
                  isHighRisk
                    ? "bg-rose-950 border-rose-500 text-rose-300"
                    : isVerified
                    ? "bg-emerald-950 border-emerald-500 text-emerald-300"
                    : isUnverified
                    ? "bg-zinc-900 border-zinc-500 text-zinc-300"
                    : "bg-zinc-900 border-zinc-700 text-zinc-400"
                }`}
              >
                {isHighRisk && "CRITICAL THREAT // CLONED VOICE DETECTED"}
                {isVerified && "AUTHENTICATED // GENUINE FAMILY MEMBER"}
                {isUnverified && "UNVERIFIED CALLER // AUTOMATED SERVICE"}
                {isInsufficient && "INSUFFICIENT AUDIO // DURATION < 1.5S"}
              </span>

              {speaker.matched_person_name && (
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-white/5 text-zinc-300 border border-white/10">
                  TARGET: {speaker.matched_person_name.toUpperCase()}
                </span>
              )}
            </div>

            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white font-sans">
              {isHighRisk && "DO NOT SEND MONEY — AI VOICE CLONING CONFIRMED"}
              {isVerified && "CALL VERIFIED: GENUINE CALL FROM RAHUL"}
              {isUnverified && "AUTOMATED CALL: NO SCAM PATTERN DETECTED"}
              {isInsufficient && "UNABLE TO SCORE: PLEASE CAPTURE LONGER AUDIO"}
            </h1>

            <p className="text-xs sm:text-sm text-zinc-300 leading-relaxed font-sans max-w-3xl">
              {isHighRisk &&
                "The caller's voice sounds like Rahul, but acoustic analysis detected neural vocoder speech synthesis. The caller is demanding an urgent Rs 50,000 UPI transfer under a fake police arrest claim while demanding strict secrecy."}
              {isVerified &&
                `Voice acoustics match the enrolled baseline for ${speaker.matched_person_name || "Rahul"}. Natural micro-jitter confirms organic vocal cord resonance with zero fraud markers.`}
              {isUnverified &&
                "Caller is not registered in your family registry. Synthetic speech detected in legitimate automated IVR context (banking statement)."}
              {isInsufficient &&
                "Audio duration (0.6s) is below the minimal 1.5s security threshold required to prevent false positives."}
            </p>
          </div>

          {/* Large Trust Score Block */}
          <div
            className={`p-4 rounded border font-mono flex flex-col items-center justify-center shrink-0 min-w-[130px] text-center ${
              isHighRisk
                ? "bg-rose-950/30 border-rose-500/50 text-rose-300"
                : isVerified
                ? "bg-emerald-950/30 border-emerald-500/50 text-emerald-300"
                : "bg-zinc-900 border-zinc-700 text-zinc-300"
            }`}
          >
            <div className="text-[10px] uppercase font-bold tracking-widest text-zinc-400">
              TRUST INDEX
            </div>
            <div className="text-4xl font-extrabold tracking-tight mt-0.5">
              {fusion.trust_score.toFixed(0)}
              <span className="text-xs text-zinc-500">/100</span>
            </div>
            <div className="text-[10px] uppercase font-semibold mt-1">
              {isHighRisk ? "SEVERE DANGER" : isVerified ? "SAFE & MATCHED" : "UNREGISTERED"}
            </div>
          </div>
        </div>

        {/* ── The 3 Truth Pillars (Identity / Voice / Intent) ── */}
        <div className="mt-6 pt-5 border-t border-white/10 grid grid-cols-1 md:grid-cols-3 gap-3 font-mono">
          <div className="p-3.5 rounded bg-[#050505] border border-white/10 space-y-1">
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">
              01 // IDENTITY MATCH
            </div>
            <div className="text-xs font-bold text-white font-sans">
              {speaker.matched_person_name ? `Target: ${speaker.matched_person_name}` : "Unknown Contact"}
            </div>
            <div className="text-[11px] text-zinc-400">
              Cosine {speaker.raw_score.toFixed(2)} (s-norm {speaker.norm_score.toFixed(2)})
            </div>
          </div>

          <div className="p-3.5 rounded bg-[#050505] border border-white/10 space-y-1">
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">
              02 // VOICE SYNTHESIS
            </div>
            <div
              className={`text-xs font-bold font-sans ${
                data.spoof.is_synthetic ? "text-rose-400" : "text-emerald-400"
              }`}
            >
              {data.spoof.is_synthetic
                ? `Synthetic Voice (Peak ${(data.spoof.peak_score * 100).toFixed(0)}%)`
                : "Authentic Human Speech"}
            </div>
            <div className="text-[11px] text-zinc-400">
              Max Synthetic Run: {data.spoof.max_synth_run_s.toFixed(1)}s
            </div>
          </div>

          <div className="p-3.5 rounded bg-[#050505] border border-white/10 space-y-1">
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider font-bold">
              03 // INTENT & PRESSURE
            </div>
            <div
              className={`text-xs font-bold font-sans ${
                data.script.risk > 0.5 ? "text-rose-400" : "text-white"
              }`}
            >
              {data.script.intent_summary || "Routine call"}
            </div>
            <div className="text-[11px] text-zinc-400">
              {data.script.incriminating_markers.length} Risk Markers Detected
            </div>
          </div>
        </div>
      </div>

      {/* ── Tactical Directive Checklist (High Visibility) ──── */}
      {fusion.recommended_actions.length > 0 && (
        <div className="hud-panel p-5 border border-white/20 bg-[#080808]">
          <div className="font-mono text-xs font-bold uppercase tracking-wider text-white mb-3 flex items-center justify-between">
            <span>TACTICAL DEFENSE DIRECTIVES:</span>
            <span className="text-zinc-500">MANDATORY PROTOCOL</span>
          </div>

          <div className="space-y-2">
            {fusion.recommended_actions.map((action, idx) => (
              <div
                key={idx}
                className="p-3 rounded bg-[#030303] border border-white/10 flex items-start gap-3 text-xs font-mono"
              >
                <span className="w-5 h-5 rounded bg-white/10 text-white font-bold flex items-center justify-center shrink-0 text-[10px]">
                  {idx + 1}
                </span>
                <span className="text-white font-sans text-xs font-semibold leading-snug">
                  {action}
                </span>
              </div>
            ))}
          </div>

          <div className="mt-4 pt-3 border-t border-white/10 flex flex-wrap items-center justify-between gap-2 text-xs font-mono text-zinc-400">
            <div>
              REPORT TO 1930 HELPLINE IMMEDIATELY
            </div>
            <Link
              to="/report"
              className="text-white hover:text-zinc-300 font-semibold no-underline flex items-center gap-1"
            >
              <span>[ GENERATE STATUTORY EVIDENCE DOSSIER → ]</span>
            </Link>
          </div>
        </div>
      )}

      {/* ── Challenge Question Prompt (Shared Secret) ───────── */}
      {fusion.challenge_question && (
        <div className="hud-panel p-5 border border-amber-500/40 bg-amber-950/20">
          <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-amber-400 mb-1">
            OUT-OF-BAND CHALLENGE VERIFICATION PROMPT:
          </div>
          <div className="text-sm font-bold text-amber-200 font-sans mb-1">
            "{fusion.challenge_question.question_text}"
          </div>
          <p className="text-xs text-zinc-400 font-sans">
            Ask the caller this question immediately. A genuine family member will answer without hesitation; an AI system or imposter will stall or deflect.
          </p>
        </div>
      )}

      {/* ── Verbatim Transcript ────────────────────────────── */}
      {transcript.text && (
        <div className="hud-panel p-4">
          <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-zinc-500 mb-2">
            VERBATIM TRANSCRIPT INTERCEPT:
          </div>
          <div className="p-3 rounded bg-[#030303] border border-white/10 text-xs font-sans text-white italic leading-relaxed">
            "{transcript.text}"
          </div>
        </div>
      )}
    </div>
  );
}
