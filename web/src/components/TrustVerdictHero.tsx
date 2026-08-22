import { type ScreeningResponse, OperatingMode, BAND_CONFIG, TrustBand } from "../types/contracts";
import { Link } from "react-router-dom";

interface TrustVerdictHeroProps {
  data: ScreeningResponse;
}

export default function TrustVerdictHero({ data }: TrustVerdictHeroProps) {
  const { fusion, speaker, quality, processing_time_ms, audio_sha256 } = data;
  const config = BAND_CONFIG[fusion.band];
  const isHighRisk = fusion.band === TrustBand.HIGH_RISK;
  const isVerified = fusion.band === TrustBand.VERIFIED;
  const isUnverified = fusion.band === TrustBand.UNVERIFIED;

  return (
    <div
      className={`panel-card p-5 relative overflow-hidden transition-all border ${
        isHighRisk
          ? "border-red-500/50 bg-gradient-to-r from-red-950/20 via-[var(--color-bg-primary)] to-[var(--color-bg-primary)]"
          : isVerified
          ? "border-emerald-500/40 bg-gradient-to-r from-emerald-950/20 via-[var(--color-bg-primary)] to-[var(--color-bg-primary)]"
          : "border-[var(--color-border-default)]"
      }`}
    >
      {/* Top Banner for High Risk / Vernacular Alert */}
      {fusion.vernacular_warning && (
        <div className="mb-4 -mx-5 -mt-5 px-5 py-2.5 bg-red-600/20 border-b border-red-500/30 flex items-center justify-between gap-3 text-red-200">
          <div className="flex items-center gap-2.5 text-xs font-sans font-semibold">
            <span className="w-4 h-4 rounded-full bg-red-500 text-white flex items-center justify-center font-mono font-bold text-[10px]">
              !
            </span>
            <span>{fusion.vernacular_warning}</span>
          </div>
          <span className="text-[10px] font-mono uppercase bg-red-500/30 px-2 py-0.5 rounded text-red-100 font-semibold shrink-0">
            FRAUD ALERT
          </span>
        </div>
      )}

      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
        {/* Left: Authoritative Score & Classification */}
        <div className="flex items-center gap-6">
          {/* Trust Score Box */}
          <div
            className="flex flex-col items-center justify-center w-28 h-28 rounded-lg border font-mono relative shrink-0"
            style={{
              backgroundColor: "var(--color-bg-secondary)",
              borderColor: config.color,
              boxShadow: `0 0 20px ${config.glowColor}`,
            }}
          >
            <span className="text-[10px] uppercase font-bold tracking-widest text-[var(--color-text-muted)]">
              TRUST INDEX
            </span>
            <span
              className="text-4xl font-extrabold tracking-tight"
              style={{ color: config.textColor }}
            >
              {fusion.trust_score.toFixed(0)}
            </span>
            <span className="text-[10px] font-medium text-[var(--color-text-muted)]">
              / 100
            </span>

            <div
              className="absolute -bottom-2 px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider text-white"
              style={{ backgroundColor: config.color }}
            >
              {config.label}
            </div>
          </div>

          {/* Verdict Description & Identity Resolution */}
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <span
                className="text-xs font-mono font-bold px-2 py-0.5 rounded uppercase"
                style={{
                  backgroundColor: config.bgColor,
                  color: config.textColor,
                  border: `1px solid ${config.color}50`,
                }}
              >
                BAND: {config.label}
              </span>

              <span className="text-xs font-mono px-2 py-0.5 rounded bg-[var(--color-bg-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border-default)]">
                MODE: {fusion.mode === OperatingMode.IDENTITY_CHECK ? "IDENTITY_CHECK" : "AUTHORITY_CHECK"}
              </span>

              {speaker.matched_person_name && (
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/60 font-semibold">
                  MATCH: {speaker.matched_person_name}
                </span>
              )}
            </div>

            <h3 className="text-lg font-bold tracking-tight text-[var(--color-text-primary)]">
              {isHighRisk && "High Probability Voice-Cloning Fraud"}
              {isVerified && "Authenticated Contact Match (Organic Speech)"}
              {isUnverified && "Unregistered Caller (Intent-Gated Synthetic Voice)"}
              {fusion.band === TrustBand.INSUFFICIENT && "Refusal to Score: Insufficient Audio Duration"}
              {fusion.band === TrustBand.CAUTION && "Elevated Caution: Verify Out-of-Band"}
              {fusion.band === TrustBand.SUSPICIOUS && "Suspicious Voice Artifacts & Script Pressure"}
            </h3>

            <p className="text-xs text-[var(--color-text-secondary)] max-w-2xl mt-0.5 leading-relaxed">
              {isHighRisk &&
                "Acoustic synthesis signatures detected along with urgent financial isolation demands. Do not transfer funds or share OTP."}
              {isVerified &&
                `Enrolled acoustic centroid matches ${speaker.matched_person_name || "target"}. Natural pitch jitter confirms authentic human speech.`}
              {isUnverified &&
                "Caller is not in the enrolled family registry. Synthetic speech detected in benign institutional context (IVR)."}
              {fusion.band === TrustBand.INSUFFICIENT &&
                `Audio sample duration (${quality.speech_duration_s.toFixed(1)}s) is below the minimum required 1.5s security threshold.`}
            </p>
          </div>
        </div>

        {/* Right: Technical Telemetry & Quick Action */}
        <div className="flex flex-col sm:flex-row lg:flex-col items-start lg:items-end justify-between gap-3 border-t lg:border-t-0 lg:border-l border-[var(--color-border-subtle)] pt-4 lg:pt-0 lg:pl-6 shrink-0">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-left lg:text-right font-mono text-[11px]">
            <div>
              <span className="text-[var(--color-text-muted)]">INFERENCE: </span>
              <span className="text-[var(--color-text-primary)] font-semibold">{processing_time_ms.toFixed(1)} ms</span>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)]">SPEECH: </span>
              <span className="text-[var(--color-text-primary)] font-semibold">{quality.speech_duration_s.toFixed(1)}s</span>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)]">EST. SNR: </span>
              <span className="text-[var(--color-text-primary)] font-semibold">{quality.snr_db.toFixed(1)} dB</span>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)]">DIGEST: </span>
              <span className="text-[var(--color-text-primary)] font-semibold" title={audio_sha256}>
                {audio_sha256.slice(0, 8)}...
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Link
              to="/report"
              className="px-3 py-1.5 rounded text-xs font-mono font-semibold bg-[var(--color-bg-surface)] hover:bg-[var(--color-bg-elevated)] border border-[var(--color-border-strong)] text-[var(--color-text-primary)] no-underline flex items-center gap-1.5 transition-all cursor-pointer shadow-sm"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              EVIDENCE DOSSIER
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
