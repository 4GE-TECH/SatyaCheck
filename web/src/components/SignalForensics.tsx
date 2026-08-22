import type { ScreeningResponse } from "../types/contracts";

interface SignalForensicsProps {
  data: ScreeningResponse;
}

export default function SignalForensics({ data }: SignalForensicsProps) {
  const { speaker, spoof, script, fusion } = data;

  return (
    <div className="hud-panel p-4 space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-white/10 font-mono">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-white"></span>
          <h3 className="text-xs font-bold uppercase tracking-wider text-white">
            TRI-BRANCH SIGNAL FUSION BREAKDOWN
          </h3>
        </div>
        <span className="text-[10px] text-zinc-500">
          S-NORMALIZED HARMONIC SUMMATION
        </span>
      </div>

      {/* Signal Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 font-mono">
        {/* Branch 1: Identity */}
        <div className="p-3 rounded bg-[#050505] border border-white/10 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-white">
              01 // IDENTITY (ECAPA)
            </span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-white/10 text-white border border-white/20 font-bold">
              {(fusion.weights_used.asv_weight * 100).toFixed(0)}% WT
            </span>
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-[11px]">
              <span className="text-zinc-500">Identity Risk:</span>
              <span className="text-white font-bold">
                {(fusion.identity_risk * 100).toFixed(1)}%
              </span>
            </div>
            <div className="h-1 rounded bg-zinc-900 overflow-hidden">
              <div
                className="h-full bg-white transition-all duration-500"
                style={{ width: `${Math.max(2, fusion.identity_risk * 100)}%` }}
              />
            </div>
          </div>

          <div className="pt-2 border-t border-white/10 text-[10px] space-y-1 text-zinc-400">
            <div className="flex justify-between">
              <span>Verdict:</span>
              <span className="text-white font-bold uppercase">
                {speaker.verdict}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Cosine Raw:</span>
              <span className="text-white">{speaker.raw_score.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span>S-Norm Score:</span>
              <span className="text-white">{speaker.norm_score.toFixed(2)}</span>
            </div>
          </div>
        </div>

        {/* Branch 2: Authenticity (Anti-Spoof) */}
        <div className="p-3 rounded bg-[#050505] border border-white/10 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-white">
              02 // AUTHENTICITY (CM)
            </span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-white/10 text-white border border-white/20 font-bold">
              {(fusion.weights_used.cm_weight * 100).toFixed(0)}% WT
            </span>
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-[11px]">
              <span className="text-zinc-500">Effective Risk:</span>
              <span className="text-white font-bold">
                {(fusion.authenticity_risk_effective * 100).toFixed(1)}%
              </span>
            </div>
            <div className="h-1 rounded bg-zinc-900 overflow-hidden">
              <div
                className="h-full bg-rose-500 transition-all duration-500"
                style={{ width: `${Math.max(2, fusion.authenticity_risk_effective * 100)}%` }}
              />
            </div>
          </div>

          <div className="pt-2 border-t border-white/10 text-[10px] space-y-1 text-zinc-400">
            <div className="flex justify-between">
              <span>Peak Synth:</span>
              <span className="text-white">{(spoof.peak_score * 100).toFixed(0)}%</span>
            </div>
            <div className="flex justify-between">
              <span>Max Synth Run:</span>
              <span className="text-white">{spoof.max_synth_run_s.toFixed(1)}s</span>
            </div>
            <div className="flex justify-between">
              <span>Intent Gated:</span>
              <span className="text-emerald-400 font-bold">ACTIVE</span>
            </div>
          </div>
        </div>

        {/* Branch 3: Script & Intent (NLP/RAG) */}
        <div className="p-3 rounded bg-[#050505] border border-white/10 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-white">
              03 // INTENT & SCRIPT
            </span>
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-white/10 text-white border border-white/20 font-bold">
              {(fusion.weights_used.text_weight * 100).toFixed(0)}% WT
            </span>
          </div>

          <div className="space-y-1">
            <div className="flex justify-between text-[11px]">
              <span className="text-zinc-500">Script Risk:</span>
              <span className="text-white font-bold">
                {(fusion.intent_risk * 100).toFixed(1)}%
              </span>
            </div>
            <div className="h-1 rounded bg-zinc-900 overflow-hidden">
              <div
                className="h-full bg-rose-500 transition-all duration-500"
                style={{ width: `${Math.max(2, fusion.intent_risk * 100)}%` }}
              />
            </div>
          </div>

          <div className="pt-2 border-t border-white/10 text-[10px] space-y-1 text-zinc-400">
            <div className="flex justify-between">
              <span>Incriminating:</span>
              <span className="text-rose-400 font-bold">{script.incriminating_markers.length} patterns</span>
            </div>
            <div className="flex justify-between">
              <span>Exculpatory:</span>
              <span className="text-emerald-400 font-bold">{script.exculpatory_markers.length} patterns</span>
            </div>
            <div className="flex justify-between">
              <span>Playbook RAG:</span>
              <span className="text-white">
                {script.playbooks.length > 0 ? `${(script.playbooks[0].similarity_score * 100).toFixed(0)}% match` : "0 matches"}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Formula Footer */}
      <div className="p-2.5 rounded bg-[#030303] border border-white/10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-[10px] font-mono text-zinc-400">
        <div>
          <span className="text-white font-bold">INTENT-GATING FORMULA: </span>
          <span>r_cm_eff = r_cm * (0.25 + 0.75 * max(script_risk, mismatch))</span>
        </div>
        <div className="text-white font-bold">
          FUSED SCORE: {fusion.trust_score.toFixed(1)} / 100
        </div>
      </div>
    </div>
  );
}
