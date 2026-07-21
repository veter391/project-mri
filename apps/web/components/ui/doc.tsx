import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/** Prose helpers for docs pages — Outfit body, mono for code (DESIGN-SYSTEM §3.1). */

export function DocH2({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2
      id={id}
      className="mt-12 scroll-mt-24 text-[length:var(--text-h3)] font-semibold first:mt-0"
    >
      {children}
    </h2>
  );
}

export function DocP({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cn("text-secondary mt-4 font-body text-body-lg leading-relaxed", className)}>
      {children}
    </p>
  );
}

export function DocList({ children }: { children: ReactNode }) {
  return <ul className="mt-4 flex flex-col gap-2">{children}</ul>;
}

export function DocLi({ children }: { children: ReactNode }) {
  return (
    <li className="text-secondary flex gap-3 font-body text-body leading-relaxed">
      <span className="text-accent mt-1 font-mono text-mono-sm">→</span>
      <span>{children}</span>
    </li>
  );
}

export function IC({ children }: { children: ReactNode }) {
  return (
    <code className="bg-inset text-primary rounded-[3px] px-1.5 py-0.5 font-mono text-[0.9em]">
      {children}
    </code>
  );
}

export function DocNote({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: "info" | "warn";
}) {
  return (
    <div
      className={cn(
        "mt-6 rounded-md border p-4 font-body text-body-sm leading-relaxed",
        tone === "warn"
          ? "border-[color-mix(in_srgb,var(--color-risk-critical)_40%,transparent)] bg-[color-mix(in_srgb,var(--color-risk-critical)_7%,transparent)] text-secondary"
          : "border-hairline-strong bg-surface text-secondary",
      )}
    >
      {children}
    </div>
  );
}
