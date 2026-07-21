/**
 * PROJECT MRI — Index entry
 * Wires all shared modules and triggers page-specific init.
 */

import './chrome.js';
import './terminal.js';
import './demos.js';

function pageInit(): void {
  const body = document.body;
  const route = body.dataset.route || '/';

  // Render the architecture graph on any page that has the canvas.
  const archCanvas = document.getElementById('arch-canvas') as HTMLCanvasElement | null;
  if (archCanvas) {
    // Re-render on resize
    let resizeRaf: number | null = null;
    const resize = () => {
      if (resizeRaf !== null) cancelAnimationFrame(resizeRaf);
      resizeRaf = requestAnimationFrame(() => {
        const mod = require_demos();
        if (mod) mod.renderArchitectureGraph(archCanvas);
      });
    };
    window.addEventListener('resize', resize);
    resize();
  }

  // File-tree simulator
  const treeHost = document.getElementById('demo-tree');
  if (treeHost) {
    const mod = require_demos();
    if (mod) mod.mountFileTreeSimulator(treeHost);
  }

  // Demo feed (live event stream)
  const feedHost = document.getElementById('demo-feed');
  if (feedHost) {
    // Already wired in terminal.ts via .demo-feed selector
  }

  // Set hero quickstats count-up targets if needed
  document.querySelectorAll<HTMLElement>('[data-count-target]').forEach((el) => {
    const target = parseInt(el.dataset.countTarget || '0', 10);
    const duration = parseInt(el.dataset.duration || '1500', 10);
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = Math.round(target * eased).toLocaleString();
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });

  // Highlight active section in TOC (scrollspy)
  const tocLinks = Array.from(document.querySelectorAll<HTMLAnchorElement>('.toc a[href^="#"]'));
  if (tocLinks.length > 0) {
    const sections = tocLinks
      .map((a) => document.getElementById(a.getAttribute('href')!.slice(1)))
      .filter((x): x is HTMLElement => x !== null);

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const id = '#' + entry.target.id;
            tocLinks.forEach((a) => {
              if (a.getAttribute('href') === id) {
                a.style.color = 'var(--accent)';
                a.style.fontWeight = '700';
              } else {
                a.style.color = '';
                a.style.fontWeight = '';
              }
            });
          }
        }
      },
      { rootMargin: '-30% 0px -60% 0px' },
    );
    sections.forEach((s) => observer.observe(s));
  }

  // Mark unused param route so TS doesn't complain about it being set
  void route;

  // ----------------------------------------------------------------
  // /demo page logic — wires up run-demo / load-sample buttons + render
  // ----------------------------------------------------------------
  if (route === '/demo') {
    void initDemoPage();
  }
}

// ============================================================================
// /demo page
// ============================================================================

interface DemoScore { label: string; value: number; band: string; contributors: string[]; }
interface DemoFinding { severity: string; category: string; title: string; description: string; target_path: string; target_symbol: string; score: number | null; data: Record<string, unknown>; }
interface DemoReport { project: { path: string; name: string; default_branch: string }; stats: { file_count: number; loc_total: number; commit_count: number; languages: Record<string, { files: number; loc: number }>; finding_counts: Record<string, number> }; overall_health: number; overall_band: string; scores: DemoScore[]; findings: DemoFinding[]; composition: string[]; }

const DEMO_BACKEND_BASE = (() => {
  const w = window as unknown as { MRI_BACKEND?: string };
  if (w.MRI_BACKEND) return w.MRI_BACKEND.replace(/\/$/, '');
  return `${window.location.protocol}//${window.location.hostname || 'localhost'}:7331`;
})();

function escapeHtml(s: unknown): string {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c as string] || c));
}

async function demoCheckApi(): Promise<boolean> {
  const statusLine = document.querySelector<HTMLElement>('#status-line');
  if (!statusLine) return false;
  statusLine.innerHTML = '<span class="spinner"></span> checking backend…';
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 2000);
    const res = await fetch(`${DEMO_BACKEND_BASE}/api/health`, { mode: 'cors', signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    statusLine.innerHTML = `<span style="color:var(--ok)">●</span> live · v${data.version}`;
    return true;
  } catch {
    statusLine.innerHTML = '<span style="color:var(--warn)">●</span> backend unreachable — click "load sample" for embedded data';
    return false;
  }
}

function renderDemoReport(r: DemoReport): void {
  const section = document.querySelector<HTMLElement>('#report-section');
  if (!section) return;
  section.style.display = 'block';
  const setText = (sel: string, t: string) => { const el = document.querySelector(sel); if (el) el.textContent = t; };
  setText('#r-project-name', r.project.name);
  setText('#r-project-meta', `${r.project.path} · branch ${r.project.default_branch} · ${r.stats.file_count} files · ${r.stats.loc_total.toLocaleString()} LOC · ${r.stats.commit_count} commits`);
  setText('#r-overall', r.overall_health.toFixed(1));
  setText('#r-band', `overall · ${r.overall_band}`);
  setText('#r-finding-count', String(r.findings.length));

  const compEl = document.querySelector('#r-composition');
  if (compEl) compEl.innerHTML = r.composition.map(c => `<div style="padding:4px 0; color:var(--text-secondary); font-size:13px;">${escapeHtml(c)}</div>`).join('');

  const scoresEl = document.querySelector('#r-scores');
  if (scoresEl) scoresEl.innerHTML = r.scores.map(s => {
    const color = s.band === 'critical' || s.band === 'poor' ? 'var(--alert)'
      : s.band === 'excellent' ? 'var(--ok)'
      : 'var(--accent)';
    return `<div class="score">
      <div class="score__label">${escapeHtml(s.label.replace(/_/g, ' '))}</div>
      <div class="score__val">${s.value.toFixed(1)}</div>
      <div style="font-size:10px; letter-spacing:0.18em; text-transform:uppercase; margin-top:4px; color:${color};">${s.band}</div>
      <div class="score__bar"><div class="score__bar-fill" style="width:${s.value}%"></div></div>
      <div class="score__contrib">${s.contributors.map(c => `<div>${escapeHtml(c)}</div>`).join('')}</div>
    </div>`;
  }).join('');

  const findingsEl = document.querySelector('#r-findings');
  if (findingsEl) findingsEl.innerHTML = r.findings.slice(0, 50).map(f => `
    <div class="finding finding--${f.severity}">
      <div class="finding__sev">${f.severity}${f.score != null ? ' · ' + Math.round(f.score) : ''}</div>
      <div>
        <div class="finding__title">${escapeHtml(f.title)}</div>
        ${f.description ? `<div class="finding__desc">${escapeHtml(f.description)}</div>` : ''}
        ${f.target_path ? `<div class="finding__path">${escapeHtml(f.target_path)}${f.target_symbol ? ' :: ' + escapeHtml(f.target_symbol) : ''}</div>` : ''}
      </div>
    </div>
  `).join('');

  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function demoLoadReport(slug: string): Promise<void> {
  const statusLine = document.querySelector<HTMLElement>('#status-line');
  const btn = document.querySelector<HTMLButtonElement>('#btn-demo');
  if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> fetching report…'; }
  const file = slug === 'clean-typescript-lib' ? '/data/demo-clean.json' : '/data/demo-legacy.json';
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 3000);
    const res = await fetch(`${DEMO_BACKEND_BASE}/api/demo/scan?slug=${encodeURIComponent(slug)}`, { mode: 'cors', signal: ctrl.signal });
    clearTimeout(t);
    if (!res.ok) throw new Error('backend ' + res.status);
    const report = await res.json();
    renderDemoReport(report as DemoReport);
    if (statusLine) statusLine.innerHTML = '<span style="color:var(--ok)">●</span> live · report fetched from backend';
  } catch {
    try {
      const res = await fetch(file);
      if (!res.ok) throw new Error('fallback ' + res.status);
      const report = await res.json();
      renderDemoReport(report as DemoReport);
      if (statusLine) statusLine.innerHTML = '<span style="color:var(--warn)">●</span> sample loaded from bundled JSON · run <code style="color:var(--accent)">mri serve</code> for live data';
    } catch (e) {
      if (statusLine) statusLine.innerHTML = `<span style="color:var(--alert)">✗</span> ${(e as Error).message}`;
    }
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = '▶ run demo scan'; }
  }
}

function initDemoPage(): void {
  const btnDemo = document.querySelector('#btn-demo');
  const btnSample = document.querySelector('#btn-sample');
  if (btnDemo) btnDemo.addEventListener('click', () => demoLoadReport('my-legacy-app'));
  if (btnSample) btnSample.addEventListener('click', () => demoLoadReport('clean-typescript-lib'));
  void demoCheckApi();
}

// Helper to dynamically grab demos module (already loaded via <script type="module">)
declare global {
  interface Window {
    __mri_demos?: typeof import('./demos.js');
  }
}
function require_demos(): typeof import('./demos.js') | null {
  return window.__mri_demos ?? null;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', pageInit);
} else {
  pageInit();
}

// SPA re-mount hook — reinitialize page-specific JS after navigation
document.addEventListener('mri:remount', () => pageInit());

// Expose demos module globally for the dynamic require helper.
import * as demosMod from './demos.js';
window.__mri_demos = demosMod;