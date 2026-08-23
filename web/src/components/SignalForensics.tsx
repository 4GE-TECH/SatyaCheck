import type { ScreeningResponse } from "../types/contracts";

interface SignalForensicsProps {
  data: ScreeningResponse;
}

export default function SignalForensics({ data }: SignalForensicsProps) {
  const { speaker, spoof, script, fusion } = data;

  return (
    <div className="sec-card-subtle p-4 space-y-4 font-mono text-xs">
      <div className="flex items-center justify-between pb-2 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[var(--accent)]"></span>
          <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--text-primary)]">
            TRI-BRANCH SIGNAL FUSION BREAKDOWN
          </h3>
        </div>
        <span className="text-[10px] text-[var(--text-muted)]">
          S-NORMALIZED HARMONIC SUMMATION
        </span>
      </div>

      {/* Signal Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Branch 1: Identity */}
        <div className="p-3 rounded bg-[var(--bg-primary)] border border-[var(--border-default)] space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-[var(--text-primary)]">
              01 // IDENTITY (ECAPA)
            </span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border-default)] font-bold">
              {(fusion.weights_used.asv_weight * 100).toFixed(0)}% WT
            </span>
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-[11px]">
              <span className="text-[var(--text-muted)]">Identity Risk:</span>
              <span className="text-[var(--text-primary)] font-bold">
                {(fusion.identity_risk * 100).toFixed(1)}%
              </span>
            </div>
            <div className="h-1 rounded bg-[var(--bg-secondary)] overflow-hidden">
              <div
                className="h-full bg-[var(--accent)] transition-all duration-500"
                style={{ width: `${Math.max(2, fusion.identity_risk * 100)}%` }}
              />
            </div>
            <div className="text-[10px] text-[var(--text-muted)] leading-normal mt-0.5">
              ⓘ Probability of voice mismatch against enrolled family baseline.
            </div>
          </div>

          <div className="pt-2 border-t border-[var(--border-subtle)] text-[10px] space-y-2 text-[var(--text-secondary)]">
            <div>
              <div className="flex justify-between">
                <span>Verdict:</span>
                <span className="text-[var(--text-primary)] font-bold uppercase">
                  {speaker.verdict}
                </span>
              </div>
              <div className="text-[9px] text-[var(--text-muted)] mt-0.5">
                ⓘ Voice verification match state.
              </div>
            </div>

            <div>
              <div className="flex justify-between">
                <span>Cosine Raw:</span>
                <span className="text-[var(--text-primary)]">{speaker.raw_score.toFixed(2)}</span>
              </div>
              <div className="text-[9px] text-[var(--text-muted)] mt-0.5">
                ⓘ Direct similarity score of voice embeddings.
              </div>
            </div>

            <div>
              <div className="flex justify-between">
                <span>S-Norm Score:</span>
                <span className="text-[var(--text-primary)]">{speaker.norm_score.toFixed(2)}</span>
              </div>
              <div className="text-[9px] text-[var(--text-muted)] mt-0.5">
                ⓘ Normalized score calibrated against cohorts.
              </div>
            </div>
          </div>
        </div>

        {/* Branch 2: Authenticity (Anti-Spoof) */}
        <div className="p-3 rounded bg-[var(--bg-primary)] border border-[var(--border-default)] space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-[var(--text-primary)]">
              02 // AUTHENTICITY (CM)
            </span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border-default)] font-bold">
              {(fusion.weights_used.cm_weight * 100).toFixed(0)}% WT
            </span>
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-[11px]">
              <span className="text-[var(--text-muted)]">Effective Risk:</span>
              <span className="text-[var(--text-primary)] font-bold">
                {(fusion.authenticity_risk_effective * 100).toFixed(1)}%
              </span>
            </div>
            <div className="h-1 rounded bg-[var(--bg-secondary)] overflow-hidden">
              <div
                className="h-full bg-[var(--danger)] transition-all duration-500"
                style={{ width: `${Math.max(2, fusion.authenticity_risk_effective * 100)}%` }}
              />
            </div>
            <div className="text-[10px] text-[var(--text-muted)] leading-normal mt-0.5">
              ⓘ Combined probability that the audio is synthetic or computer-generated.
            </div>
          </div>

          <div className="pt-2 border-t border-[var(--border-subtle)] text-[10px] space-y-2 text-[var(--text-secondary)]">
            <div>
              <div className="flex justify-between">
                <span>Peak Synth:</span>
                <span className="text-[var(--text-primary)]">{(spoof.peak_score * 100).toFixed(0)}%</span>
              </div>
              <div className="text-[9px] text-[var(--text-muted)] mt-0.5">
                ⓘ Maximum single-segment AI clone probability.
              </div>
            </div>

            <div>
              <div className="flex justify-between">
                <span>Max Synth Run:</span>
                <span className="text-[var(--text-primary)]">{spoof.max_synth_run_s.toFixed(1)}s</span>
              </div>
              <div className="text-[9px] text-[var(--text-muted)] mt-0.5">
                ⓘ Longest contiguous segment of synthetic speech.
              </div>
            </div>

            <div>
              <div className="flex justify-between">
                <span>Intent Gated:</span>
                <span className="text-[var(--success-text)] font-bold">ACTIVE</span>
              </div>
              <div className="text-[9px] text-[var(--text-muted)] mt-0.5">
                ⓘ Synthesis threat verification gating mode.
              </div>
            </div>
          </div>
        </div>

        {/* Branch 3: Script & Intent (NLP/RAG) */}
        <div className="p-3 rounded bg-[var(--bg-primary)] border border-[var(--border-default)] space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-[var(--text-primary)]">
              03 // INTENT & SCRIPT
            </span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border-default)] font-bold">
              {(fusion.weights_used.text_weight * 100).toFixed(0)}% WT
            </span>
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-[11px]">
              <span className="text-[var(--text-muted)]">Script Risk:</span>
              <span className="text-[var(--text-primary)] font-bold">
                {(fusion.intent_risk * 100).toFixed(1)}%
              </span>
            </div>
            <div className="h-1 rounded bg-[var(--bg-secondary)] overflow-hidden">
              <div
                className="h-full bg-[var(--danger)] transition-all duration-500"
                style={{ width: `${Math.max(2, fusion.intent_risk * 100)}%` }}
              />
            </div>
            <div className="text-[10px] text-[var(--text-muted)] leading-normal mt-0.5">
              ⓘ Intent urgency threat marker score from natural language patterns.
            </div>
          </div>

          <div className="pt-2 border-t border-[var(--border-subtle)] text-[10px] space-y-2 text-[var(--text-secondary)]">
            <div>
              <div className="flex justify-between">
                <span>Incriminating:</span>
                <span className="text-[var(--danger-text)] font-bold">{script.incriminating_markers.length} patterns</span>
              </div>
              <div className="text-[9px] text-[var(--text-muted)] mt-0.5">
                ⓘ Extortion or emergency keywords detected.
              </div>
            </div>

            <div>
              <div className="flex justify-between">
                <span>Exculpatory:</span>
                <span className="text-[var(--success-text)] font-bold">{script.exculpatory_markers.length} patterns</span>
              </div>
              <div className="text-[9px] text-[var(--text-muted)] mt-0.5">
                ⓘ Clarifying/trust safety patterns detected.
              </div>
            </div>

            <div>
              <div className="flex justify-between">
                <span>Playbook RAG:</span>
                <span className="text-[var(--text-primary)]">
                  {script.playbooks.length > 0 ? `${(script.playbooks[0].similarity_score * 100).toFixed(0)}% match` : "0 matches"}
                </span>
              </div>
              <div className="text-[9px] text-[var(--text-muted)] mt-0.5">
                ⓘ Advisory match likelihood against RAG.
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Formula Footer */}
      <div className="p-2.5 rounded bg-[var(--bg-primary)] border border-[var(--border-default)] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-[10px] text-[var(--text-muted)]">
        <div>
          <span className="text-[var(--text-primary)] font-bold">INTENT-GATING FORMULA: </span>
          <span>r_cm_eff = r_cm * (0.25 + 0.75 * max(script_risk, mismatch))</span>
        </div>
        <div className="text-[var(--text-primary)] font-bold">
          FUSED SCORE: {fusion.trust_score.toFixed(1)} / 100
        </div>
      </div>
    </div>
  );
}
