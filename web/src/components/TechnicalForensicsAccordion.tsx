import { useState } from "react";
import type { ScreeningResponse } from "../types/contracts";
import SignalForensics from "./SignalForensics";
import SpoofTimeline from "./SpoofTimeline";
import EvidencePanel from "./EvidencePanel";
import AudioInspector from "./AudioInspector";

interface TechnicalForensicsAccordionProps {
  data: ScreeningResponse;
}

export default function TechnicalForensicsAccordion({ data }: TechnicalForensicsAccordionProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="hud-panel overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full p-4 flex items-center justify-between bg-[#080808] hover:bg-[#101010] transition-colors cursor-pointer text-left border-none font-mono"
      >
        <div>
          <div className="text-xs font-bold uppercase tracking-wider text-white">
            ADVANCED FORENSICS & SIGNAL CITATIONS
          </div>
          <div className="text-[11px] text-zinc-500 font-sans mt-0.5">
            Acoustic timeline strip, ECAPA-TDNN vector stats, intent-gating multipliers, and I4C playbook links
          </div>
        </div>

        <div className="text-xs text-zinc-400 font-semibold px-2 py-1 rounded bg-white/5 border border-white/10">
          {isOpen ? "[- HIDE FORENSICS]" : "[+ VIEW FORENSICS]"}
        </div>
      </button>

      {isOpen && (
        <div className="p-5 border-t border-white/10 space-y-5 bg-[#000000]">
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
  );
}
