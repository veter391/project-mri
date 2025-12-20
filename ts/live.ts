// ============================================================================
// live.ts — backend integration (real scan / WebSocket progress / report)
// ============================================================================

const BACKEND_BASE = (() => {
  // Allow override via window.MRI_BACKEND for local dev.
  const w = window as unknown as { MRI_BACKEND?: string };
  if (w.MRI_BACKEND) return w.MRI_BACKEND.replace(/\/$/, '');
  // Default: same host as the page, port 7331
  const host = window.location.hostname || 'localhost';
  return `http://${host}:7331`;
})();

export interface Score {
  label: string;
  value: number;
  band: 'excellent' | 'good' | 'fair' | 'poor' | 'critical';
  contributors: string[];
}

export interface Finding {
  severity: 'info' | 'low' | 'medium' | 'high' | 'critical';
  category: string;
  title: string;
  description: string;
  target_path: string;
  target_symbol: string;
  score: number | null;
  data: Record<string, unknown>;
}

export interface AnalyzerRun {
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  duration_ms: number | null;
  score: Score | null;
  signals: Record<string, unknown>;
  findings: Finding[];
  error_message: string;
}

export interface Report {
  scan_uuid: string;
  project: { path: string; name: string; default_branch: string };
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  scores: Score[];
  overall_health: number;
  overall_band: string;
  runs: AnalyzerRun[];
  findings: Finding[];
  stats: {
    file_count: number;
    loc_total: number;
    commit_count: number;
    languages: Record<string, { files: number; loc: number }>;
    finding_counts: Record<string, number>;
  };
  composition: string[];
}

export interface ScanStatus {
  scan_uuid: string;
  project_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  report?: Report;
  summary?: {
    overall_health: number;
    file_count: number;
    loc_total: number;
    commit_count: number;
    finding_counts: Record<string, number>;
    duration_ms: number | null;
  };
}

// ----------------------------------------------------------------------------
// API helpers
// ----------------------------------------------------------------------------

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  // Bound every request to 10s — better to fail fast than hang the UI.
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 10_000);
  try {
    const res = await fetch(`${BACKEND_BASE}${path}`, {
      ...init,
      signal: init?.signal ?? ctrl.signal,
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`${res.status} ${res.statusText} — ${text.slice(0, 200)}`);
    }
    return res.json();
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchDemoReport(slug = 'my-legacy-app'): Promise<Report> {
  return jsonFetch<Report>(`/api/demo/scan?slug=${encodeURIComponent(slug)}`);
}

export async function startScan(projectPath: string, branch?: string): Promise<{ scan_uuid: string; project_name: string }> {
  return jsonFetch('/api/scans', {
    method: 'POST',
    body: JSON.stringify({ project_path: projectPath, branch: branch || null }),
  });
}

export async function pollScan(scanUuid: string): Promise<ScanStatus> {
  return jsonFetch<ScanStatus>(`/api/scans/${scanUuid}`);
}

// WebSocket progress stream
export interface ProgressEvent {
  type: 'hello' | 'progress' | 'done' | 'error' | 'ping';
  phase?: string;
  detail?: string;
  percent?: number;
  message?: string;
  scan_uuid?: string;
  overall_health?: number;
}

export function subscribeProgress(
  scanUuid: string,
  onEvent: (msg: ProgressEvent) => void,
  onError?: (err: Event) => void,
): () => void {
  const wsUrl = BACKEND_BASE.replace(/^http/, 'ws') + `/api/ws/scans/${scanUuid}`;
  let ws: WebSocket | null = null;
  let closed = false;
  let errored = false;

  const cleanup = () => {
    closed = true;
    if (ws) {
      // Remove handlers first so onclose doesn't fire mid-cleanup
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      try {
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          ws.close();
        }
      } catch { /* */ }
      ws = null;
    }
  };

  try {
    ws = new WebSocket(wsUrl);
  } catch (e) {
    if (onError) onError(e as Event);
    return cleanup;
  }

  ws.onmessage = (ev) => {
    if (closed) return;
    try {
      const data = JSON.parse(ev.data);
      onEvent(data);
      // Auto-cleanup on terminal messages
      if (data && (data.type === 'done' || data.type === 'error')) {
        // Give the consumer one tick to handle it, then close
        setTimeout(cleanup, 0);
      }
    } catch {
      // ignore malformed payload
    }
  };
  ws.onerror = (ev) => {
    if (closed || errored) return;
    errored = true;
    if (onError) onError(ev);
    // Important: close the socket on error, otherwise the browser may keep
    // it alive until the safety timeout fires (60s leak per scan).
    cleanup();
  };
  ws.onclose = () => {
    if (closed) return;
    closed = true;
  };

  return cleanup;
}

// ----------------------------------------------------------------------------
// UI render helpers — feed the existing terminal / progress UI
// ----------------------------------------------------------------------------

export function renderReportIntoFeed(report: Report, onDone?: () => void): void {
  const feed = document.querySelector('[data-scan-feed]');
  if (!feed) return;
  feed.innerHTML = '';

  const lines: Array<{ text: string; cls?: string }> = [];
  lines.push({ text: `$ project-mri analyze ./${report.project.name} --output ./${report.project.name}-report.html`, cls: 'cmd' });
  lines.push({ text: '→ loading configuration…', cls: 'mute' });

  // Per-run lines
  for (const run of report.runs) {
    const score = run.score;
    if (!score) continue;
    lines.push({
      text: `→ ${run.name.replace('_', ' ')} = ${score.value.toFixed(0)}/100 (${score.band})`,
      cls: score.band === 'critical' || score.band === 'poor' ? 'warn'
         : score.band === 'excellent' ? 'ok'
         : 'mute',
    });
    for (const c of score.contributors.slice(0, 2)) {
      lines.push({ text: `    · ${c}`, cls: 'mute' });
    }
  }
  lines.push({ text: `→ overall health = ${report.overall_health.toFixed(1)}/100 (${report.overall_band})`, cls: 'ok' });
  lines.push({ text: `→ report saved → ./${report.project.name}-report.html (${formatBytes(report.stats.loc_total * 4)} · self-contained)`, cls: 'mute' });
  lines.push({ text: '$ open ./' + report.project.name + '-report.html', cls: 'cmd' });
  lines.push({ text: `→ completed in ${report.duration_ms ?? 0}ms · 0 telemetry events`, cls: 'ok' });

  // Animate line-by-line
  lines.forEach((line, i) => {
    setTimeout(() => {
      const div = document.createElement('div');
      div.className = 'hero-cli__line' + (line.cls ? ` hero-cli__out--${line.cls}` : '');
      div.textContent = line.text;
      feed.appendChild(div);
      if (i === lines.length - 1 && onDone) onDone();
    }, i * 120);
  });
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// ----------------------------------------------------------------------------
// High-level orchestrator: run a scan with live progress, render into feed
// ----------------------------------------------------------------------------

export async function runScanWithUI(
  projectPath: string,
  feedSelector: string,
  onComplete?: (report: Report) => void,
): Promise<Report | null> {
  const feed = document.querySelector(feedSelector);
  if (feed) feed.innerHTML = '';

  // Step 1: POST /api/scans
  let scanUuid: string;
  try {
    const r = await startScan(projectPath);
    scanUuid = r.scan_uuid;
    appendLine(feed, `$ project-mri analyze ${projectPath}`, 'cmd');
    appendLine(feed, `→ scan queued · uuid=${scanUuid.slice(0, 8)}`, 'mute');
  } catch (e) {
    appendLine(feed, `✗ failed to start scan: ${(e as Error).message}`, 'alert');
    return null;
  }

  // Step 2: subscribe to WS for live progress
  let finalReport: Report | null = null;
  await new Promise<void>((resolve) => {
    let resolved = false;
    let unsubscribe: (() => void) | null = null;

    const finishOnce = (r?: Report | null) => {
      if (resolved) return;
      resolved = true;
      if (unsubscribe) {
        try { unsubscribe(); } catch { /* */ }
        unsubscribe = null;
      }
      if (r) finalReport = r;
      resolve();
    };

    unsubscribe = subscribeProgress(
      scanUuid,
      (msg) => {
        if (msg.type === 'progress') {
          appendLine(feed, `  → ${msg.phase}: ${msg.detail} (${msg.percent?.toFixed(0)}%)`, 'mute');
        } else if (msg.type === 'done') {
          appendLine(feed, `✓ scan complete · overall = ${msg.overall_health?.toFixed(1)}/100`, 'ok');
          finishOnce();
        } else if (msg.type === 'error') {
          appendLine(feed, `✗ error: ${msg.message}`, 'alert');
          finishOnce();
        }
      },
      () => {
        // WebSocket unavailable \u2014 fall back to polling
        appendLine(feed, `  (WebSocket unavailable \u2014 falling back to polling)`, 'mute');
        pollUntilDone(scanUuid).then(finishOnce);
      },
    );

    // Safety timeout \u2014 bail out after 60s no matter what
    setTimeout(() => {
      if (!resolved) {
        appendLine(feed, `  (timeout \u2014 finalising)`, 'mute');
        // Don't await pollScan here \u2014 just resolve
        finishOnce(null);
      }
    }, 60_000);
  });

  // Step 3: fetch the final report
  try {
    const status = await pollScan(scanUuid);
    if (status.report) {
      finalReport = status.report;
    }
  } catch (e) {
    appendLine(feed, `✗ failed to fetch report: ${(e as Error).message}`, 'alert');
  }

  if (finalReport && onComplete) onComplete(finalReport);
  return finalReport;
}

async function pollUntilDone(scanUuid: string): Promise<Report | null> {
  for (let i = 0; i < 30; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    try {
      const s = await pollScan(scanUuid);
      if (s.status === 'completed' && s.report) return s.report;
      if (s.status === 'failed') return null;
    } catch {
      // ignore
    }
  }
  return null;
}

function appendLine(feed: Element | null, text: string, cls?: string): void {
  if (!feed) return;
  const div = document.createElement('div');
  div.className = 'hero-cli__line' + (cls ? ` hero-cli__out--${cls}` : '');
  div.textContent = text;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
}

// Expose globally for inline onclick handlers
(window as unknown as { mriLive: typeof import('./live') }).mriLive = {
  fetchDemoReport, startScan, pollScan, subscribeProgress,
  renderReportIntoFeed, runScanWithUI,
};
export {};