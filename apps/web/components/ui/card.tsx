import type { ReactNode } from "react";
import { Link } from "@/components/link";
import { cn } from "@/lib/cn";
import { ArrowUpRightIcon } from "@/components/icons";

/**
 * Bento card — the base surface for asymmetric grid composition
 * (DESIGN-SYSTEM §4.2: no three-equal-cards). Column span is set by the caller
 * via className (e.g. `md:col-span-8`), driven by information density.
 */
export function Card({
  children,
  className,
  interactive = false,
}: {
  children: ReactNode;
  className?: string;
  interactive?: boolean;
}) {
  return (
    <div
      className={cn(
        "border-hairline bg-surface rounded-md border p-6",
        interactive &&
          "transition-shadow duration-100 hover:shadow-[var(--elevation-2)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** A card that is entirely a link (whole surface clickable). */
export function LinkCard({
  href,
  title,
  children,
  className,
}: {
  href: string;
  title: string;
  children?: ReactNode;
  className?: string;
}) {
  const external = href.startsWith("http");
  const inner = (
    <>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-accent font-sans text-body font-semibold">
          {title}
        </h3>
        <ArrowUpRightIcon
          width={16}
          height={16}
          className="text-mute transition-transform duration-100 group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
        />
      </div>
      {children && (
        <p className="text-secondary mt-2 font-body text-body-sm leading-relaxed">
          {children}
        </p>
      )}
    </>
  );
  const cls = cn(
    "group border-hairline bg-surface hover:border-hairline-strong block rounded-md border p-5 transition-colors",
    className,
  );
  return external ? (
    <a href={href} target="_blank" rel="noopener noreferrer" className={cls}>
      {inner}
    </a>
  ) : (
    <Link href={href} className={cls}>
      {inner}
    </Link>
  );
}
