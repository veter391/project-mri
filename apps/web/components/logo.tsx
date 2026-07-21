import { cn } from "@/lib/cn";

// "Scan Line Monogram" (BRANDING §7.1): a geometric M of three vertical bars,
// crossed by a single horizontal amber scan line at ~1/3 height — the one
// sanctioned amber gradient in the brand, reserved to this mark. Bars render in
// currentColor so the mark works in both themes; the scan line stays amber.
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={cn("h-6 w-6", className)}
      role="img"
      aria-label="MRI"
    >
      <defs>
        <linearGradient id="mri-scan" x1="0" x2="24" y1="0" y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#F4A847" stopOpacity="0" />
          <stop offset="0.5" stopColor="#F4A847" />
          <stop offset="1" stopColor="#F4A847" stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* three vertical bars */}
      <g fill="currentColor">
        <rect x="3" y="4" width="3.2" height="16" rx="1" />
        <rect x="10.4" y="4" width="3.2" height="16" rx="1" />
        <rect x="17.8" y="4" width="3.2" height="16" rx="1" />
      </g>
      {/* horizontal scan line at ~1/3 height */}
      <rect x="1" y="10.4" width="22" height="1.8" rx="0.9" fill="url(#mri-scan)" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "font-sans text-[1.05rem] font-semibold tracking-[-0.01em] text-primary",
        className,
      )}
    >
      MRI
    </span>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark />
      <Wordmark />
    </span>
  );
}
