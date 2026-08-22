import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";
import type { SpoofSegment } from "../types/contracts";

interface SpoofTimelineProps {
  timeline: SpoofSegment[];
  threshold?: number;
}

export default function SpoofTimeline({
  timeline,
  threshold = 0.4,
}: SpoofTimelineProps) {
  if (timeline.length === 0) {
    return (
      <div className="hud-panel p-4 font-mono">
        <h3 className="text-xs font-bold uppercase tracking-wider text-white mb-2">
          ACOUSTIC SPOOF TIMELINE STRIP
        </h3>
        <p className="text-xs text-zinc-500 font-sans">
          No audio segments available for timeline rendering.
        </p>
      </div>
    );
  }

  const data = timeline.map((seg, i) => ({
    name: `${seg.start_s.toFixed(1)}–${seg.end_s.toFixed(1)}s`,
    score: seg.score,
    isSynthetic: seg.is_synthetic,
    index: i,
  }));

  return (
    <div className="hud-panel p-4 font-mono">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-white">
          SEGMENT-LEVEL SYNTHETIC PROBABILITY TIMELINE (AASIST-CM)
        </h3>
        <span className="text-[10px] text-zinc-500">
          THRESHOLD: {(threshold * 100).toFixed(0)}%
        </span>
      </div>

      <ResponsiveContainer width="100%" height={110}>
        <BarChart data={data} barCategoryGap="20%">
          <XAxis
            dataKey="name"
            tick={{ fontSize: 10, fill: "#71717A" }}
            axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            tick={{ fontSize: 10, fill: "#71717A" }}
            axisLine={false}
            tickLine={false}
            width={32}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#050505",
              border: "1px solid rgba(255,255,255,0.2)",
              borderRadius: 4,
              color: "#FFFFFF",
              fontSize: 11,
              fontFamily: "JetBrains Mono",
            }}
            formatter={(value: unknown) => [
              typeof value === "number" ? `${(value * 100).toFixed(1)}%` : String(value ?? ""),
              "SYNTHETIC PROB",
            ]}
          />
          <ReferenceLine
            y={threshold}
            stroke="#F43F5E"
            strokeDasharray="4 4"
            strokeOpacity={0.6}
          />
          <Bar dataKey="score" radius={[2, 2, 0, 0]}>
            {data.map((entry) => (
              <Cell
                key={entry.index}
                fill={entry.isSynthetic ? "#F43F5E" : "#10B981"}
                fillOpacity={0.85}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div className="flex items-center gap-4 mt-2 text-[10px] text-zinc-400 font-mono">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-sm bg-[#10B981]" />
          BONAFIDE SPEECH
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-sm bg-[#F43F5E]" />
          SYNTHETIC CLONE
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 border-t border-dashed border-[#F43F5E]" />
          DECISION THRESHOLD
        </span>
      </div>
    </div>
  );
}
