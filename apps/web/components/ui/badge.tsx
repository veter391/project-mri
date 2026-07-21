import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type Tone = "accent" | "neutral" | "ok" | "critical" | "ai";

const TONES: Record<Tone, string> = {
  accent: "text-accent border-[color-mix(in_srgb,var(--color-accent)_35%,transparent)] bg-[var(--accent-wash)]",
  neutral: "text-mute border-hairline-strong bg-surface",
  ok: "text-risk-low border-[color-mix(in_srgb,var(--color-risk-low)_35%,transparent)] bg-[color-mix(in_srgb,var(--color-risk-low)_8%,transparent)]",
  critical:
    "text-risk-critical border-[color-mix(in_srgb,var(--color-risk-critical)_35%,transparent)] bg-[color-mix(in_srgb,var(--color-risk-critical)_8%,transparent)]",
  ai: "text-author-ai border-[color-mix(in_srgb,var(--color-author-ai)_35%,transparent)] bg-[color-mix(in_srgb,var(--color-author-ai)_10%,transparent)]",
};

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-0.5 font-sans text-caption font-medium tracking-[0.04em] uppercase",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
