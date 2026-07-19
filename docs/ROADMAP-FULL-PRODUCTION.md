# Project MRI — Roadmap

**Goal:** a production-ready, self-hosted, MIT-licensed codebase intelligence
tool — not a demo and not an MVP.

**Last verified against the code:** 2026-07-19. Every box below was checked by
running the thing or reading the file that implements it, not from memory. If
you find a claim here that the code does not support, that is a bug in this
document and worth an issue.

## What this repository ships

Two artifacts, deliberately separate:

| | Source | Audience |
|---|---|---|
| **Public site** | [`apps/web/`](../apps/web) | People discovering the product |
| **The product** | [`src/mri/`](../src/mri) (API + CLI), [`apps/dashboard/`](../apps/dashboard) (UI) | People who installed it |

They share a design language and nothing else. The site is read-only; the
dashboard is the installed tool's own interface, served by the API at
`/dashboard/`.

---

## Shipped

**Engine and CLI**
- [x] Git-history and structure analyzers, with explainable per-analyzer scoring
- [x] `mri init`, `scan`, `serve`, `watch`, `demo`, `backup`, `restore`, `upgrade`, `reset`, `ui`
- [x] Scanning a remote URL — clone, then scan; GitHub and GitLab tokens; shallow clone
- [x] Self-contained HTML reports
- [x] SARIF export for CI
- [x] Webhook notifications, with delivery recorded in the database
- [x] `GET /api/scans/{a}/diff/{b}` — compare two scans
- [x] Live scan progress over WebSocket

**Foundations**
- [x] `.mri.yml` configuration ([CONFIG.md](CONFIG.md))
- [x] Single-user auth set during `mri init` — password hashing, JWT
- [x] Schema migrations — a small in-house runner, not Alembic
      ([ADR-005](adr/ADR-005-schema-migrations.md) explains why)
- [x] Reproducible toolchain: `uv.lock` plus a hash-pinned `requirements.txt`
- [x] Deterministic container image, verified by an actual `docker run`
- [x] CI: lint, types, tests, dashboard e2e with axe accessibility checks

**The fusion data model** — the tables the remaining layers are built on:
sessions, session events, file touches, authorship shares, decisions,
consequences. Two product claims are enforced by the schema rather than by
convention: an attribution's shares must account for the whole file with
`unattributed` as a first-class share, and a consequence must declare whether
it claims correlation or causation.

**Documentation**
- [x] [INSTALL.md](INSTALL.md), [CONFIG.md](CONFIG.md), [API.md](API.md),
      [INTEGRATIONS.md](INTEGRATIONS.md), [DASHBOARD.md](DASHBOARD.md)
- [x] [Architecture decision records](adr/README.md), including the ones that
      declined a dependency and said why

---

## In progress

**AI-authorship attribution.** Reading local agent session logs to decompose
per-file risk into AI-authored, human-authored, and — honestly labelled —
unattributed shares. The data model is in place; the ingest is not yet.

---

## Planned

- **Decision provenance.** Link commits, ADRs, and issues into a queryable
  why-graph, with the "why" left absent when it cannot be recovered rather
  than invented.
- **The consequence loop.** Measure what actually changed after a decision, and
  report it as correlation unless causation can be justified.
- **Agent-native surface (MCP).** Let coding agents query risk, history, and
  decisions live.
- **Evaluation harness.** A labelled corpus and metrics, so the accuracy claims
  in this README are numbers rather than adjectives.

---

## Not built yet

Named explicitly so the absence is not mistaken for an oversight:

- The dashboard is currently a login shell. The projects list, scan detail,
  diff view, and settings screens are designed but not implemented.
- No persistent scan queue — scans do not survive a server restart.
- No `install.sh` one-liner, `docker-compose.yml`, GitHub Action, GitLab CI
  template, or Homebrew formula. The supported installs today are
  `pip install project-mri` and the container image.

## Definition of done, for any item above

1. Type checks and lint pass.
2. The change was exercised — a test, a dev server, or both. "It reads
   correctly" is not evidence.
3. A security and a performance pass over the change, with findings either
   fixed or declined in writing with a measurement.
4. No accuracy claim ships without the number behind it.
