"use client";

import { Link } from "@/components/link";
import { usePathname } from "next/navigation";
import { useCallbackRef } from "@/lib/use-callback-ref";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { SITE, NAV_LINKS } from "@/lib/site";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { GitHubIcon, MenuIcon, CloseIcon } from "@/components/icons";

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const close = useCallbackRef(() => setOpen(false));

  // Close the drawer on route change.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Drawer open: lock scroll, trap focus, Escape closes, background inert.
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const drawer = drawerRef.current;
    document.body.style.overflow = "hidden";
    // Make everything behind the drawer inert — including the header, whose
    // toggle/GitHub/hamburger controls stay visible at tablet widths and would
    // otherwise be reachable by a screen-reader virtual cursor while the modal
    // drawer is open (the Tab-trap alone doesn't cover non-Tab AT navigation).
    const inertTargets = [
      document.getElementById("main-content"),
      document.getElementById("site-footer"),
      document.getElementById("site-header"),
    ];
    inertTargets.forEach((el) => el?.setAttribute("inert", ""));
    drawer?.querySelector<HTMLElement>("a, button")?.focus();

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        close();
        return;
      }
      if (e.key !== "Tab" || !drawer) return;
      const focusable = drawer.querySelectorAll<HTMLElement>("a[href], button:not([disabled])");
      if (focusable.length === 0) return;
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      inertTargets.forEach((el) => el?.removeAttribute("inert"));
      (previous ?? triggerRef.current)?.focus();
    };
  }, [open, close]);

  return (
    <>
    <header id="site-header" className="border-hairline bg-void/80 sticky top-0 z-40 border-b backdrop-blur-md">
      <nav
        aria-label="Primary"
        className="mx-auto flex h-[var(--nav-h)] max-w-[var(--container-content)] items-center gap-6 px-4 sm:px-6"
      >
        <Link href="/" aria-label="MRI — home" className="shrink-0">
          <Logo />
        </Link>

        {/* Desktop links */}
        <ul className="ml-2 hidden items-center gap-1 md:flex">
          {NAV_LINKS.map((l) => {
            const active = isActive(pathname, l.href);
            return (
              <li key={l.href}>
                <Link
                  href={l.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "font-sans text-body-sm rounded-sm px-3 py-2 transition-colors",
                    active
                      ? "text-primary"
                      : "text-secondary hover:text-primary",
                  )}
                >
                  {l.label}
                </Link>
              </li>
            );
          })}
        </ul>

        <div className="ml-auto flex items-center gap-1">
          <a
            href={SITE.github}
            target="_blank"
            rel="noopener noreferrer"
            className="text-secondary hover:text-primary hover:border-hairline-strong hidden h-9 items-center gap-2 rounded-sm border border-transparent px-3 font-sans text-body-sm transition-colors sm:inline-flex"
          >
            <GitHubIcon width={18} height={18} />
            <span className="hidden lg:inline">GitHub</span>
          </a>
          <ThemeToggle />
          <button
            ref={triggerRef}
            type="button"
            className="text-secondary hover:text-primary grid h-9 w-9 place-items-center rounded-sm md:hidden"
            aria-label="Open menu"
            aria-expanded={open}
            aria-controls="mobile-drawer"
            onClick={() => setOpen(true)}
          >
            <MenuIcon />
          </button>
        </div>
      </nav>
    </header>

      {/* Mobile drawer — rendered OUTSIDE <header> so its `fixed` positioning is
          viewport-relative (a backdrop-filter ancestor would otherwise become
          its containing block and break full-screen coverage). */}
      {open && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="Close menu"
            tabIndex={-1}
            className="bg-void/70 absolute inset-0 backdrop-blur-sm"
            onClick={close}
          />
          <div
            ref={drawerRef}
            id="mobile-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Site menu"
            className="bg-surface border-hairline absolute inset-y-0 right-0 flex w-[min(20rem,85vw)] flex-col border-l p-6"
          >
            <div className="flex items-center justify-between">
              <Logo />
              <button
                type="button"
                className="text-secondary hover:text-primary grid h-9 w-9 place-items-center rounded-sm"
                aria-label="Close menu"
                onClick={close}
              >
                <CloseIcon />
              </button>
            </div>
            <ul className="mt-8 flex flex-col gap-1">
              {NAV_LINKS.map((l) => {
                const active = isActive(pathname, l.href);
                return (
                  <li key={l.href}>
                    <Link
                      href={l.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "block rounded-sm px-3 py-3 font-sans text-body transition-colors",
                        active
                          ? "text-primary bg-[var(--accent-wash)]"
                          : "text-secondary hover:text-primary",
                      )}
                    >
                      {l.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
            <a
              href={SITE.github}
              target="_blank"
              rel="noopener noreferrer"
              className="text-secondary hover:text-primary border-hairline mt-auto inline-flex items-center gap-2 rounded-sm border px-3 py-3 font-sans text-body-sm"
            >
              <GitHubIcon width={18} height={18} />
              GitHub
            </a>
          </div>
        </div>
      )}
    </>
  );
}
