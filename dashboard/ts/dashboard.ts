/**
 * PROJECT MRI — Self-hosted Dashboard
 * Single-page app, vanilla TypeScript, no framework.
 * Same design language as the marketing site.
 */

// ============================================================================
// Types
// ============================================================================

type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical';
type Band = 'excellent' | 'good' | 'fair' | 'poor' | 'critical';
type ScanStatus = 'pending' | 'running' | 'completed' | 'failed';

interface Finding {
  severity: Severity;
  category: string;
  title: string;
  description: string;
  target_path: string;
  target_symbol: string;
  score: number | null;
  data: Record<string, unknown>;
}

interface Score {
  label: string;
  value: number;
  band: Band;
  contributors: string[];
}

interface AnalyzerRun {
  name: string;
  status: ScanStatus;
  score: Score | null;
  findings: Finding[];
  signals: Record<string, unknown>;
  error_message: string;
}

interface Report {
  scan_uuid: string;
  project: { path: string; name: string; default_branch: string };
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  scores: Score[];
  overall_health: number;
  overall_band: Band;
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

interface Project {
  id: number;
  path: string;
  name: string;
  default_branch: string;
  first_scanned: string;
  last_scanned: string;
  file_count: number;
  loc_total: number;
  scan_count?: number;
  last_scan?: string;
}

interface ScanListItem {
  id: number;
  scan_uuid: string;
  project_id: number;
  status: ScanStatus;
  started_at: string;
  finished_at: string | null;
  error_message: string;
  project_name: string;
  project_path: string;
  summary: {
    overall_health: number;
    overall_band: Band;
    file_count: number;
    loc_total: number;
    commit_count: number;
    finding_counts: Record<string, number>;
  };
}

interface User {
  id: number;
  username: string;
  created_at: string;
  last_login_at: string | null;
}

// ============================================================================
// API client
// ============================================================================

const API_BASE = (() => {
  // Same origin as the page
  return `${window.location.protocol}//${window.location.host}`;
})();

let _token: string | null = null;
function getToken(): string | null { return _token || localStorage.getItem('mri_token'); }
function setToken(t: string | null) {
  _token = t;
  if (t) localStorage.setItem('mri_token', t);
  else localStorage.removeItem('mri_token');
}

async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> || {}),
  };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  // 10s timeout
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 10_000);
  try {
    const res = await fetch(`${API_BASE}${path}`, { ...init, headers, signal: ctrl.signal });
    if (res.status === 401) {
      setToken(null);
      // Don't navigate on 401 if we're already on the login page or trying to log in —
      // the form has its own error display.
      const r = currentRoute();
      const isAuthPath = path.startsWith('/api/auth/');
      if (r.name !== 'login' && !isAuthPath) {
        navigate('login');
      }
      throw new Error('Not authenticated');
    }
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`);
    }
    if (res.status === 204) return undefined as T;
    return await res.json() as T;
  } finally {
    clearTimeout(t);
  }
}

// ============================================================================
// Router (hash-based)
// ============================================================================

type Route = { name: string; params: Record<string, string> };

function currentRoute(): Route {
  const h = window.location.hash.replace(/^#\/?/, '');
  const [name, ...rest] = h.split('/');
  const params: Record<string, string> = {};
  if (name === 'scan' && rest[0]) params.uuid = rest[0];
  if (name === 'diff' && rest[0] && rest[1]) {
    params.a = rest[0];
    params.b = rest[1];
  }
  return { name: name || 'overview', params };
}

function navigate(name: string, params: Record<string, string> = {}) {
  let hash = `#/${name}`;
  if (name === 'scan' && params.uuid) hash += `/${params.uuid}`;
  if (name === 'diff' && params.a && params.b) hash += `/${params.a}/${params.b}`;
  window.location.hash = hash;
}

// ============================================================================
// View renderers
// ============================================================================

const root = () => document.getElementById('root')!;

function html(strings: TemplateStringsArray, ...values: any[]): string {
  let out = '';
  for (let i = 0; i < strings.length; i++) {
    out += strings[i];
    if (i < values.length) {
      const v = values[i];
      out += v === null || v === undefined ? '' : String(v)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }
  }
  return out;
}

function bandClass(b: Band): string { return `band-fill--${b}`; }
function bandBadgeClass(b: Band): string { return `badge--${b === 'good' ? 'good' : b}`; }
function severityClass(s: Severity): string { return `finding--${s}`; }

function escapeAttr(s: string): string {
  return s.replace(/'/g, '&#39;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

// ============================================================================
// Login view
// ============================================================================

async function renderLogin() {
  // Check if already initialized
  let status: { initialized: boolean; user_count: number };
  try {
    status = await api<{ initialized: boolean; user_count: number }>('/api/auth/status');
  } catch (e) {
    root().innerHTML = `<div class="empty"><h2>Cannot reach server</h2><p>${(e as Error).message}</p></div>`;
    return;
  }
  if (!status.initialized) {
    root().innerHTML = `
      <div class="login">
        <div class="login__box">
          <div class="login__brand">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>
              <path d="M12 1v3M12 20v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M1 12h3M20 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>
            </svg>
            project-mri
          </div>
          <div class="login__title">Not initialized</div>
          <div class="login__sub">Run <code>mri init</code> on the server to create the admin user, then refresh this page.</div>
        </div>
      </div>`;
    return;
  }
  root().innerHTML = `
    <div class="login">
      <div class="login__box">
        <div class="login__brand">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>
            <path d="M12 1v3M12 20v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M1 12h3M20 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>
          </svg>
          project-mri
        </div>
        <div class="login__title">Sign in</div>
        <div class="login__sub">Self-hosted dashboard for your local install.</div>
        <form class="login__form" id="login-form">
          <input type="text" id="login-username" placeholder="username" autocomplete="username" required>
          <input type="password" id="login-password" placeholder="password" autocomplete="current-password" required>
          <button type="submit" class="login__btn">Sign in</button>
          <div class="login__err" id="login-err"></div>
        </form>
      </div>
    </div>`;
  document.getElementById('login-form')!.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = (document.getElementById('login-username') as HTMLInputElement).value;
    const password = (document.getElementById('login-password') as HTMLInputElement).value;
    const err = document.getElementById('login-err')!;
    err.textContent = '';
    try {
      const res = await api<{ token: string }>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      setToken(res.token);
      navigate('overview');
    } catch (e) {
      err.textContent = 'Invalid username or password';
    }
  });
}

// ============================================================================
// App shell
// ============================================================================

async function renderShell(view: () => Promise<void>) {
  const route = currentRoute();
  const user = await api<User>('/api/auth/whoami').catch(() => null);
  if (!user) {
    return renderLogin();
  }
  root().innerHTML = `
    <nav class="nav">
      <div class="nav__inner">
        <a href="#/overview" class="nav__brand">
          <svg class="nav__brand-mark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>
            <path d="M12 1v3M12 20v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M1 12h3M20 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>
          </svg>
          project-mri
        </a>
        <div class="nav__links">
          <a class="nav-link ${route.name === 'overview' ? 'is-active' : ''}" href="#/overview">overview</a>
          <a class="nav-link ${route.name === 'projects' ? 'is-active' : ''}" href="#/projects">projects</a>
          <a class="nav-link ${route.name === 'scans' ? 'is-active' : ''}" href="#/scans">scans</a>
          <a class="nav-link ${route.name === 'new-scan' ? 'is-active' : ''}" href="#/new-scan">+ new scan</a>
          <a class="nav-link ${route.name === 'settings' ? 'is-active' : ''}" href="#/settings">settings</a>
        </div>
        <div class="nav__meta">
          <span>@${escapeAttr(user.username)}</span>
          <a href="#" id="logout-link">logout</a>
        </div>
      </div>
    </nav>
    <div class="status-bar">
      <div class="status-bar__group">
        <span class="status-bar__live"><span class="status-bar__dot"></span>local-first</span>
        <span>offline-ready</span>
        <span>mit · v0.3.0</span>
      </div>
      <div class="status-bar__group">
        <span>user @${escapeAttr(user.username)}</span>
      </div>
    </div>
    <div class="app">
      <aside class="sidebar">
        <div class="sidebar__section">
          <div class="sidebar__label">navigation</div>
          <a class="sidebar__item ${route.name === 'overview' ? 'is-active' : ''}" href="#/overview">overview</a>
          <a class="sidebar__item ${route.name === 'projects' ? 'is-active' : ''}" href="#/projects">projects</a>
          <a class="sidebar__item ${route.name === 'scans' ? 'is-active' : ''}" href="#/scans">all scans</a>
          <a class="sidebar__item ${route.name === 'new-scan' ? 'is-active' : ''}" href="#/new-scan">+ new scan</a>
        </div>
        <div class="sidebar__section">
          <div class="sidebar__label">resources</div>
          <a class="sidebar__item" href="/api/docs" target="_blank">api docs ↗</a>
          <a class="sidebar__item" href="/api/health/deep" target="_blank">health check ↗</a>
          <a class="sidebar__item" href="/metrics" target="_blank">metrics ↗</a>
        </div>
        <div class="sidebar__section">
          <div class="sidebar__label">help</div>
          <a class="sidebar__item" href="https://github.com/project-mri/project-mri" target="_blank">github ↗</a>
        </div>
      </aside>
      <main class="main" id="main-content"></main>
    </div>
    <footer class="footer">project-mri v0.3.0 · self-hosted · local-first · ${new Date().getFullYear()}</footer>
  `;
  document.getElementById('logout-link')!.addEventListener('click', async (e) => {
    e.preventDefault();
    await api('/api/auth/logout', { method: 'POST' }).catch(() => {});
    setToken(null);
    navigate('login');
  });
  // Render the actual view into <main>
  const main = document.getElementById('main-content')!;
  const originalInner = main.innerHTML;
  // Stub a render function that the view writes into:
  (window as any).__renderInto = (html: string) => { main.innerHTML = html; };
  try {
    await view();
  } catch (e) {
    main.innerHTML = `<div class="empty"><h2>Failed to load</h2><p>${(e as Error).message}</p></div>`;
  }
  if (main.innerHTML === originalInner) {
    // view didn't write anything
  }
}

function setMain(html: string) {
  (window as any).__renderInto(html);
}

// ============================================================================
// Views
// ============================================================================

async function renderOverview() {
  setMain(`<div class="loading"></div>`);
  const [projects, scans] = await Promise.all([
    api<{ projects: Project[]; count: number }>('/api/projects?limit=10'),
    api<{ scans: ScanListItem[]; count: number }>('/api/scans?limit=10'),
  ]);
  const totalScans = scans.count;
  const totalFiles = projects.projects.reduce((sum, p) => sum + (p.file_count || 0), 0);
  const totalLoc = projects.projects.reduce((sum, p) => sum + (p.loc_total || 0), 0);
  const recentCompleted = scans.scans.filter(s => s.status === 'completed');
  const avgHealth = recentCompleted.length > 0
    ? recentCompleted.reduce((s, sc) => s + (sc.summary?.overall_health || 0), 0) / recentCompleted.length
    : 0;
  const running = scans.scans.filter(s => s.status === 'running' || s.status === 'pending').length;

  setMain(`
    <div class="page-header">
      <h1>overview</h1>
      <p>Summary of your project-mri installation.</p>
    </div>
    <div class="grid grid--4" style="margin-bottom:32px;">
      <div class="card">
        <div class="card__label">projects</div>
        <div class="card__val">${projects.count}</div>
        <div class="card__sub">${running} scan${running === 1 ? '' : 's'} running</div>
      </div>
      <div class="card">
        <div class="card__label">scans</div>
        <div class="card__val">${totalScans}</div>
        <div class="card__sub">all-time</div>
      </div>
      <div class="card">
        <div class="card__label">files analyzed</div>
        <div class="card__val">${totalFiles.toLocaleString()}</div>
        <div class="card__sub">${totalLoc.toLocaleString()} LOC</div>
      </div>
      <div class="card">
        <div class="card__label">avg health</div>
        <div class="card__val">${avgHealth.toFixed(1)}</div>
        <div class="card__sub">across ${recentCompleted.length} completed</div>
      </div>
    </div>
    <h2 style="font-size:14px; letter-spacing:0.18em; text-transform:uppercase; color:var(--text-mute); margin-bottom:12px;">recent scans</h2>
    ${renderScansTable(scans.scans)}
  `);
}

function renderScansTable(scans: ScanListItem[]): string {
  if (!scans.length) {
    return `<div class="empty"><h2>No scans yet</h2><p>Click <a href="#/new-scan">+ new scan</a> to start one.</p></div>`;
  }
  return `
    <table class="table">
      <thead>
        <tr>
          <th>project</th>
          <th>status</th>
          <th>health</th>
          <th>files</th>
          <th>LOC</th>
          <th>commits</th>
          <th>started</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        ${scans.map(s => `
          <tr>
            <td>
              <a href="#/scan/${s.scan_uuid}">${escapeAttr(s.project_name || '?')}</a>
              <div style="color:var(--text-mute); font-size:11px;">${escapeAttr(s.project_path || '')}</div>
            </td>
            <td><span class="badge badge--${s.status === 'completed' ? 'ok' : s.status === 'failed' ? 'alert' : 'info'}">${s.status}</span></td>
            <td>${s.summary?.overall_health != null ? `<span class="badge badge--${bandBadgeClass(s.summary.overall_band)}">${s.summary.overall_health.toFixed(1)}</span>` : '—'}</td>
            <td class="num">${s.summary?.file_count?.toLocaleString() || '—'}</td>
            <td class="num">${s.summary?.loc_total?.toLocaleString() || '—'}</td>
            <td class="num">${s.summary?.commit_count?.toLocaleString() || '—'}</td>
            <td>${(s.started_at || '').slice(0, 19).replace('T', ' ')}</td>
            <td><a href="#/scan/${s.scan_uuid}">view →</a></td>
          </tr>
        `).join('')}
      </tbody>
    </table>`;
}

async function renderProjects() {
  setMain(`<div class="loading"></div>`);
  const res = await api<{ projects: Project[]; count: number }>('/api/projects?limit=100');
  setMain(`
    <div class="page-header">
      <h1>projects</h1>
      <p>${res.count} project${res.count === 1 ? '' : 's'} scanned.</p>
    </div>
    ${res.projects.length === 0
      ? `<div class="empty"><h2>No projects yet</h2><p>Start a scan to add a project.</p></div>`
      : `<div class="grid grid--3">
          ${res.projects.map(p => `
            <div class="card card--hover" onclick="window.location.hash='#/scans?project=${encodeURIComponent(p.path)}'">
              <div class="card__label">${escapeAttr(p.name)}</div>
              <div class="card__val" style="font-size:18px;">${p.file_count.toLocaleString()} <span style="color:var(--text-mute); font-size:14px; font-weight:400;">files</span></div>
              <div class="card__sub">${p.loc_total.toLocaleString()} LOC · ${p.scan_count || 0} scan${(p.scan_count || 0) === 1 ? '' : 's'}</div>
              <div class="card__sub" style="margin-top:4px; color:var(--text-dim); word-break:break-all;">${escapeAttr(p.path)}</div>
            </div>
          `).join('')}
        </div>`}
  `);
}

async function renderScans() {
  setMain(`<div class="loading"></div>`);
  const url = new URL(window.location.href);
  const projectFilter = url.searchParams.get('project');
  const apiUrl = projectFilter
    ? `/api/scans?limit=100` // would need backend support; for now show all
    : '/api/scans?limit=100';
  const res = await api<{ scans: ScanListItem[]; count: number }>(apiUrl);
  setMain(`
    <div class="page-header">
      <h1>scans</h1>
      <p>${res.count} scan${res.count === 1 ? '' : 's'}.</p>
    </div>
    ${renderScansTable(res.scans)}
  `);
}

async function renderNewScan() {
  setMain(`
    <div class="page-header">
      <h1>+ new scan</h1>
      <p>Start a scan on a local directory or a git URL.</p>
    </div>
    <div class="form-section">
      <h3>scan target</h3>
      <form id="new-scan-form">
        <div class="form-row">
          <div class="form-label">path or url</div>
          <input class="form-input" id="ns-path" type="text" placeholder="/path/to/repo  OR  https://github.com/owner/name" required>
        </div>
        <div class="form-row">
          <div class="form-label">branch (optional)</div>
          <input class="form-input" id="ns-branch" type="text" placeholder="main">
        </div>
        <div class="form-row">
          <div class="form-label">clone depth (urls only)</div>
          <input class="form-input" id="ns-depth" type="number" min="1" placeholder="full history">
        </div>
        <div class="form-row">
          <div class="form-label"></div>
          <button type="submit">start scan</button>
          <span id="ns-err" style="color:var(--alert); margin-left:12px;"></span>
        </div>
      </form>
    </div>
    <div class="form-section">
      <h3>how it works</h3>
      <p style="color:var(--text-secondary); font-size:12px; line-height:1.7;">
        <strong style="color:var(--text-primary);">Local path</strong> — scans the directory directly. Run as the user who owns the files.
        <br><br>
        <strong style="color:var(--text-primary);">Git URL</strong> — shallow-clones to <code>~/.cache/project-mri/repos/</code>, then scans. Cleanup is automatic.
        For private repos, set the <code>integrations.github.token</code> or <code>integrations.gitlab.token</code> in your <code>.mri.yml</code>.
        <br><br>
        <strong style="color:var(--text-primary);">Async</strong> — scans run in a background task. Navigate away; the scan continues. You'll see status updates on the scan detail page.
      </p>
    </div>
  `);
  document.getElementById('new-scan-form')!.addEventListener('submit', async (e) => {
    e.preventDefault();
    const path = (document.getElementById('ns-path') as HTMLInputElement).value.trim();
    const branch = (document.getElementById('ns-branch') as HTMLInputElement).value.trim() || null;
    const depthStr = (document.getElementById('ns-depth') as HTMLInputElement).value.trim();
    const depth = depthStr ? parseInt(depthStr, 10) : null;
    const err = document.getElementById('ns-err')!;
    err.textContent = '';
    try {
      const res = await api<{ scan_uuid: string }>('/api/scans', {
        method: 'POST',
        body: JSON.stringify({
          project_path: path,
          branch,
          depth,
        }),
      });
      navigate('scan', { uuid: res.scan_uuid });
    } catch (e) {
      err.textContent = (e as Error).message;
    }
  });
}

async function renderScanDetail(uuid: string) {
  setMain(`<div class="loading"></div>`);
  // Poll the scan status
  const poll = async (): Promise<any> => {
    return api(`/api/scans/${uuid}`);
  };
  let status: any;
  try {
    status = await poll();
  } catch (e) {
    setMain(`<div class="empty"><h2>Scan not found</h2><p>${(e as Error).message}</p></div>`);
    return;
  }
  const projectName = status.project_name || '?';
  const projectPath = status.project_path || '';

  // If completed, fetch the report
  if (status.status === 'completed' && status.report) {
    renderCompletedScan(status, uuid);
  } else if (status.status === 'failed') {
    setMain(`
      <div class="page-header">
        <h1>${escapeAttr(projectName)}</h1>
        <p style="color:var(--alert);">Scan failed: ${escapeAttr(status.error_message || 'unknown error')}</p>
      </div>
    `);
  } else {
    // Still running — show progress + connect WebSocket
    setMain(`
      <div class="page-header">
        <h1>${escapeAttr(projectName)}</h1>
        <p>${escapeAttr(projectPath)} · <span class="badge badge--info">${status.status}</span></p>
      </div>
      <div class="card" style="margin-bottom:24px;">
        <div class="card__label">scanning…</div>
        <div class="progress" style="margin-top:12px;"><div class="progress__fill" id="scan-progress-fill" style="width:0%"></div></div>
        <div id="scan-progress-text" style="color:var(--text-mute); font-size:11px; margin-top:8px;">connecting…</div>
      </div>
    `);
    connectWebSocket(uuid);
  }
}

function connectWebSocket(uuid: string) {
  const wsUrl = `${API_BASE.replace(/^http/, 'ws')}/api/ws/scans/${uuid}`;
  const ws = new WebSocket(wsUrl);
  const fill = document.getElementById('scan-progress-fill') as HTMLElement;
  const text = document.getElementById('scan-progress-text') as HTMLElement;
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'progress') {
        if (fill) fill.style.width = `${msg.percent || 0}%`;
        if (text) text.textContent = `${msg.phase}: ${msg.detail} (${msg.percent?.toFixed(0)}%)`;
      } else if (msg.type === 'done') {
        if (text) text.textContent = `Done! Reloading…`;
        setTimeout(() => renderScanDetail(uuid), 500);
      } else if (msg.type === 'error') {
        if (text) text.textContent = `Error: ${msg.message}`;
      }
    } catch {}
  };
  ws.onerror = () => {
    // Fall back to polling
    const interval = setInterval(async () => {
      try {
        const s = await api<any>(`/api/scans/${uuid}`);
        if (s.status === 'completed' || s.status === 'failed') {
          clearInterval(interval);
          renderScanDetail(uuid);
        }
      } catch {}
    }, 2000);
  };
}

function renderCompletedScan(status: any, uuid: string) {
  const r: Report = status.report;
  setMain(`
    <div class="page-header">
      <h1>${escapeAttr(r.project.name)}</h1>
      <p>${escapeAttr(r.project.path)} · branch ${escapeAttr(r.project.default_branch)} · ${r.stats.file_count} files · ${r.stats.loc_total.toLocaleString()} LOC · ${r.stats.commit_count} commits</p>
      <div style="margin-top:8px; display:flex; gap:8px;">
        <a href="/api/scans/${uuid}/report.html" target="_blank" class="badge badge--accent">full report (html) ↗</a>
        <a href="/api/scans/${uuid}/report.json" target="_blank" class="badge">json ↗</a>
        <a href="/api/scans/${uuid}/report.sarif" target="_blank" class="badge">sarif ↗</a>
        <button id="delete-btn" style="margin-left:auto;">delete</button>
      </div>
    </div>
    <div class="grid grid--4" style="margin-bottom:32px;">
      <div class="card">
        <div class="card__label">overall</div>
        <div class="card__val">${r.overall_health.toFixed(1)}</div>
        <div class="badge badge--${bandBadgeClass(r.overall_band)}" style="margin-top:8px;">${r.overall_band}</div>
      </div>
      <div class="card">
        <div class="card__label">findings</div>
        <div class="card__val">${r.findings.length}</div>
        <div class="card__sub">${Object.entries(r.stats.finding_counts).map(([s, c]) => `${escapeAttr(s)}: ${c}`).join(' · ') || 'none'}</div>
      </div>
      <div class="card">
        <div class="card__label">duration</div>
        <div class="card__val">${((r.duration_ms || 0) / 1000).toFixed(1)}s</div>
        <div class="card__sub">${(r.started_at || '').slice(0, 19).replace('T', ' ')}</div>
      </div>
      <div class="card">
        <div class="card__label">languages</div>
        <div class="card__val" style="font-size:18px;">${Object.keys(r.stats.languages).length}</div>
        <div class="card__sub">${Object.entries(r.stats.languages).slice(0, 3).map(([l, d]) => `${escapeAttr(l)}: ${d.files}`).join(' · ')}</div>
      </div>
    </div>
    <h2 style="font-size:14px; letter-spacing:0.18em; text-transform:uppercase; color:var(--text-mute); margin-bottom:12px;">score breakdown</h2>
    <div class="score-grid" style="margin-bottom:32px;">
      ${r.scores.map(s => `
        <div class="score-card">
          <div class="score-card__label">${escapeAttr(s.label.replace(/_/g, ' '))}</div>
          <div class="score-card__val">${s.value.toFixed(1)}</div>
          <div class="score-card__band badge--${bandBadgeClass(s.band)}">${s.band}</div>
          <div class="band-fill ${bandClass(s.band)}" style="width:${s.value}%"></div>
          <div style="margin-top:8px; font-size:11px; color:var(--text-mute);">
            ${s.contributors.slice(0, 2).map(c => `<div>· ${escapeAttr(c)}</div>`).join('')}
          </div>
        </div>
      `).join('')}
    </div>
    <h2 style="font-size:14px; letter-spacing:0.18em; text-transform:uppercase; color:var(--text-mute); margin-bottom:12px;">how this score was composed</h2>
    <div class="card" style="margin-bottom:32px;">
      ${r.composition.map(c => `<div style="padding:6px 0; border-bottom:1px dashed var(--line); color:var(--text-secondary); font-size:12px;">${escapeAttr(c)}</div>`).join('')}
    </div>
    <h2 style="font-size:14px; letter-spacing:0.18em; text-transform:uppercase; color:var(--text-mute); margin-bottom:12px;">top findings (${r.findings.length} total)</h2>
    <div class="findings">
      ${r.findings.slice(0, 50).map(f => `
        <div class="finding ${severityClass(f.severity)}">
          <div class="finding__sev">${f.severity}${f.score != null ? ' · ' + Math.round(f.score) : ''}</div>
          <div>
            <div class="finding__title">${escapeAttr(f.title)}</div>
            ${f.description ? `<div class="finding__desc">${escapeAttr(f.description)}</div>` : ''}
            ${f.target_path ? `<div class="finding__path">${escapeAttr(f.target_path)}${f.target_symbol ? ' :: ' + escapeAttr(f.target_symbol) : ''}</div>` : ''}
          </div>
        </div>
      `).join('')}
    </div>
  `);
  document.getElementById('delete-btn')!.addEventListener('click', async () => {
    if (!confirm('Delete this scan? This cannot be undone.')) return;
    await api(`/api/scans/${uuid}`, { method: 'DELETE' });
    navigate('scans');
  });
}

async function renderSettings() {
  setMain(`<div class="loading"></div>`);
  const user = await api<User>('/api/auth/whoami');
  setMain(`
    <div class="page-header">
      <h1>settings</h1>
      <p>Account, integrations, and configuration.</p>
    </div>
    <div class="form-section">
      <h3>account</h3>
      <div class="form-row">
        <div class="form-label">username</div>
        <div class="form-input">${escapeAttr(user.username)}</div>
      </div>
      <div class="form-row">
        <div class="form-label">created</div>
        <div class="form-input">${(user.created_at || '').slice(0, 19).replace('T', ' ')}</div>
      </div>
      <div class="form-row">
        <div class="form-label">last login</div>
        <div class="form-input">${(user.last_login_at || 'never').slice(0, 19).replace('T', ' ')}</div>
      </div>
    </div>
    <div class="form-section">
      <h3>change password</h3>
      <form id="pw-form">
        <div class="form-row">
          <div class="form-label">current password</div>
          <input class="form-input" type="password" id="pw-current" required>
        </div>
        <div class="form-row">
          <div class="form-label">new password (8+ chars)</div>
          <input class="form-input" type="password" id="pw-new" minlength="8" required>
        </div>
        <div class="form-row">
          <div class="form-label"></div>
          <button type="submit">change password</button>
          <span id="pw-msg" style="margin-left:12px; font-size:12px;"></span>
        </div>
      </form>
    </div>
    <div class="form-section">
      <h3>integrations</h3>
      <p style="color:var(--text-secondary); font-size:12px; margin-bottom:12px;">
        To enable GitHub/GitLab private repos, edit your <code>.mri.yml</code> config and restart the server.
        See <a href="https://github.com/project-mri/project-mri/blob/main/docs/INTEGRATIONS.md" target="_blank">docs/INTEGRATIONS.md</a>.
      </p>
      <pre style="font-size:11px;">integrations:
  github:
    token: ghp_xxxxxxxxxxxx
  gitlab:
    token: glpat-xxxxxxxxxxxx

notifications:
  webhook:
    url: https://your-server/webhook
    events: [scan_complete, scan_failed]</pre>
    </div>
    <div class="form-section">
      <h3>configuration file</h3>
      <p style="color:var(--text-secondary); font-size:12px; margin-bottom:12px;">
        Edit <code>~/.config/project-mri/config.yml</code> to customize the server, scans, and integrations.
        See <a href="https://github.com/project-mri/project-mri/blob/main/docs/CONFIG.md" target="_blank">docs/CONFIG.md</a> for the full reference.
      </p>
    </div>
  `);
  document.getElementById('pw-form')!.addEventListener('submit', async (e) => {
    e.preventDefault();
    const current = (document.getElementById('pw-current') as HTMLInputElement).value;
    const newPw = (document.getElementById('pw-new') as HTMLInputElement).value;
    const msg = document.getElementById('pw-msg')!;
    try {
      await api('/api/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: current, new_password: newPw }),
      });
      msg.innerHTML = '<span style="color:var(--ok);">password changed</span>';
      (document.getElementById('pw-current') as HTMLInputElement).value = '';
      (document.getElementById('pw-new') as HTMLInputElement).value = '';
    } catch (e) {
      msg.innerHTML = `<span style="color:var(--alert);">${(e as Error).message}</span>`;
    }
  });
}

// ============================================================================
// Router dispatch
// ============================================================================

async function route() {
  const r = currentRoute();
  if (r.name === 'login' || !getToken()) {
    return renderLogin();
  }
  await renderShell(async () => {
    switch (r.name) {
      case 'overview': return renderOverview();
      case 'projects': return renderProjects();
      case 'scans': return renderScans();
      case 'new-scan': return renderNewScan();
      case 'scan': return renderScanDetail(r.params.uuid || '');
      case 'settings': return renderSettings();
      default:
        setMain(`<div class="empty"><h2>Not found</h2><p>No view for "${escapeAttr(r.name)}".</p></div>`);
    }
  });
}

window.addEventListener('hashchange', route);
window.addEventListener('DOMContentLoaded', route);
if (document.readyState !== 'loading') route();
