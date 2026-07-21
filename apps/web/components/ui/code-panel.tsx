"use client";

import { useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { CopyIcon, CheckIcon } from "@/components/icons";

/**
 * Terminal / Code Panel (DESIGN-SYSTEM §8.5). Inset background, header with the
 * command/path + copy button, mono body with contained horizontal scroll.
 * `copyText` is the raw text placed on the clipboard; `children` is the (often
 * token-colored) display.
 */
export function CodePanel({
  title,
  meta,
  copyText,
  children,
  className,
}: {
  title: string;
  meta?: string;
  copyText: string;
  children: ReactNode;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(copyText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable — no-op */
    }
  }

  return (
    <div
      className={cn(
        "border-hairline bg-inset overflow-hidden rounded-md border",
        className,
      )}
    >
      <div className="border-hairline flex items-center justify-between gap-3 border-b px-4 py-2.5">
        <span className="text-mute truncate font-mono text-mono-sm">{title}</span>
        <div className="flex items-center gap-3">
          {meta && (
            <span className="text-mute hidden font-mono text-mono-sm sm:inline">
              {meta}
            </span>
          )}
          <button
            type="button"
            onClick={copy}
            className="text-mute hover:text-primary grid h-7 w-7 place-items-center rounded-sm transition-colors"
            aria-label={copied ? "Copied" : "Copy to clipboard"}
          >
            {copied ? (
              <CheckIcon width={15} height={15} className="text-risk-low" />
            ) : (
              <CopyIcon width={15} height={15} />
            )}
          </button>
        </div>
      </div>
      <pre className="overflow-x-auto px-4 py-4 font-mono text-mono leading-relaxed">
        <code>{children}</code>
      </pre>
    </div>
  );
}

/* Token helpers for terminal content — keep coloring tied to real semantics. */
export function Prompt({ children }: { children?: ReactNode }) {
  return <span className="text-accent select-none">{children ?? "$"} </span>;
}
export function Comment({ children }: { children: ReactNode }) {
  return <span className="text-mute italic">{children}</span>;
}
export function Out({ children }: { children: ReactNode }) {
  return <span className="text-risk-low">{children}</span>;
}
