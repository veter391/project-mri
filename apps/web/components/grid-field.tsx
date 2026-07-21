"use client";

import { useEffect, useRef } from "react";

/**
 * Signature interactive background: a faint square grid that comes alive under
 * the cursor. Grid intersections inside a lens radius bloom into amber dots and
 * are pushed gently outward — a subtle magnifying-lens / wave distortion that
 * tracks the pointer. Sparse "hotspot" points each carry one real, checkable
 * fact that surfaces as a tooltip on dwell.
 *
 * Optimized: the static grid is rendered once into an offscreen canvas and
 * blitted each frame; only the bounded region around the cursor is computed
 * per frame, and the rAF loop parks when idle.
 *
 * Constraints: pointer-events:none + window-level mousemove (never blocks
 * content); decorative (aria-hidden); disabled on touch/no-hover and under
 * prefers-reduced-motion (static grid only).
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

const CELL = 56;
const HOTSPOT_STEP = 7 * CELL; // deliberately sparse fact points
const REVEAL = 120; // "?" reveal distance
const HOVER = 46; // fact-tooltip trigger distance
const LENS = 165; // lens / glow radius
const PUSH = 15; // max outward lens displacement (px)
const AMBER_FALLBACK = "244, 168, 71";

type Hotspot = { x: number; y: number; fact: string };

function hash(a: number, b: number): number {
  const h = Math.abs(Math.sin(a * 127.1 + b * 311.7) * 43758.5453);
  return Math.floor((h - Math.floor(h)) * 1000);
}

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
    const canvas: HTMLCanvasElement = canvasEl;
    const tip: HTMLDivElement = tipEl;
    const ctx: CanvasRenderingContext2D = context;

    // Offscreen static-grid layer, blitted each frame.
    const base: HTMLCanvasElement = document.createElement("canvas");
    const baseCtx = base.getContext("2d");
    if (!baseCtx) return;
    const bctx: CanvasRenderingContext2D = baseCtx;

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

    // Render the faint static grid + resting dots into the offscreen layer.
    function drawBase() {
      base.width = Math.floor(w * dpr);
      base.height = Math.floor(h * dpr);
      bctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      bctx.clearRect(0, 0, w, h);
      const lineA = isLight ? 0.1 : 0.06;
      const dotA = isLight ? 0.17 : 0.11;
      bctx.strokeStyle = `rgba(${accent}, ${lineA})`;
      bctx.lineWidth = 1;
      bctx.beginPath();
      for (let x = 0; x <= w; x += CELL) {
        bctx.moveTo(x + 0.5, 0);
        bctx.lineTo(x + 0.5, h);
      }
      for (let y = 0; y <= h; y += CELL) {
        bctx.moveTo(0, y + 0.5);
        bctx.lineTo(w, y + 0.5);
      }
      bctx.stroke();
      bctx.fillStyle = `rgba(${accent}, ${dotA})`;
      for (let x = 0; x <= w; x += CELL) {
        for (let y = 0; y <= h; y += CELL) {
          bctx.fillRect(x - 0.9, y - 0.9, 1.8, 1.8);
        }
      }
    }

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      ctx.font = "600 16px ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      drawBase();
      seedHotspots();
      drawFrame();
    }

    function drawFrame() {
      // blit static base (identity transform), then draw dynamic overlay scaled
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(base, 0, 0);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      if (mouseX > -9000) {
        // soft glow
        const g = ctx.createRadialGradient(mouseX, mouseY, 0, mouseX, mouseY, LENS);
        g.addColorStop(0, `rgba(${accent}, ${isLight ? 0.12 : 0.09})`);
        g.addColorStop(1, `rgba(${accent}, 0)`);
        ctx.fillStyle = g;
        ctx.fillRect(mouseX - LENS, mouseY - LENS, LENS * 2, LENS * 2);

        // lens: grid intersections bloom + push outward near the cursor
        const c0 = Math.floor((mouseX - LENS) / CELL);
        const c1 = Math.ceil((mouseX + LENS) / CELL);
        const r0 = Math.floor((mouseY - LENS) / CELL);
        const r1 = Math.ceil((mouseY + LENS) / CELL);
        const peak = isLight ? 0.95 : 0.8;
        for (let col = c0; col <= c1; col++) {
          for (let row = r0; row <= r1; row++) {
            const ix = col * CELL;
            const iy = row * CELL;
            const dx = ix - mouseX;
            const dy = iy - mouseY;
            const d = Math.hypot(dx, dy);
            if (d >= LENS) continue;
            const t = 1 - d / LENS; // closeness 0..1
            const ease = t * t; // concentrated push
            const push = ease * PUSH;
            const nx = d > 0.001 ? dx / d : 0;
            const ny = d > 0.001 ? dy / d : 0;
            const px = ix + nx * push;
            const py = iy + ny * push;
            const rad = 1 + t * 4; // grows toward the cursor
            const alpha = Math.pow(t, 1.15) * peak; // broader glow of lit dots
            ctx.fillStyle = `rgba(${accent}, ${alpha})`;
            ctx.beginPath();
            ctx.arc(px, py, rad, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }

      // "?" only at hotspots (cell-centred), revealed as the lens approaches
      for (const hs of hotspots) {
        const d = Math.hypot(hs.x - mouseX, hs.y - mouseY);
        if (d < REVEAL) {
          const a = (1 - d / REVEAL) * (isLight ? 0.95 : 0.72);
          ctx.fillStyle = `rgba(${accent}, ${a})`;
          ctx.fillText("?", hs.x, hs.y);
        }
      }
    }

    function loop() {
      drawFrame();
      if (performance.now() - lastMove < 160) {
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

    const themeObserver = new MutationObserver(() => {
      readColors();
      drawBase();
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
