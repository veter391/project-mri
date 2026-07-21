# MRI

> **MRI reads what's actually in your codebase — and who actually wrote it.**
> Local-first codebase intelligence: git history, AI-session provenance, explainable risk, decision-to-consequence tracking. MIT licensed.

![License: MIT](https://img.shields.io/badge/license-MIT--forever-amber)
![Version](https://img.shields.io/badge/version-0.3.0-amber)
![Status: Beta](https://img.shields.io/badge/status-beta-amber)
[![CI](https://github.com/project-mri/project-mri/actions/workflows/ci.yml/badge.svg)](https://github.com/project-mri/project-mri/actions/workflows/ci.yml)

**MRI** turns a repository into an explainable model of its history, structure,
and risk — and then goes where other tools stop: it reads the AI-session logs
already on your machine (`~/.claude`, `~/.cursor`) to map **prompt → file →
commit**, decomposes each file's risk into **AI-authored vs human-authored
shares**, and correlates the **decision** behind a change to the **consequence**
that followed. All on your machine. Zero cloud, zero telemetry, zero accounts.

**Site**: [mri.shypot.com](https://mri.shypot.com) · **Docs**: [`docs/`](./docs) · **How it works**: [mri.shypot.com/how-it-works](https://mri.shypot.com/how-it-works)

```bash
pip install project-mri

mri scan .        # analyze a repo (path or git URL)
mri fusion        # AI-provenance view: authorship, decisions, consequences
mri serve         # dashboard at http://localhost:7331/dashboard/
```

---

## The loop

Individually, most of MRI's capabilities have a rival. Collectively — as one
complete, trustworthy, free, self-hostable loop — it stands alone:

1. **History + structure** — full git history × tree-sitter AST. Hotspots,
   churn, ownership, coupling, complexity: measured, not guessed.
2. **Session-log provenance** — reads local `~/.claude` / `~/.cursor` logs (and
   consumes Agent Trace / git-ai git-notes) to map prompts to files to commits.
3. **Authorship-decomposed risk** — every 0–100 score carries a ledger, then
   splits into AI vs human shares via `git blame` × session-commit correlation.
   Unattributed lines stay unattributed — never silently counted as human.
4. **Decision provenance** — the "why" behind a change, mined from ADRs
   (confidence 0.95) and commit rationale (0.6), recorded as a first-class artifact.
5. **Consequence loop** — did the metric move afterward? 30-day window,
   confidence capped at 0.6, confounder guardrails. **Correlation, never causation.**

Surfaced to humans — dashboard, self-contained HTML report, CLI, SARIF CI-gate —
and to agents, via a read-only **MCP server** (`mri mcp`).

---

## Highlights

- **Local-first, forever** — `pip install project-mri`; nothing leaves your machine
- **Session-log AI provenance** — prompt-level attribution, not git-metadata guessing
- **Explainable scores** — every number traces to a commit, line, or AST node
- **Six analyzers** — git history, architecture, dependencies, complexity, tech debt, coupling
- **Decision → consequence** — guardrailed correlation, drawn as a dashed line by design
- **Agent-native** — read-only MCP server over stdio for Claude Code, Cursor, any MCP client
- **Self-hosted dashboard** — terminal-aesthetic UI at `/dashboard/`, shipped in the wheel
- **CI integration** — GitHub Action, GitLab CI template, SARIF with authorship properties
- **Zero telemetry, proven** — an egress-tripwire test fails the build if any code path opens a non-loopback connection
- **Privacy by default** — session *content* is off (`store_content=False`), enforced at the DB layer
- Watch mode, webhooks (HMAC-signed), scan diff, backups

---

## Quick start

### Install

```bash
pipx install project-mri        # or: pip install --user project-mri
```

Or with Docker (build from source):
```bash
git clone https://github.com/project-mri/project-mri.git
cd project-mri
docker build -t project-mri .
docker run -d --name project-mri -p 7331:7331 \
  -v mri-data:/home/mri/.cache/project-mri \
  project-mri
```

### First run

```bash
mri init          # create admin user (interactive)
mri serve         # start API + dashboard
```

Open `http://localhost:7331/dashboard/`. Loopback needs no auth; binding to a
public interface **fails closed** without configured auth (ADR-013).

### Scan something

```bash
mri scan /path/to/your/repo                      # local path
mri scan https://github.com/owner/repo.git       # shallow clone, auto-cleanup
mri scan . --sessions ~/.claude                  # include AI-session provenance
mri fusion                                       # authorship / decisions / consequences
mri watch /path/to/your/repo                     # re-scan on change
mri demo                                         # synthetic demo scan
```

Reports land in `~/.cache/project-mri/reports/<uuid>.html` — self-contained,
archivable, readable in five years.

---

## Repository layout

The repo is a hybrid monorepo: a Python package (`src`-layout) plus a pnpm
workspace of Next.js apps.

```
project-mri/
├── pyproject.toml               # Python package (src-layout), pinned deps
├── pnpm-workspace.yaml          # pnpm workspace → apps/*
├── src/mri/                     # Python package (import name: mri)
│   ├── analyzers/               # six analyzers
│   ├── api/                     # FastAPI app, routes, middleware
│   ├── auth/                    # JWT + bcrypt
│   ├── services/                # scanner, repo_cloner, webhook, watcher
│   ├── db/                      # schema.sql + repository (content-retention triggers)
│   ├── _frontend/dashboard/     # built dashboard, embedded at build time (gitignored)
│   ├── security.py              # path/branch validation, safe-bind guard
│   ├── config.py                # .mri.yml loader
│   └── cli.py                   # CLI commands
├── apps/
│   ├── web/                     # Next.js 16 marketing site → Cloudflare Workers (mri.shypot.com)
│   └── dashboard/               # Next.js dashboard → static export, embedded in the wheel
├── tests/                       # pytest suite (unit + API + E2E + egress tripwire)
├── docs/                        # METHODOLOGY, TRUST, AUDIT, API, CONFIG, INSTALL, INTEGRATIONS + adr/
├── .github/
│   ├── workflows/ci.yml         # lint, tests, Next builds, Docker, Bandit, pip-audit
│   └── action/action.yml        # official GitHub Action
├── ci/gitlab-ci.yml             # GitLab CI template
└── LICENSE, CHANGELOG.md, CONTRIBUTING.md, SECURITY.md
```

The dashboard ships **inside the Python wheel**: `apps/dashboard` builds a static
export that is served by FastAPI at `/dashboard/` — `pip install project-mri`
needs no Node runtime.

---

## The six analyzers

| Analyzer | What it measures |
|---|---|
| **git_history** | Commit hotspots, bus factor, knowledge islands, change frequency |
| **architecture** | Module map, god modules, deep nesting, layer violations |
| **dependencies** | Import graph, SCC cycle detection, fan-in/fan-out, unstable modules |
| **complexity** | LOC, function length, cyclomatic complexity (lizard), comment ratio |
| **tech_debt** | Weighted TODO/FIXME/HACK markers, dead code, density per file |
| **coupling** | Robert Martin's I/A/D metrics, afferent/efferent coupling |

Each contributes a 0–100 score with a contributor ledger. The composite is a
weighted mean; **unmeasured analyzers are excluded, never zeroed**. Every score
decomposes in the dashboard — [METHODOLOGY.md](./docs/METHODOLOGY.md) explains
every number.

---

## HTTP API

| Endpoint | Purpose |
|---|---|
| `GET  /api/health` · `/api/health/deep` | Liveness / readiness |
| `POST /api/scans` | Start a scan (path or URL) |
| `GET  /api/scans` · `/api/scans/{uuid}` | List / status + report |
| `GET  /api/scans/{uuid}/report.{html,json,sarif}` | Three formats |
| `GET  /api/scans/{a}/diff/{b}` | Compare two scans |
| `GET  /api/projects/{id}/fusion` | AI-provenance fusion view |
| `WS   /api/ws/scans/{uuid}` | Live progress |
| `POST /api/auth/login` · `GET /api/auth/whoami` | Auth (JWT, 24h) |
| `GET  /metrics` | Prometheus format |
| `GET  /dashboard/` | Self-hosted dashboard |

Full reference: [API.md](./docs/API.md)

---

## Tech stack

- **Backend**: Python 3.10+, FastAPI, aiosqlite, GitPython, tree-sitter, Pydantic v2, bcrypt, PyJWT, watchdog, prometheus-client
- **Frontend**: Next.js + TypeScript + Tailwind v4 — `apps/web` (marketing, Cloudflare Workers) and `apps/dashboard` (embedded in the wheel)
- **Tests**: pytest, pytest-asyncio, httpx, Playwright (E2E), an egress tripwire
- **CI**: GitHub Actions (lint + tests + Next builds + Docker + Bandit + pip-audit)

---

## Performance

Measured on MRI's own repository ([AUDIT.md](./docs/AUDIT.md)): **270 files,
98 findings, ~2.5s**. Scaling study: 200 files ≈ 2.4s · 800 ≈ 9.7s ·
1600 ≈ 13.2s — roughly linear.

---

## Security

Self-hosted means you own your data — MRI ships hardened defaults:

- **Fail-closed exposure** — non-loopback bind without auth refuses to start (ADR-013)
- **bcrypt(12)** password hashing · **JWT HS256** (24h) with DB-stored secrets
- **Path validation** (rejects `..`), **branch validation** (rejects shell metacharacters), clone-SSRF guard
- **Per-IP rate limiting** — 60 req/min, 5 scans/min
- **CSP, HSTS, X-Frame-Options** on every response · CORS allowlist, no wildcards
- **HMAC-SHA256 webhook signing** · 1 MiB body cap · tarfile traversal guard in `mri restore`
- **Zero telemetry, enforced by test** — `tests/test_no_network.py` seals the network and fails the build on any egress

Every guarantee maps to the code or test that proves it: [TRUST.md](./docs/TRUST.md).
Disclosure policy: [SECURITY.md](./SECURITY.md).

---

## Development

```bash
git clone https://github.com/project-mri/project-mri.git
cd project-mri

# Backend (src-layout, editable install)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
mri init && pytest

# Frontend (pnpm workspace)
pnpm install
pnpm dev:web                # marketing site
pnpm dev:dashboard          # dashboard
pnpm build:dashboard        # static export → embedded into src/mri/_frontend

# Quality gate
ruff check src/mri && bandit -r src/mri && pip-audit --strict
```

Quality bars are enforced in CI: ruff zero-findings, 75% coverage floor
([QUALITY-BARS.md](./docs/QUALITY-BARS.md)). Contribution flow:
[CONTRIBUTING.md](./CONTRIBUTING.md).

---

## Project status

**v0.3.0** — Beta. The fusion loop (session provenance → authorship-decomposed
risk → decisions → consequences) is complete end-to-end; API, CLI and dashboard
are stable. Toward 1.0:

- [ ] Cursor / aider session-log ingestion (deferred until real samples — ADR-009)
- [ ] Session-reasoning "why" mining (ADR-012)
- [ ] Plugin system for custom analyzers
- [ ] Incremental scans · configurable scoring weights
- [ ] Multi-language structural expansion (Rust, Go, Java)

Decision records: [docs/adr/](./docs/adr). History: [CHANGELOG.md](./CHANGELOG.md).

---

## License

**MIT — forever.** The whole system is open source: all analyzers, the fusion
engine, the API, the dashboard, the MCP server, the CI integrations. No paid
tier, no feature gating, no telemetry, no account. A tool that reads your
prompts and your source has to be inspectable and un-revocable — so it is.

---

## Credits

Built on excellent open source, named and credited: [tree-sitter](https://tree-sitter.github.io/),
[PyDriller](https://pydriller.readthedocs.io/), [lizard](https://github.com/terryyin/lizard),
[grimp](https://github.com/seddonym/grimp) + [import-linter](https://github.com/seddonym/import-linter),
[NetworkX](https://networkx.org/), [GitPython](https://gitpython.readthedocs.io/),
[FastAPI](https://fastapi.tiangolo.com/) + [Pydantic](https://docs.pydantic.dev/).
