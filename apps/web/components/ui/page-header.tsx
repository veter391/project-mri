import type { ReactNode } from "react";
import { Container } from "@/components/ui/container";

export function PageHeader({
  eyebrow,
  title,
  lede,
}: {
  eyebrow: string;
  title: ReactNode;
  lede?: ReactNode;
}) {
  return (
    <header className="border-hairline relative overflow-hidden border-b">
      {/* faint readout grid on the header only */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.4]"
        style={{
          backgroundImage:
            "linear-gradient(var(--color-hairline) 1px, transparent 1px), linear-gradient(90deg, var(--color-hairline) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage:
            "radial-gradient(120% 100% at 15% 0%, black, transparent 70%)",
          WebkitMaskImage:
            "radial-gradient(120% 100% at 15% 0%, black, transparent 70%)",
        }}
      />
      <Container className="relative py-14 md:py-20">
        <p className="font-mono text-mono-sm">
          <span className="text-mute">~/</span>
          <span className="text-accent">mri</span>
          <span className="text-mute"> · </span>
          <span className="text-secondary tracking-[0.1em] uppercase">
            {eyebrow}
          </span>
          <span className="mri-caret ml-2 opacity-70" />
        </p>
        <h1 className="mt-5 max-w-[22ch] text-[length:var(--text-h1)] leading-[var(--text-h1--line-height)] font-semibold text-balance">
          {title}
        </h1>
        {lede && (
          <p className="text-secondary mt-5 max-w-[68ch] font-body text-body-lg text-pretty">
            {lede}
          </p>
        )}
      </Container>
    </header>
  );
}
