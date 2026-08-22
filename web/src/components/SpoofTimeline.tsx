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
import { useTheme } from "../context/ThemeContext";

interface SpoofTimelineProps {
  timeline: SpoofSegment[];
  threshold?: number;
}

export default function SpoofTimeline({
  timeline,
  threshold = 0.4,
}: SpoofTimelineProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";

  if (timeline.length === 0) {
    return (
      <div className="sec-card-subtle p-4 font-mono text-xs">
        <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--text-primary)] mb-2">
          ACOUSTIC SPOOF TIMELINE STRIP
        </h3>
        <p className="text-xs text-[var(--text-muted)] font-sans">
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

  const tickColor = isDark ? "#8B949E" : "#57606A";
  const axisColor = isDark ? "#30363D" : "#D0D7DE";
  const dangerColor = isDark ? "#F85149" : "#CF222E";
  const successColor = isDark ? "#3FB950" : "#1A7F37";
  const tooltipBg = isDark ? "#161B22" : "#FFFFFF";
  const tooltipBorder = isDark ? "#30363D" : "#D0D7DE";
  const tooltipText = isDark ? "#F0F6FC" : "#1F2328";

  return (
    <div className="sec-card-subtle p-4 font-mono text-xs space-y-2">
      <div>
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--text-primary)]">
            SEGMENT-LEVEL SYNTHETIC PROBABILITY TIMELINE (AASIST-CM)
          </h3>
          <span className="text-[10px] text-[var(--text-muted)]">
            THRESHOLD: {(threshold * 100).toFixed(0)}%
          </span>
        </div>
        <p className="text-[10px] text-[var(--text-secondary)] font-sans mt-0.5 leading-normal">
          ⓘ Shows likelihood of synthetic speech detected second-by-second (red bars indicate parts that sound artificially generated).
        </p>
      </div>

      <ResponsiveContainer width="100%" height={110}>
        <BarChart data={data} barCategoryGap="20%">
          <XAxis
            dataKey="name"
            tick={{ fontSize: 10, fill: tickColor }}
            axisLine={{ stroke: axisColor }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            tick={{ fontSize: 10, fill: tickColor }}
            axisLine={false}
            tickLine={false}
            width={32}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: tooltipBg,
              border: `1px solid ${tooltipBorder}`,
              borderRadius: 6,
              color: tooltipText,
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
            stroke={dangerColor}
            strokeDasharray="4 4"
            strokeOpacity={0.7}
          />
          <Bar dataKey="score" radius={[2, 2, 0, 0]}>
            {data.map((entry) => (
              <Cell
                key={entry.index}
                fill={entry.isSynthetic ? dangerColor : successColor}
                fillOpacity={0.85}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div className="flex items-center gap-4 mt-2 text-[10px] text-[var(--text-muted)] font-mono">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: successColor }} />
          BONAFIDE SPEECH
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: dangerColor }} />
          SYNTHETIC CLONE
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 border-t border-dashed" style={{ borderColor: dangerColor }} />
          DECISION THRESHOLD
        </span>
      </div>
    </div>
  );
}
