import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Container({
  children,
  narrow = false,
  className,
}: {
  children: ReactNode;
  narrow?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full px-4 sm:px-6",
        narrow
          ? "max-w-[var(--container-narrow)]"
          : "max-w-[var(--container-content)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Section({
  children,
  className,
  id,
}: {
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cn("py-16 md:py-24", className)}>
      {children}
    </section>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="text-accent font-mono text-mono-sm tracking-[0.14em] uppercase">
      <span className="text-mute">///</span> {children}
    </p>
  );
}

export function SectionHeader({
  eyebrow,
  title,
  lede,
  align = "left",
  className,
}: {
  eyebrow?: string;
  title: ReactNode;
  lede?: ReactNode;
  align?: "left" | "center";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3",
        align === "center" && "items-center text-center",
        className,
      )}
    >
      {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
      <h2 className="text-[length:var(--text-h2)] leading-[var(--text-h2--line-height)] font-semibold text-balance">
        {title}
      </h2>
      {lede && (
        <p
          className={cn(
            "text-secondary max-w-[62ch] font-body text-body-lg",
            align === "center" && "mx-auto",
          )}
        >
          {lede}
        </p>
      )}
    </div>
  );
}
