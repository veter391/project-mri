import { cn } from "@/lib/cn";
import { Badge } from "@/components/ui/badge";

// Session Trace Card (DESIGN-SYSTEM §8.3): one ingested AI session mapped to the
// files/commits it touched. The prompt excerpt is human-written text, so it is
// set in the UI typeface (Space Grotesk) — NOT mono; file paths stay mono.
type Source = "CLAUDE CODE" | "CURSOR" | "AGENT TRACE";
type Tier = "low" | "medium" | "high" | "critical";

const TIER_DOT: Record<Tier, string> = {
  low: "var(--color-risk-low)",
  medium: "var(--color-risk-medium)",
  high: "var(--color-risk-high)",
  critical: "var(--color-risk-critical)",
};

export function SessionTraceCard({
  source,
  when,
  prompt,
  files,
  className,
}: {
  source: Source;
  when: string;
  prompt: string;
  files: { path: string; tier: Tier }[];
  className?: string;
}) {
  return (
    <div
      className={cn(
        "border-hairline bg-surface rounded-md border p-5",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <Badge tone="ai">{source}</Badge>
        <span className="text-mute font-mono text-mono-sm">{when}</span>
      </div>
      <p className="text-secondary mt-3 font-sans text-body-sm leading-relaxed">
        <span className="text-mute">&ldquo;</span>
        {prompt}
        <span className="text-mute">&rdquo;</span>
      </p>
      <ul className="mt-4 flex flex-col gap-1.5">
        {files.map((f) => (
          <li
            key={f.path}
            className="text-secondary flex items-center gap-2 font-mono text-mono-sm"
          >
            <span
              aria-hidden="true"
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: TIER_DOT[f.tier] }}
            />
            {f.path}
          </li>
        ))}
      </ul>
    </div>
  );
}
