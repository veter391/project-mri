# Project MRI — Roadmap

**Goal:** a production-ready, self-hosted, MIT-licensed codebase intelligence
tool — not a demo and not an MVP.

**Last verified against the code:** 2026-07-20. Every box below was checked by
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

**Fusion — the moat.** The data model above, now driven end to end:
- [x] Ingest local agent session logs and correlate each session to the commits
      it produced (`git log` NUL-delimited, no shell escaping surprises)
- [x] Per-file AI/human/unattributed line-share via `git blame` × session→commit,
      with an over-claim guard: shares sum to 100, blame never asserts a human
      share, a sub-noise signal reports "none" rather than a fabricated number
- [x] Decision provenance from ADRs and commits, the "why" left null when it
      cannot be recovered, related decisions linked
- [x] The consequence loop — what measurably changed after a decision, reported
      as correlation unless causation is justified
- [x] Four surfaces over the same audited layers: `mri fusion` (CLI),
      `GET /api/projects/{id}/fusion` (HTTP), `mri eval` (validate), and an
      **agent-native MCP server** (`mri mcp`, optional `[mcp]` extra) so a coding
      agent can ask who authored a file and what decided it, mid-task
- [x] Evaluation harness — a synthetic labelled corpus with known ground truth;
      calibration error 0.0 and the over-claim guard run as a hard gate

**Documentation**
- [x] [INSTALL.md](INSTALL.md), [CONFIG.md](CONFIG.md), [API.md](API.md),
      [INTEGRATIONS.md](INTEGRATIONS.md), [DASHBOARD.md](DASHBOARD.md)
- [x] [Architecture decision records](adr/README.md), including the ones that
      declined a dependency and said why

---

## In progress

**Base-risk composition.** Folding the fusion signals (AI-share, decision
density, consequence volatility) back into the analyzer layer's per-file risk
score, so the headline number reflects provenance and not only static and
git-history metrics. The signals are computed and surfaced; the weighted
recomposition into the base score is the remaining step.

---

## Planned

- **Session-reasoning mining.** Recover the *why* an agent made a change from
  the reasoning in its session log — off by default, since logs can hold
  secrets, and gated behind explicit content retention.
- **Third-party log formats.** Ingest Cursor and aider session logs once a
  verified real-world sample of each format is in hand ([ADR-009](adr/ADR-009-cursor-aider-ingest-deferred.md)).

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
