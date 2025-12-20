# Project MRI — Full Production Roadmap

**Goal:** 100% production-ready, self-hosted, open-source codebase intelligence tool.
**Status:** In progress (Phase 0 → Phase 7)
**Last updated:** 2025-12-20

## Two artifacts

This repository ships **two distinct things**:

### 1. Public marketing site (root of repo)
- Lives at `/workspace/project-mri/*.html` and `/workspace/project-mri/css/`, etc.
- Deployed to `dhik11xvyp9l.space.minimax.io` (separate static deployment).
- Shows: features, manifesto, install instructions, architecture diagram, demo.
- Audience: people discovering the product.

### 2. Self-hosted product (the actual deliverable)
- Lives in `/workspace/project-mri/backend/` (API + CLI) and `/workspace/project-mri/dashboard/` (UI).
- Installed by end users via `pip install project-mri` or `docker run projectmri/mri`.
- Includes its own web UI at `http://localhost:7331/dashboard/`.
- Audience: people who installed it on their own server.

The marketing site and the dashboard share the same **design language** (warm amber, JetBrains Mono,
terminal aesthetic) but are **completely separate** — the marketing site is read-only docs/info,
the dashboard is a fully interactive tool.

## Phases

### Phase 0: Restructure (in progress)
- [x] Add `dashboard/` directory for the self-hosted UI source
- [x] Keep `*.html` and `css/` at repo root (the marketing site)
- [x] Document the separation

### Phase 1: Backend foundations
- [ ] `.mri.yml` config file loader (`mri/config.py`)
- [ ] Single-user auth (set during `mri init`) — username + password + JWT
- [ ] Alembic migrations
- [ ] WebSocket auth
- [ ] Persistent scan queue (in DB) so scans survive server restart

### Phase 2: Repository cloning
- [ ] `mri scan <url>` — clone remote repo, then scan
- [ ] GitHub PAT support for private repos
- [ ] GitLab PAT support
- [ ] Shallow clone (`--depth=N`)
- [ ] Auto-cleanup of cloned repos

### Phase 3: Operational features
- [ ] `GET /api/scans/{a}/diff/{b}` — compare two scans
- [ ] SARIF export for CI integration
- [ ] Webhook notifications on scan_complete / scan_failed
- [ ] `mri watch <path>` — re-scan on file change
- [ ] DB backup / restore commands (`mri backup`, `mri restore`)

### Phase 4: Self-hosted dashboard
- [ ] Login page (JWT)
- [ ] Projects list (with status badges, last scan, score)
- [ ] Project detail (list of scans, ability to trigger new scan)
- [ ] Scan detail (real-time progress via WebSocket, results, findings)
- [ ] Diff view (compare 2 scans side-by-side)
- [ ] Settings (admin: change password, integrations, webhooks)
- [ ] Same design language as marketing site

### Phase 5: Distribution
- [ ] `pyproject.toml` ready for `pip install project-mri`
- [ ] `install.sh` one-liner: `curl -fsSL ... | bash`
- [ ] `mri init` — first-run setup (admin user, DB, default config)
- [ ] `mri upgrade` — pull latest and run migrations
- [ ] `mri reset` — wipe DB (with confirmation)
- [ ] Dockerfile + docker-compose ready for Docker Hub
- [ ] GitHub Action: `uses: project-mri/action@v1`
- [ ] GitLab CI template
- [ ] Homebrew formula (optional)

### Phase 6: Tests
- [ ] New tests for all features (config, auth, clone, diff, SARIF, webhook, watch)
- [ ] Dashboard E2E tests with Playwright
- [ ] All 85+ existing tests still pass

### Phase 7: Documentation
- [ ] `INSTALL.md` — full install guide
- [ ] `DASHBOARD.md` — dashboard user guide
- [ ] `API.md` — auto-generated API reference
- [ ] `INTEGRATIONS.md` — GitHub, GitLab, webhooks
- [ ] `CONFIG.md` — `.mri.yml` reference
- [ ] Updated `README.md` with new install instructions
- [ ] Updated `CHANGELOG.md` with v0.3.0 entry

### Final
- [ ] Re-deploy marketing site
- [ ] Package final v0.3.0 zip
- [ ] Full E2E verification
- [ ] Honest final report
