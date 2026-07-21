"use client";

import { useEffect, useRef } from "react";

/**
 * Signature interactive background: a faint square grid with a soft amber glow
 * that follows the cursor. Sparse "hotspot" points across the grid each hold one
 * real, checkable fact about MRI or its domain; a "?" fades in on a hotspot only
 * as the glow approaches it (never on every cell), and dwelling on one floats its
 * fact as a tooltip — "facts over magic scores", made ambient and unobtrusive.
 *
 * Constraints: pointer-events:none + window-level mousemove (never blocks
 * content); decorative (aria-hidden); disabled on touch/no-hover and under
 * prefers-reduced-motion (static grid only); rAF parks when idle.
 */

const FACTS: readonly string[] = [
  "Hotspot = commits × (1 + √churn / 10).",
  "Bus factor = the fewest authors covering 80% of change.",
  "A knowledge island = one author, five or more commits, nobody else.",
  "Coupling instability: I = Ce / (Ca + Ce).",
  "God module: over 5,000 lines in one file.",
  "McCabe complexity over 10 flags a function for review.",
  "FIXME weighs 2.0; TODO weighs 1.0. Debt is measured, not vibed.",
  "AI authorship = git blame × session-commit correlation.",
  "Unattributed is not the same as human-written.",
  "Decision → consequence is correlation, never causation.",
  "ADR rationale scores 0.95 confidence; a bare commit subject, 0.3.",
  "Unmeasured analyzers are excluded from the score, never zeroed.",
  "Comprehension debt: code that runs but no one can safely change.",
  "OCaml declined a ~13,000-line AI PR — over provenance, not bugs.",
  "CloudBees 2026: ~81% more production issues from opaque AI code.",
  "Zero telemetry — proven by a build-failing egress test.",
  "Session content is off by default. Your prompts stay local.",
  "Every number links to the commit, line, or AST node behind it.",
];

const CELL = 56; // faint grid cell
const HOTSPOT_STEP = 7 * CELL; // one fact point per ~390px region — deliberately sparse
const REVEAL = 118; // distance at which a hotspot's "?" starts to appear
const HOVER = 46; // distance at which the fact tooltip triggers
const GLOW = 150; // cursor glow radius
const AMBER_FALLBACK = "244, 168, 71";

type Hotspot = { x: number; y: number; fact: string };

function hash(a: number, b: number): number {
  const h = Math.abs(Math.sin(a * 127.1 + b * 311.7) * 43758.5453);
  return Math.floor((h - Math.floor(h)) * 1000);
}

// "#rrggbb" -> "r, g, b" (for canvas rgba); tolerant of whitespace.
function hexToRgb(hex: string): string | null {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex.trim());
  if (!m) return null;
  return `${parseInt(m[1]!, 16)}, ${parseInt(m[2]!, 16)}, ${parseInt(m[3]!, 16)}`;
}

export function GridField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvasEl = canvasRef.current;
    const tipEl = tipRef.current;
    if (!canvasEl || !tipEl) return;
    const context = canvasEl.getContext("2d");
    if (!context) return;
    // Typed non-null consts so narrowing survives inside the closures below.
    const canvas: HTMLCanvasElement = canvasEl;
    const tip: HTMLDivElement = tipEl;
    const ctx: CanvasRenderingContext2D = context;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const hover = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

    let w = 0;
    let h = 0;
    let dpr = 1;
    let raf = 0;
    let mouseX = -9999;
    let mouseY = -9999;
    let lastMove = 0;
    let hotspots: Hotspot[] = [];

    // Colours read from the live theme so the grid, glow and "?" stay visible in
    // both dark and the light (vintage-paper) theme.
    let accent = AMBER_FALLBACK;
    let isLight = false;
    function readColors() {
      const cs = getComputedStyle(document.documentElement);
      accent = hexToRgb(cs.getPropertyValue("--color-accent")) ?? AMBER_FALLBACK;
      isLight = document.documentElement.getAttribute("data-theme") === "light";
    }

    function seedHotspots() {
      hotspots = [];
      const start = HOTSPOT_STEP / 2;
      for (let gx = start; gx < w; gx += HOTSPOT_STEP) {
        for (let gy = start; gy < h; gy += HOTSPOT_STEP) {
          // land each "?" in the CENTRE of a grid cell (not on an intersection),
          // with a small deterministic jitter across nearby cells.
          const jx = (hash(gx, gy) % 3) - 1;
          const jy = (hash(gx + 17, gy + 31) % 3) - 1;
          const col = Math.round(gx / CELL) + jx;
          const row = Math.round(gy / CELL) + jy;
          const x = (col + 0.5) * CELL;
          const y = (row + 0.5) * CELL;
          const fact = FACTS[hash(gx * 3, gy * 7) % FACTS.length] ?? FACTS[0]!;
          hotspots.push({ x, y, fact });
        }
      }
    }

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.font = "600 16px ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      seedHotspots();
      drawFrame();
    }

    function drawFrame() {
      ctx.clearRect(0, 0, w, h);
      const gridA = isLight ? 0.1 : 0.05;
      const glowA = isLight ? 0.12 : 0.09;
      const markA = isLight ? 0.95 : 0.72;

      // faint base grid
      ctx.strokeStyle = `rgba(${accent}, ${gridA})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let x = 0; x <= w; x += CELL) {
        ctx.moveTo(x + 0.5, 0);
        ctx.lineTo(x + 0.5, h);
      }
      for (let y = 0; y <= h; y += CELL) {
        ctx.moveTo(0, y + 0.5);
        ctx.lineTo(w, y + 0.5);
      }
      ctx.stroke();

      // soft glow following the cursor
      if (mouseX > -9000) {
        const g = ctx.createRadialGradient(mouseX, mouseY, 0, mouseX, mouseY, GLOW);
        g.addColorStop(0, `rgba(${accent}, ${glowA})`);
        g.addColorStop(1, `rgba(${accent}, 0)`);
        ctx.fillStyle = g;
        ctx.fillRect(mouseX - GLOW, mouseY - GLOW, GLOW * 2, GLOW * 2);
      }

      // "?" only at hotspots (cell-centred), revealed as the glow approaches
      for (const hs of hotspots) {
        const d = Math.hypot(hs.x - mouseX, hs.y - mouseY);
        if (d < REVEAL) {
          const a = (1 - d / REVEAL) * markA;
          ctx.fillStyle = `rgba(${accent}, ${a})`;
          ctx.fillText("?", hs.x, hs.y);
        }
      }
    }

    function loop() {
      drawFrame();
      // keep animating briefly after the last movement, then park
      if (performance.now() - lastMove < 140) {
        raf = requestAnimationFrame(loop);
      } else {
        raf = 0;
      }
    }
    function wake() {
      if (!raf) raf = requestAnimationFrame(loop);
    }

    let tipTimer = 0;
    function onMove(e: MouseEvent) {
      mouseX = e.clientX;
      mouseY = e.clientY;
      lastMove = performance.now();
      wake();

      // nearest hotspot within HOVER → show its fact after a short dwell
      let near: Hotspot | null = null;
      let best = HOVER;
      for (const hs of hotspots) {
        const d = Math.hypot(hs.x - mouseX, hs.y - mouseY);
        if (d < best) {
          best = d;
          near = hs;
        }
      }
      window.clearTimeout(tipTimer);
      if (!near) {
        tip.style.opacity = "0";
        return;
      }
      const target = near;
      tipTimer = window.setTimeout(() => {
        tip.textContent = target.fact;
        const tw = 260;
        let tx = target.x + 22;
        if (tx + tw > window.innerWidth - 12) tx = target.x - tw - 22;
        let ty = target.y + 16;
        if (ty + 80 > window.innerHeight - 12) ty = target.y - 64;
        tip.style.left = `${Math.max(12, tx)}px`;
        tip.style.top = `${Math.max(12, ty)}px`;
        tip.style.opacity = "1";
      }, 140);
    }

    function onLeave() {
      mouseX = -9999;
      mouseY = -9999;
      window.clearTimeout(tipTimer);
      tip.style.opacity = "0";
      wake();
    }

    readColors();
    resize();
    window.addEventListener("resize", resize);

    // Re-read theme colours + redraw when the theme toggles.
    const themeObserver = new MutationObserver(() => {
      readColors();
      drawFrame();
    });
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    if (reduce || !hover) {
      return () => {
        window.removeEventListener("resize", resize);
        themeObserver.disconnect();
      };
    }

    window.addEventListener("mousemove", onMove, { passive: true });
    document.addEventListener("mouseleave", onLeave);

    return () => {
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseleave", onLeave);
      themeObserver.disconnect();
      window.clearTimeout(tipTimer);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <>
      <canvas
        ref={canvasRef}
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 -z-10 h-full w-full"
      />
      <div
        ref={tipRef}
        aria-hidden="true"
        className="border-hairline-strong bg-surface text-secondary pointer-events-none fixed z-30 max-w-[260px] rounded-md border px-3 py-2 font-mono text-mono-sm leading-snug opacity-0 shadow-[var(--elevation-2)] transition-opacity duration-150"
        style={{ left: 0, top: 0 }}
      />
    </>
  );
}
