import { cn } from "@/lib/cn";

// Risk score is 0–100; higher = more risk. Discrete tiers, never a continuous
// gradient (DESIGN-SYSTEM §8.1) — the score is explainable and tiered.
type Tier = "low" | "medium" | "high" | "critical";

function tierFor(value: number): Tier {
  if (value >= 85) return "critical";
  if (value >= 60) return "high";
  if (value >= 40) return "medium";
  return "low";
}

const TIER_STROKE: Record<Tier, string> = {
  low: "var(--color-risk-low)",
  medium: "var(--color-risk-medium)",
  high: "var(--color-risk-high)",
  critical: "var(--color-risk-critical)",
};

const TIER_LABEL: Record<Tier, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

export function RiskRing({
  value,
  size = 96,
  label = true,
  className,
}: {
  value: number;
  size?: number;
  label?: boolean;
  className?: string;
}) {
  const v = Math.max(0, Math.min(100, value));
  const tier = tierFor(v);
  const stroke = size >= 80 ? 4 : 3;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - v / 100);

  return (
    <div className={cn("inline-flex flex-col items-center gap-2", className)}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          role="img"
          aria-label={`Risk score ${v} of 100, ${TIER_LABEL[tier]}`}
          className="-rotate-90"
        >
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--color-hairline)"
            strokeWidth={stroke}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={TIER_STROKE[tier]}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="absolute inset-0 grid place-items-center">
          <span
            className="font-mono font-semibold tabular-nums"
            style={{ fontSize: size >= 80 ? "var(--text-mono-lg)" : "var(--text-mono)" }}
          >
            {v}
          </span>
        </div>
      </div>
      {label && (
        <span className="font-sans text-caption font-medium tracking-[0.04em] uppercase" style={{ color: TIER_STROKE[tier] }}>
          Risk: {TIER_LABEL[tier]}
        </span>
      )}
    </div>
  );
}
