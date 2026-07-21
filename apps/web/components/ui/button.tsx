import type { ComponentProps, ReactNode } from "react";
import { Link } from "@/components/link";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost";
type Size = "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  // Primary: amber fill, void text (both themes verified AA on the accent value).
  primary:
    "bg-accent text-void hover:bg-accent-dim border border-transparent",
  secondary:
    "border border-hairline-strong text-primary hover:bg-raised",
  ghost: "text-secondary hover:text-primary border border-transparent",
};

const SIZES: Record<Size, string> = {
  md: "h-9 px-4 text-body-sm",
  lg: "h-11 px-5 text-body",
};

const baseClass =
  "inline-flex items-center justify-center gap-2 rounded-sm font-sans font-medium transition-colors duration-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]";

function classesFor(variant: Variant, size: Size, className?: string) {
  return cn(baseClass, VARIANTS[variant], SIZES[size], className);
}

type CommonProps = {
  children: ReactNode;
  variant?: Variant;
  size?: Size;
  className?: string;
};

/** Internal navigation button (Next Link). */
export function ButtonLink({
  href,
  variant = "primary",
  size = "md",
  className,
  children,
  ...rest
}: CommonProps & { href: string } & Omit<ComponentProps<typeof Link>, "href" | "className">) {
  const external = href.startsWith("http");
  if (external) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={classesFor(variant, size, className)}
      >
        {children}
      </a>
    );
  }
  return (
    <Link href={href} className={classesFor(variant, size, className)} {...rest}>
      {children}
    </Link>
  );
}

/** Action button (non-navigation). */
export function Button({
  variant = "primary",
  size = "md",
  className,
  children,
  ...rest
}: CommonProps & Omit<ComponentProps<"button">, "className">) {
  return (
    <button className={classesFor(variant, size, className)} {...rest}>
      {children}
    </button>
  );
}
