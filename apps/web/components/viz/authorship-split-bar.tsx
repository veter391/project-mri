import { cn } from "@/lib/cn";

// Authorship Split Bar (DESIGN-SYSTEM §8.2): human / AI / mixed / unattributed,
// always in that left-to-right order. "unattributed" is deliberately distinct
// from "human" — the product never treats unattributed lines as human-written.
type Shares = {
  human: number;
  ai: number;
  mixed?: number;
  unattributed?: number;
};

const SEGMENTS: {
  key: keyof Shares;
  color: string;
  label: string;
}[] = [
  { key: "human", color: "var(--color-author-human)", label: "Human" },
  { key: "ai", color: "var(--color-author-ai)", label: "AI" },
  { key: "mixed", color: "var(--color-author-mixed)", label: "Mixed" },
  { key: "unattributed", color: "var(--color-risk-none)", label: "Unattributed" },
];

export function AuthorshipSplitBar({
  shares,
  height = 16,
  legend = true,
  className,
}: {
  shares: Shares;
  height?: number;
  legend?: boolean;
  className?: string;
}) {
  const present = SEGMENTS.filter((s) => (shares[s.key] ?? 0) > 0);
  const total =
    present.reduce((sum, s) => sum + (shares[s.key] ?? 0), 0) || 1;

  if (present.length === 0) {
    return (
      <div
        className={cn(
          "bg-inset text-mute grid place-items-center rounded-sm font-mono text-mono-sm",
          className,
        )}
        style={{ height }}
        role="img"
        aria-label="Authorship: no data"
      >
        No authorship data
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div
        className="bg-inset flex w-full overflow-hidden rounded-sm"
        style={{ height, gap: 1 }}
        role="img"
        aria-label={present
          .map((s) => `${s.label} ${Math.round(((shares[s.key] ?? 0) / total) * 100)}%`)
          .join(", ")}
      >
        {present.map((s) => (
          <div
            key={s.key}
            style={{
              width: `${((shares[s.key] ?? 0) / total) * 100}%`,
              background: s.color,
            }}
          />
        ))}
      </div>
      {legend && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1">
          {present.map((s) => (
            <li
              key={s.key}
              className="text-secondary flex items-center gap-1.5 font-mono text-mono-sm tabular-nums"
            >
              <span
                aria-hidden="true"
                className="inline-block h-2 w-2 rounded-[1px]"
                style={{ background: s.color }}
              />
              {s.label} {Math.round(((shares[s.key] ?? 0) / total) * 100)}%
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
