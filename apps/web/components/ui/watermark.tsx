import { cn } from "@/lib/cn";

/**
 * Ghost numeral watermark behind a section. Rendered as SVG text: purely
 * decorative, sized by the parent, and outside the scope of HTML text-contrast
 * rules (it is intentionally near-invisible — 5% opacity chrome, not content).
 */
export function Watermark({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 240 170"
      className={cn(
        "text-primary pointer-events-none absolute select-none",
        className,
      )}
      fill="currentColor"
      opacity={0.05}
    >
      <text
        x="240"
        y="150"
        textAnchor="end"
        fontFamily="var(--font-mono), monospace"
        fontWeight={700}
        fontSize="170"
      >
        {text}
      </text>
    </svg>
  );
}
