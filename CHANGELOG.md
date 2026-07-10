# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2025-12-20

### Added

#### Authentication & users
- **Single-user self-hosted auth** — no registration, no multi-tenant
- `bcrypt(12)` password hashing
- **JWT HS256** tokens (24h TTL), auto-generated secret stored in DB
- `POST /api/auth/login`, `/logout`, `/whoami`, `/change-password`, `/status`
- Session cookie (HttpOnly, SameSite=Lax) alongside JWT
- Legacy API key auth still works for backward compat

#### Configuration
- **`.mri.yml`** loader with deep-merge over compiled defaults
- 11 sections: server, database, scans, analyzers, auth, integrations, notifications, clones, watch, dashboard
- All env vars (`MRI_*`) override `.mri.yml` values
- Schema validation on startup

#### Repository cloning
- `mri scan https://github.com/owner/repo.git` — shallow clone, scan, auto-cleanup
- HTTPS + SSH URLs (`git@host:owner/name.git`)
- **GitHub / GitLab / Bitbucket PAT** support — token injected into URL, never logged
- Cached in `~/.cache/project-mri/repos/<sha256-prefix>/`

#### Watch mode
- `mri watch PATH` — re-scan on file change
- Debounced (default 2s) to coalesce bursts
- Configurable globs + ignore patterns

#### Webhooks
- `notifications.webhook.url` config or `MRI_WEBHOOK_URL` env var
- Optional HMAC-SHA256 signing (`X-MRI-Signature` header)
- Events: `scan.completed`, `scan.failed`
- Retries with exponential backoff (1s, 5s, 30s)
- All deliveries logged in `webhook_deliveries` table

#### Diff endpoint
- `GET /api/scans/{a}/diff/{b}` — compare two scans
- Per-analyzer score delta, findings added/removed/severity-changed, stats diff

#### SARIF export
- `GET /api/scans/{uuid}/report.sarif` — SARIF 2.1.0
- Compatible with GitHub Code Scanning, IDE SARIF viewers

#### Delete endpoint
- `DELETE /api/scans/{uuid}` — idempotent

#### CLI
- `mri init` — interactive admin setup
- `mri scan PATH_OR_URL [--depth N] [--branch X] [--json-out FILE] [--output FILE]`
- `mri watch PATH`
- `mri serve` — API + dashboard
- `mri demo` — synthetic report
- `mri backup/restore FILE.tar.gz` — DB + config
- `mri reset` — wipe DB + clones
- `mri upgrade` — pip install --upgrade
- `mri ui` — open dashboard in browser
- `mri list` — recent scans

#### Self-hosted dashboard
- Terminal-aesthetic SPA at `/dashboard/`
- 6 views: login, overview, projects, scans, new scan, scan detail, diff, settings
- Live progress via WebSocket (with polling fallback)
- API client with 10s AbortController timeout, JWT in localStorage
- Mobile-responsive (hamburger menu, card stacks)
- Accessibility: skip link, ARIA labels, keyboard navigation
- Ships in pip wheel — no separate frontend install

#### Distribution
- `install.sh` — one-liner installer (`curl ... | bash`) with `--user` / `--system` modes
- Python-version detection (3.10+)
- `.github/action/action.yml` — official GitHub Action for CI
- `ci/gitlab-ci.yml` — GitLab CI template with Code Quality output
- Comprehensive [INSTALL.md](./docs/INSTALL.md), [DASHBOARD.md](./docs/DASHBOARD.md), [API.md](./docs/API.md), [INTEGRATIONS.md](./docs/INTEGRATIONS.md), [CONFIG.md](./docs/CONFIG.md)

### Changed
- Tree-sitter pinned to `<0.21` in both requirements.txt and pyproject.toml
- Hand-rolled Prometheus metrics replaced with official `prometheus_client` (gains `process_*`, `python_gc_*` metrics for free)
- Replaced recursive Tarjan SCC with iterative (handles 5000 modules in 8ms)
- Replaced recursive AST traversal with iterative (handles 10k-deep ASTs)
- Parser instances cached with `@lru_cache(maxsize=8)` — was creating one per file
- DB writes throttled to 1/sec with lock (was N+1 per progress event)
- File reads capped at 2MB with sample-based LOC estimation for large files

### Security
- **Path validation** — rejects `..`, absolute paths outside allowed roots, etc.
- **Branch validation** — rejects shell metacharacters
- **URL validation** for git clones — only known hosts (github.com, gitlab.com, bitbucket.org) + custom via config
- **HMAC-SHA256 webhook signing** with `X-MRI-Signature` header
- **Auth middleware** distinguishes JWTs from API keys by `token.count(".") == 2` (prevents JWT being accepted as API key when `MRI_API_KEYS` is empty)
- **Public paths** for `/api/auth/login`, `/logout`, `/status`, `/dashboard/**` so login always works
- **tarfile.extractall** validated to reject path traversal, symlinks, special files (in `mri restore`)
- All subprocess calls use fixed args + URL validation + `# nosec` annotations
- Removed `assert` from production code paths (`repository.py`)

### Fixed
- 20 audit findings (see commit history):
  - Duplicate function definitions in `repository.py`
  - Recursive → iterative in `dependencies.py`, `complexity.py`
  - Parser caching
  - Comment ratio logic
  - Dead code in `tech_debt.py`
  - Operator precedence in `coupling.py`
  - Misplaced `import re`
  - N+1 DB writes
  - File-size cap in scanner
  - WS orphan leak on error
  - `fetch` no timeout → AbortController 10s
  - `_module_of` extension strip collision (`foo.bar.py` vs `foo/bar.py`)
  - Various other correctness/clarity fixes

### Performance
- 500-file repo: ~800ms
- 30 concurrent scans: 100% completion in 3.4s
- 5000-module dependency graph: 8ms (was crashing on 1k+)

### Testing
- **134 tests** passing 3x in a row
  - 74 original (analyzers, API, security, failure modes)
  - 36 v0.3.0 backend tests (config, auth, JWT, repo URL, webhook, diff, delete, SARIF)
  - 7 watch + CLI tests (debounce, globs, init, list, backup/restore)
  - 11 audit-fix regression tests (no-duplicates, parser cache, _module_of, etc.)
  - 6 Playwright E2E tests (login, wrong-password, overview, full scan flow, password change, responsive)
- **Bandit**: 0 High, 0 Medium, 0 Low
- **pip-audit**: 0 vulnerabilities
- **ruff**: All checks pass

## [0.2.0] — 2025-12-19

### Added
- 6 analyzers: git_history, architecture, dependencies, complexity, tech_debt, coupling
- Scanner orchestrator with progress callback
- Jinja2 HTML report generator + JSON dump
- Demo feed (deterministic synthetic data for `my-legacy-app` and `clean-typescript-lib`)
- FastAPI app with: health, version, scans (POST/GET/list), projects (list), WebSocket progress
- Click CLI: `mri scan`, `mri serve`, `mri demo`, `mri ui`
- SQLite schema + async repository (projects, scans, analyzer_runs, findings, scan_events)
- Pydantic v2 models (Finding, Score, Report, Project, etc.)
- Frontend TypeScript modules (chrome, terminal, demos, index, live)
- Demo page with live backend integration + bundled fallback JSON
- CORS lockdown, rate limiting, body cap, security headers, path validation

## [0.1.0] — 2025-12-18

### Added
- Initial 7-page static site (index, features, architecture, install, manifesto, roadmap, about)
- Terminal aesthetic with warm amber palette
- TypeScript build pipeline (vanilla → ES modules)
- Go backend placeholder (replaced by Python in 0.2.0)

[0.3.0]: https://github.com/project-mri/project-mri/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/project-mri/project-mri/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/project-mri/project-mri/releases/tag/v0.1.0