# project-mri

> **MRI scan for your software project.**
> Local-first codebase intelligence — history, architecture, risk, explainable scoring.

![License: MIT](https://img.shields.io/badge/license-MIT-amber)
![Version](https://img.shields.io/badge/version-0.3.0-amber)
![Status: Beta](https://img.shields.io/badge/status-beta-amber)
![Tests: 134 passing](https://img.shields.io/badge/tests-134%20passing-amber)

**project-mri** analyzes your codebase across **6 dimensions** — git history,
architecture, dependencies, complexity, tech debt, coupling — and produces a
self-contained HTML report you can open offline. **Zero cloud. Zero telemetry.
Zero accounts.**

```bash
# One-line install:
curl -fsSL https://raw.githubusercontent.com/project-mri/project-mri/main/install.sh | bash

# Then:
mri init          # create your admin user
mri serve         # start the API + dashboard
open http://localhost:7331/dashboard/
```

---

## Why this exists

You inherit codebases with **no context**. Existing tools analyze code but rarely
explain history and risk. Project MRI turns any repository into an interactive,
queryable, and **scorable** model of its architecture, history, and health — all
locally.

We lead with **facts**, not magic scores. Every number traces back to a signal.
Every score explains itself.

---

## Highlights

- **100% self-hosted** — `pip install project-mri`, that's it
- **Single-user admin** — no registration, no multi-tenant, no SaaS
- **Six analyzers** — git history, architecture, dependencies, complexity, tech debt, coupling
- **Self-hosted dashboard** — terminal-aesthetic SPA at `/dashboard/`
- **Repository cloning** — scan `https://github.com/owner/repo.git` directly
- **CI integration** — official GitHub Action, GitLab CI template
- **SARIF export** — for GitHub Code Scanning, IDE integration
- **Webhooks** — get notified on scan complete (Slack, custom, etc.)
- **Watch mode** — `mri watch PATH` re-scans on file change
- **Diff** — compare any two scans
- **Backups** — `mri backup/restore`

---

## Quick start

### Install

```bash
curl -fsSL https://raw.githubusercontent.com/project-mri/project-mri/main/install.sh | bash
```

Or with pip:
```bash
pip install --user project-mri
export PATH="$HOME/.local/bin:$PATH"
```

Or with Docker:
```bash
docker pull ghcr.io/project-mri/project-mri:latest
docker run -d --name project-mri -p 7331:7331 \
  -v mri-data:/home/mri/.cache/project-mri \
  ghcr.io/project-mri/project-mri:latest
```

### First run

```bash
mri init          # create admin user (interactive)
mri serve         # start API + dashboard
```

Open `http://localhost:7331/dashboard/` in your browser.

### Scan something

```bash
# Local path:
mri scan /path/to/your/repo

# Git URL:
mri scan https://github.com/owner/repo.git

# Watch mode (re-scan on every file change):
mri watch /path/to/your/repo

# Generate synthetic demo:
mri demo
```

Reports are written to `~/.cache/project-mri/reports/<uuid>.html`.

---

## Repository layout

```
project-mri/
├── *.html, css/, ts/, dist/     # Static marketing site (7 pages)
├── data/                        # Bundled demo JSON
├── dashboard/                   # Self-hosted dashboard SPA
│   ├── ts/                      # Vanilla TypeScript (no framework)
│   ├── dist/                    # Compiled JS
│   ├── css/                     # Design system
│   └── index.html
├── backend/
│   ├── mri/                     # Python package
│   │   ├── analyzers/           # 6 analyzers
│   │   ├── auth/                # JWT + bcrypt
│   │   ├── api/routes/          # FastAPI routes
│   │   ├── services/            # scanner, repo_cloner, webhook, watcher
│   │   ├── db/                  # schema + repository
│   │   ├── security.py          # path validation, branch validation
│   │   ├── middleware.py        # 5 middlewares
│   │   ├── config.py            # .mri.yml loader
│   │   ├── metrics.py           # prometheus_client integration
│   │   └── cli.py               # 11 Click commands
│   └── tests/                   # 134 tests (incl. Playwright E2E)
├── .github/
│   ├── workflows/ci.yml         # CI: lint, test, build, audit
│   └── action/action.yml        # Official GitHub Action
├── ci/gitlab-ci.yml             # GitLab CI template
├── install.sh                   # One-liner installer
├── Dockerfile                   # Multi-stage, non-root, distroless
├── docker-compose.yml
├── LICENSE, CHANGELOG.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md
├── README.md (this file)
├── INSTALL.md                   # Detailed install guide
├── DASHBOARD.md                 # Dashboard user guide
├── API.md                       # HTTP API reference
├── INTEGRATIONS.md              # Webhooks, CI/CD, IDE integration
└── CONFIG.md                    # .mri.yml reference
```

---

## Architecture

```
mri scan PATH_OR_URL
       │
       ▼
   ┌─────────┐    ┌─────────────────┐
   │ Clone   │───▶│   Scanner       │
   │ (URL)   │    │   orchestrator  │
   └─────────┘    └────────┬────────┘
       │                   │
       │           ┌───────┴───────┐
       │           ▼               ▼
       │      ┌─────────┐    ┌────────────┐
       │      │git_histr│...│coupling    │  ← 6 parallel analyzers
       │      └────┬────┘    └─────┬──────┘
       │           │              │
       │           ▼              ▼
       │      ┌─────────────────────┐
       │      │  SQLite (aiosqlite) │
       │      │  scans, findings,   │
       │      │  analyzer_runs,     │
       │      │  users, webhooks    │
       │      └──────────┬──────────┘
       │                 │
       │                 ▼
       │           ┌──────────────┐
       │           │  FastAPI     │
       │           │  + dashboard │
       │           └──────┬───────┘
       │                  │
       └─────cleanup──────┴─────webhook──▶ Slack/your endpoint
```

---

## The six analyzers

| Analyzer | What it measures |
|---|---|
| **git_history** | Commit hotspots, bus factor, knowledge islands, change frequency |
| **architecture** | Module map, god modules, deep nesting, layer violations |
| **dependencies** | Import graph, SCC cycle detection, fan-in/fan-out, unstable modules |
| **complexity** | LOC, function length, cyclomatic, comment ratio, long files |
| **tech_debt** | TODO/FIXME/HACK markers, dead code, density per file |
| **coupling** | Robert Martin's I/A/D metrics, afferent/efferent coupling |

Each contributes a 0–100 score. The composite health score is a weighted average.
Every score explains itself in the dashboard.

---

## HTTP API

| Endpoint | Purpose |
|---|---|
| `GET  /api/health` | Liveness |
| `GET  /api/health/deep` | Readiness (DB + analyzers + tree-sitter + git) |
| `POST /api/scans` | Start a scan (path or URL) |
| `GET  /api/scans` | List recent scans |
| `GET  /api/scans/{uuid}` | Scan status + report |
| `GET  /api/scans/{uuid}/report.{html,json,sarif}` | Three formats |
| `GET  /api/scans/{a}/diff/{b}` | Compare two scans |
| `DELETE /api/scans/{uuid}` | Idempotent delete |
| `WS   /api/ws/scans/{uuid}` | Live progress |
| `POST /api/auth/login` | Get JWT (24h) |
| `GET  /api/auth/whoami` | Current user |
| `POST /api/auth/change-password` | Rotate password |
| `GET  /metrics` | Prometheus format |
| `GET  /dashboard/` | Self-hosted dashboard |

Full reference: [API.md](./API.md)

---

## Tech stack

- **Backend**: Python 3.10+, FastAPI, aiosqlite, GitPython, tree-sitter, Jinja2, Pydantic v2, bcrypt, PyJWT, watchdog, prometheus-client, click
- **Frontend (marketing site)**: Vanilla TypeScript → ES modules, custom CSS, JetBrains Mono
- **Frontend (dashboard)**: Vanilla TypeScript SPA, ~30KB, no framework
- **Tests**: pytest, pytest-asyncio, httpx, Playwright (E2E)
- **CI**: GitHub Actions (lint + tests + Docker build + Bandit + pip-audit)

---

## Performance

| Repo size | Scan time |
|---|---|
| < 100 files | < 1s |
| 500 files | ~800ms |
| 1k files | 1–2s |
| 10k files | 5–15s |
| 50k+ files | 30s–2min (with default config) |

- 30 concurrent scans on small repos: 100% completion in 3.4s
- 5000-module dependency graph (Tarjan SCC): 8ms

---

## Security

Self-hosted means you own your data, but also your security posture. We ship with
sensible defaults:

- **bcrypt(12)** for password hashing
- **JWT HS256** tokens with auto-generated secrets (stored in DB)
- **Path validation** — rejects `..`, absolute paths outside allowed roots
- **Branch validation** — rejects shell metacharacters
- **Per-IP rate limiting** — 60 req/min, 5 scans/min
- **CSP, HSTS, X-Frame-Options** on every response
- **CORS lockdown** — explicit allowlist, no wildcards
- **Body size cap** — 1 MiB default
- **Structured logging** — JSON for prod, text for dev
- **HMAC-SHA256 webhook signing**
- **Tarfile path-traversal protection** in `mri restore`

For production deployments, see [INTEGRATIONS.md → expose publicly](./INTEGRATIONS.md#reverse-proxy--public-access).

---

## Development

```bash
# Clone
git clone https://github.com/project-mri/project-mri.git
cd project-mri

# Backend dev
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
mri init
PYTHONPATH=. pytest tests/ -v          # 134 tests

# Frontend dev
cd ..
npm run build                          # tsc → dist/
npm run serve                          # python server with .html auto-rewrite

# Or full validation
bandit -r backend/mri/                 # 0/0/0
ruff check backend/mri/                # clean
pip-audit --strict --requirement backend/requirements.txt  # 0 vulnerabilities
```

---

## Project status

**v0.3.0** — Beta. API stable, CLI stable, dashboard stable.

We're working towards 1.0:

- [ ] Plugin system for custom analyzers
- [ ] Incremental scans (diff against cached results)
- [ ] GitHub Checks API integration
- [ ] Email notifications
- [ ] Configurable scoring weights
- [ ] Multi-language expansion (Rust, Go, Java)

See [CHANGELOG.md](./CHANGELOG.md) for the full release history.

---

## License

MIT. The core engine is MIT-licensed forever. Commercial features (managed
hosting, enterprise SSO) will live on top of the open core, never instead of it.

---

## Credits

- [tree-sitter](https://tree-sitter.github.io/) for parsing
- [GitPython](https://gitpython.readthedocs.io/) for git access
- [FastAPI](https://fastapi.tiangolo.com/) + [Pydantic](https://pydantic-docs.helpmanual.io/) for the API
- [Prometheus](https://prometheus.io/) for metrics
- Everyone who gave feedback on the spec