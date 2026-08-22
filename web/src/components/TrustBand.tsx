/**
 * TrustBand pill — coloured badge showing the current band.
 */

import { TrustBand as TrustBandEnum, BAND_CONFIG } from "../types/contracts";

interface TrustBandProps {
  band: TrustBandEnum;
  size?: "sm" | "md" | "lg";
}

const SIZES = {
  sm: "text-xs px-2 py-0.5",
  md: "text-sm px-3 py-1",
  lg: "text-base px-4 py-1.5 font-semibold",
};

export default function TrustBandPill({ band, size = "md" }: TrustBandProps) {
  const config = BAND_CONFIG[band];

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium uppercase tracking-wider ${SIZES[size]}`}
      style={{
        color: config.textColor,
        backgroundColor: config.bgColor,
        border: `1px solid ${config.color}33`,
      }}
    >
      <span
        className="w-2 h-2 rounded-full mr-1.5 shrink-0"
        style={{ backgroundColor: config.color }}
      />
      {config.label}
    </span>
  );
}
