"use client";

import { useEffect, useState } from "react";
import { SunIcon, MoonIcon } from "@/components/icons";

type Theme = "dark" | "light";

// Dark is the unconditional default (see globals.css). This toggle only ever
// stamps an explicit choice onto <html data-theme> and persists it. No inline
// head script is used, so the strict CSP needs no script hash — the tradeoff is
// a one-frame flip for a returning light-mode visitor, acceptable for a
// dark-native brand where dark is also the correct default paint.
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("mri-theme") as Theme | null;
    if (stored === "light") {
      document.documentElement.setAttribute("data-theme", "light");
      setTheme("light");
    }
    setMounted(true);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("mri-theme", next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className="text-secondary hover:text-primary hover:border-hairline-strong grid h-9 w-9 place-items-center rounded-sm border border-transparent transition-colors"
      aria-label={
        mounted
          ? `Switch to ${theme === "dark" ? "light" : "dark"} theme`
          : "Toggle theme"
      }
    >
      {theme === "dark" ? (
        <SunIcon width={18} height={18} />
      ) : (
        <MoonIcon width={18} height={18} />
      )}
    </button>
  );
}
