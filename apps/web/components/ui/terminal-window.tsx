import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * A framed instrument panel with a terminal title bar (traffic-light dots +
 * title + optional right-aligned meta). Wraps arbitrary content so a section
 * reads as a diagnostic readout rather than a generic card.
 */
export function TerminalWindow({
  title,
  meta,
  children,
  className,
  bodyClassName,
  tone = "surface",
}: {
  title: string;
  meta?: string;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  tone?: "surface" | "inset" | "raised";
}) {
  const bg =
    tone === "inset" ? "bg-inset" : tone === "raised" ? "bg-raised" : "bg-surface";
  return (
    <div
      className={cn(
        "border-hairline overflow-hidden rounded-md border",
        bg,
        className,
      )}
    >
      <div className="border-hairline bg-[color-mix(in_srgb,var(--color-void)_35%,transparent)] flex items-center gap-3 border-b px-4 py-2.5">
        <span className="flex items-center gap-1.5" aria-hidden="true">
          <span className="bg-hairline-strong h-2.5 w-2.5 rounded-full" />
          <span className="bg-hairline-strong h-2.5 w-2.5 rounded-full" />
          <span className="bg-hairline-strong h-2.5 w-2.5 rounded-full" />
        </span>
        <span className="text-mute truncate font-mono text-mono-sm">{title}</span>
        {meta && (
          <span className="text-mute ml-auto hidden shrink-0 font-mono text-mono-sm sm:inline">
            {meta}
          </span>
        )}
      </div>
      <div className={cn("p-5 md:p-6", bodyClassName)}>{children}</div>
    </div>
  );
}
