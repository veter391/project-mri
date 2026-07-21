import { cn } from "@/lib/cn";

// Decision → Consequence Timeline Strip (DESIGN-SYSTEM §8.4). The connecting
// line is ALWAYS dashed — a permanent visual convention that this is a
// correlated link, never a proven causal one. Never reuse the dash elsewhere.
type Direction = "improved" | "regressed" | "inconclusive";
type Confidence = "LOW" | "MED" | "HIGH";

const DIRECTION_COLOR: Record<Direction, string> = {
  improved: "var(--color-risk-low)",
  regressed: "var(--color-risk-critical)",
  inconclusive: "var(--color-risk-none)",
};

export function DecisionConsequenceStrip({
  decision,
  consequence,
  direction,
  confidence,
  className,
}: {
  decision: string;
  consequence: string;
  direction: Direction;
  confidence: Confidence;
  className?: string;
}) {
  const color = DIRECTION_COLOR[direction];
  return (
    <div
      className={cn(
        "border-hairline bg-surface rounded-md border p-5",
        className,
      )}
    >
      <div className="flex items-center gap-3">
        {/* decision marker */}
        <span
          aria-hidden="true"
          className="bg-accent h-3 w-3 shrink-0 rounded-full"
        />
        {/* dashed correlation line + confidence chip */}
        <div className="relative flex-1">
          <div
            className="w-full border-t border-dashed"
            style={{ borderColor: "var(--color-hairline-strong)" }}
          />
          <span className="bg-surface text-mute absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 px-2 font-sans text-caption font-medium tracking-[0.04em] uppercase">
            {confidence} confidence
          </span>
        </div>
        {/* consequence marker (outlined, direction-colored) */}
        <span
          aria-hidden="true"
          className="h-3 w-3 shrink-0 rounded-full border-2"
          style={{ borderColor: color }}
        />
      </div>
      <div className="mt-3 flex items-start justify-between gap-4">
        <div className="max-w-[45%]">
          <p className="text-mute font-sans text-caption tracking-[0.04em] uppercase">
            Decision
          </p>
          <p className="text-secondary mt-1 font-body text-body-sm">{decision}</p>
        </div>
        <div className="max-w-[45%] text-right">
          <p className="text-mute font-sans text-caption tracking-[0.04em] uppercase">
            Consequence
          </p>
          <p
            className="mt-1 font-body text-body-sm"
            style={{ color }}
          >
            {consequence}
          </p>
        </div>
      </div>
      <p className="text-mute mt-3 font-mono text-mono-sm">
        Correlation, not causation — a dashed link, by design.
      </p>
    </div>
  );
}
