"use client";

import { useEffect, useRef } from "react";

/**
 * Signature interactive background: a square grid that reveals amber "?" glyphs
 * around the cursor as it moves, and — when the cursor dwells on a cell — floats
 * a tooltip with a real, inspectable fact about MRI or its problem domain
 * ("facts over magic scores", made ambient).
 *
 * Constraints honored:
 *  - `pointer-events: none` + window-level mousemove, so it NEVER blocks content.
 *  - Decorative: aria-hidden, keyboard-irrelevant.
 *  - Disabled on touch / no-hover devices and under prefers-reduced-motion
 *    (renders a single static faint grid, no reveal, no tooltip).
 *  - rAF runs only while there is activity, then parks.
 */

// Each fact is short, true, and checkable — sourced in the repo docs.
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

const CELL = 54;
const RADIUS = 130;
const AMBER = "244, 168, 71";

function hashCell(col: number, row: number): number {
  const h = Math.abs(Math.sin(col * 127.1 + row * 311.7) * 43758.5453);
  return Math.floor((h - Math.floor(h)) * FACTS.length);
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
    // Typed non-null consts so control-flow narrowing survives inside the
    // closures below (TS does not preserve guard narrowing across function
    // boundaries otherwise).
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
    // per-cell activation (keyed "col,row") with decaying intensity
    const active = new Map<string, number>();

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.font = "600 13px ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      // Resizing the bitmap implicitly clears it; redraw so the grid survives a
      // window/orientation resize even when the rAF loop is parked or absent
      // (reduced-motion / no-hover static path).
      drawBaseGrid();
    }

    function drawBaseGrid() {
      ctx.clearRect(0, 0, w, h);
      ctx.strokeStyle = `rgba(${AMBER}, 0.05)`;
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
    }

    function frame() {
      drawBaseGrid();
      // seed activation for cells near the cursor
      const c0 = Math.floor((mouseX - RADIUS) / CELL);
      const c1 = Math.floor((mouseX + RADIUS) / CELL);
      const r0 = Math.floor((mouseY - RADIUS) / CELL);
      const r1 = Math.floor((mouseY + RADIUS) / CELL);
      for (let col = c0; col <= c1; col++) {
        for (let row = r0; row <= r1; row++) {
          const cx = col * CELL + CELL / 2;
          const cy = row * CELL + CELL / 2;
          const d = Math.hypot(cx - mouseX, cy - mouseY);
          if (d < RADIUS) {
            const target = 1 - d / RADIUS;
            const key = `${col},${row}`;
            active.set(key, Math.max(active.get(key) ?? 0, target));
          }
        }
      }
      // draw + decay
      let anyAlive = false;
      for (const [key, val] of active) {
        const next = val - 0.02;
        if (next <= 0.01) {
          active.delete(key);
          continue;
        }
        anyAlive = true;
        active.set(key, next);
        const [colS, rowS] = key.split(",");
        const col = Number(colS);
        const row = Number(rowS);
        const cx = col * CELL + CELL / 2;
        const cy = row * CELL + CELL / 2;
        ctx.fillStyle = `rgba(${AMBER}, ${next * 0.55})`;
        ctx.fillText("?", cx, cy);
      }
      if (anyAlive || performance.now() - lastMove < 120) {
        raf = requestAnimationFrame(frame);
      } else {
        raf = 0;
      }
    }

    function wake() {
      if (!raf) raf = requestAnimationFrame(frame);
    }

    let tipTimer = 0;
    function onMove(e: MouseEvent) {
      mouseX = e.clientX;
      mouseY = e.clientY;
      lastMove = performance.now();
      wake();
      // dwell → fact tooltip
      window.clearTimeout(tipTimer);
      tip.style.opacity = "0";
      tipTimer = window.setTimeout(() => {
        const col = Math.floor(mouseX / CELL);
        const row = Math.floor(mouseY / CELL);
        const fact = FACTS[hashCell(col, row)] ?? FACTS[0]!;
        tip.textContent = fact;
        const tw = 260;
        let tx = mouseX + 18;
        if (tx + tw > window.innerWidth - 12) tx = mouseX - tw - 18;
        let ty = mouseY + 18;
        if (ty + 80 > window.innerHeight - 12) ty = mouseY - 64;
        tip.style.left = `${Math.max(12, tx)}px`;
        tip.style.top = `${Math.max(12, ty)}px`;
        tip.style.opacity = "1";
      }, 260);
    }

    function onLeave() {
      mouseX = -9999;
      mouseY = -9999;
      window.clearTimeout(tipTimer);
      tip.style.opacity = "0";
    }

    resize();
    window.addEventListener("resize", resize);

    if (reduce || !hover) {
      drawBaseGrid();
      return () => window.removeEventListener("resize", resize);
    }

    window.addEventListener("mousemove", onMove, { passive: true });
    document.addEventListener("mouseleave", onLeave);
    drawBaseGrid();

    return () => {
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseleave", onLeave);
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
