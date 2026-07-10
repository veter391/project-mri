# Self-hosted dashboard

The dashboard is a small, terminal-aesthetic web UI that ships with project-mri. It runs
on the same port as the API (`http://localhost:7331/dashboard/`) and is served from the
local filesystem — no external CDN, no third-party scripts.

![dashboard preview placeholder]

---

## Access

```bash
mri serve
# → open http://localhost:7331/dashboard/
```

Log in with the username and password you set during `mri init`.

> The dashboard is local-first: there's no public URL by default. To expose it via
> reverse proxy, see [INSTALL.md → expose publicly](#expose-publicly).

---

## Views

### 1. Overview (`#/overview`)

A snapshot of all your projects:
- **Total scans** — all-time count
- **Total files scanned** — across every project
- **Average health score** — 0-100, weighted by file count
- **Recent scans** — last 10, click to drill in

### 2. Projects (`#/projects`)

Card grid of all unique projects (deduped by path / URL). Each card shows:
- Project name
- Latest scan date + status badge
- Latest health score (color-coded band)
- Number of scans

Click any card to see all scans for that project.

### 3. Scans (`#/scans`)

Full table of every scan. Columns:
- **UUID** (truncated, click to copy)
- **Project**
- **Status** badge (queued / running / completed / failed / cancelled)
- **Health score** (color-coded band)
- **Started** (relative time + absolute on hover)

Use the search box at the top to filter by project name or UUID prefix.

### 4. New scan (`#/new-scan`)

Form with three fields:
- **Path or URL** — absolute local path (`/home/me/code`) **or** git URL
  (`https://github.com/owner/repo.git`)
- **Branch** — optional, defaults to default branch (URLs only)
- **Depth** — clone depth for URL scans, `1` = shallow (fast), `0` = full clone

Click **Start scan** to submit. You'll be redirected to the scan detail page with
live progress.

### 5. Scan detail (`#/scan/<uuid>`)

Once a scan starts:
- **Progress bar** with current phase + percent
- **Live log** via WebSocket — shows analyzer start/stop events
- **Cancel** button (if still running)

When complete, the view switches to:

#### Score breakdown
Six cards, one per analyzer:
- Health (overall composite)
- Architecture (module coupling / cycles)
- Dependencies (imports)
- Complexity (cyclomatic)
- Tech debt (TODO / dead code)
- Git history (commit cadence / hotspots)

Each card shows the analyzer's 0-100 score and a short description.

#### Composition
Bar chart of language breakdown by line count.

#### Findings
Top 50 findings, sorted by severity (critical → low). Each shows:
- Severity badge (color-coded)
- Category + analyzer
- Title
- File:line location
- Short description

Click any finding to expand its full detail.

#### Reports
Three buttons at the top:
- **HTML report** — full visual report
- **JSON report** — machine-readable, for tooling
- **SARIF report** — for GitHub Code Scanning / IDEs

#### Diff (`#/diff/<a>/<b>`)
Select two completed scans and click **Compare**. Shows:
- Per-analyzer score delta (↑ green / ↓ red / = grey)
- Findings added / removed / severity-changed
- Stats diff (files, LOC, commits)

#### Delete
The **Delete** button at the bottom removes the scan record permanently.
This is irreversible.

### 6. Settings (`#/settings`)

#### Account
- **Username** (read-only)
- **Member since** (created_at)
- **Last login**

#### Change password
Form with current + new password (8+ chars). On success you'll be logged out
and asked to log in with the new password.

#### Integrations
Read-only docs showing where to put your secrets (see [INTEGRATIONS.md](./INTEGRATIONS.md)):
- `MRI_GITHUB_TOKEN` env var → for cloning private GitHub repos
- `MRI_GITLAB_TOKEN` env var → for cloning private GitLab repos
- `MRI_BITBUCKET_TOKEN` env var → for Bitbucket
- `MRI_WEBHOOK_URL` env var → for scan-complete notifications

#### Config reference
Links to [CONFIG.md](./CONFIG.md) for the full `.mri.yml` reference.

#### Logout
Button at the bottom right of the top nav.

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| `g` then `o` | Go to Overview |
| `g` then `p` | Go to Projects |
| `g` then `s` | Go to Scans |
| `g` then `n` | New scan |
| `g` then `c` | Settings |
| `?` | Show shortcuts |
| `Esc` | Close modals |

(Shortcuts are off by default; enable in `~/.config/project-mri/.mri.yml` under
`dashboard.shortcuts: true`.)

---

## Theming

The dashboard uses your terminal-aesthetic palette:
- **Background**: `#06080C` (deep dark)
- **Accent**: `#F4A847` (warm amber)
- **Font**: system monospace (no external font load)

If your terminal has a different palette you'd like the dashboard to mirror,
set `dashboard.accent_color` in your `.mri.yml`.

---

## Mobile

The dashboard is responsive down to 360px wide. On mobile:
- The sidebar collapses to a hamburger menu
- Tables become card stacks
- Score breakdowns stack vertically

---

## Security

- All API requests are sent over the loopback interface by default — never the public
  network unless you bind it explicitly
- Passwords are hashed with bcrypt (12 rounds)
- Session is JWT (HS256, 24h TTL) stored in `localStorage` + a same-origin `HttpOnly`
  cookie for API requests
- CSRF is enforced on POST/PUT/DELETE via the `SameSite` cookie attribute
- Rate limiting: 60 req/min general, 5 scans/min per IP (configurable)

For exposing the dashboard on a public network, see [INSTALL.md → expose publicly](#expose-publicly)
and put it behind HTTPS + reverse proxy + basic-auth or VPN.

---

## Disabling the dashboard

If you only want the API (e.g., for headless CI usage):

```yaml
# .mri.yml
dashboard:
  enabled: false
```

Restart `mri serve` and the `/dashboard/` route will return 404.

---

## What's *not* in the dashboard

The dashboard is intentionally minimal. We don't have:
- User management (it's single-user self-hosted — there's only one admin)
- Project sharing / multi-tenant views
- Comment threads on findings
- Web-based config editing (edit `.mri.yml` directly)

For these, use the [HTTP API](./API.md) directly.