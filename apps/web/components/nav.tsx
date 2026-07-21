"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const GITHUB = "https://github.com/veter391/project-mri";

const LINKS = [
  { href: "/", label: "~ /" },
  { href: "/features", label: "~ /features" },
  { href: "/architecture", label: "~ /architecture" },
  { href: "/comparison", label: "~ /comparison" },
  { href: "/install", label: "~ /install" },
  { href: "/self-host", label: "~ /self-host" },
  { href: "/manifesto", label: "~ /manifesto" },
  { href: "/roadmap", label: "~ /roadmap" },
  { href: "/about", label: "~ /about" },
];

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <nav
      className="sticky top-0 z-50 border-b border-line bg-void/90 backdrop-blur"
      aria-label="Primary"
    >
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
        <Link href="/" className="flex items-center gap-2 font-bold" aria-label="project-mri — home">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5 text-accent" aria-hidden="true">
            <circle cx="12" cy="12" r="9" />
            <circle cx="12" cy="12" r="3" />
            <path d="M12 1v3M12 20v3M1 12h3M20 12h3" />
          </svg>
          project-mri
        </Link>

        <div className="hidden items-center gap-5 text-[13px] md:flex">
          {LINKS.slice(1).map((l) => {
            const active = pathname === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={active ? "text-accent" : "text-mute transition-colors hover:text-ink"}
              >
                {l.label}
              </Link>
            );
          })}
          <a href={GITHUB} className="text-mute transition-colors hover:text-accent">
            github ↗
          </a>
        </div>

        <button
          type="button"
          className="text-mute md:hidden"
          aria-label="Toggle navigation menu"
          aria-expanded={open}
          aria-controls="mobile-nav"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "✕" : "≡"}
        </button>
      </div>

      {open && (
        <div id="mobile-nav" className="flex flex-col border-t border-line bg-raised md:hidden">
          {LINKS.slice(1).map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              aria-current={pathname === l.href ? "page" : undefined}
              className="border-b border-line px-6 py-3 text-sm text-secondary hover:text-accent"
            >
              {l.label}
            </Link>
          ))}
          <a href={GITHUB} className="px-6 py-3 text-sm text-secondary hover:text-accent">
            github ↗
          </a>
        </div>
      )}
    </nav>
  );
}
