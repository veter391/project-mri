# Project MRI — Roadmap

**Goal:** a production-ready, self-hosted, MIT-licensed codebase intelligence
tool — not a demo and not an MVP.

**Last verified against the code:** 2026-07-21. Every box below was checked by
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
- [x] Authorship-weighted risk — the portion of a file's existing risk that sits
      under agent-modified code, bounded ≤ the base risk and labelled
      correlation, not blame; the fusion view leads with the most
      agent-attributable file. Provenance is *not* folded into the risk score
      itself ([ADR-011](adr/ADR-011-base-risk-composition.md) explains why that
      would be an over-claim)

**Product surfaces & release readiness**
- [x] The moat is carried by every surface: `mri fusion` (CLI), the fusion HTTP
      route, the agent-native MCP server (5 tools), SARIF (authorship in finding
      properties), the self-contained HTML report (fusion section), and the
      **dashboard fusion view** — verified in a real browser + axe
- [x] Security & performance audit gate run ([AUDIT.md](AUDIT.md)): bandit 0
      medium+ (4 false positives verified and suppressed with reason), pip-audit
      0 known CVEs, a perf figure on a mid-size repo
- [x] Packaging verified ([PACKAGING.md](PACKAGING.md)): the wheel installs into
      a clean virtualenv and the `mri` CLI runs from the installed path; it ships
      the pre-built dashboard so no Node runtime is needed
- [x] Technical SEO on the public site: sitemap, robots, JSON-LD structured data

**Documentation**
- [x] [INSTALL.md](INSTALL.md), [CONFIG.md](CONFIG.md), [API.md](API.md),
      [INTEGRATIONS.md](INTEGRATIONS.md), [DASHBOARD.md](DASHBOARD.md),
      [METHODOLOGY.md](METHODOLOGY.md), [TRUST.md](TRUST.md),
      [AUDIT.md](AUDIT.md), [PACKAGING.md](PACKAGING.md)
- [x] [Architecture decision records](adr/README.md) (14 ADRs), including the
      ones that declined a dependency or a framing and said why

---

## In progress

**Nothing mid-flight.** The fusion moat is complete end to end. The next items
are in "Planned" below, each gated on a real input rather than started early.

---

## Planned

- **Session-reasoning mining.** Recover the *why* an agent made a change from the
  reasoning in its session log. Free-form rationale extraction is deferred as an
  over-claim without a validated corpus ([ADR-012](adr/ADR-012-session-reasoning-mining-deferred.md));
  the verifiable slice named there is deterministic citation-linking of stored
  reasoning to decisions the project already records. Off by default, since logs
  can hold secrets, and gated behind explicit content retention.
- **Third-party log formats.** Ingest Cursor and aider session logs once a
  verified real-world sample of each format is in hand ([ADR-009](adr/ADR-009-cursor-aider-ingest-deferred.md)).

---

## Not built yet

Named explicitly so the absence is not mistaken for an oversight:

- The dashboard has login, an overview + scans list, and the **AI-provenance
  fusion view** (per-file authorship, decisions and consequences, verified in a
  real browser with axe). The scan-detail, diff, and settings screens are
  designed but not implemented.
- No persistent scan queue — scans do not survive a server restart.
- No GitLab CI template or Homebrew formula. (`pip install project-mri`, `pipx`,
  `scripts/install.sh`, the `Dockerfile` + `deploy/docker-compose.yml`, and the
  `.github/action/` composite Action all exist.)
- Actual **publish/launch is owner-gated**: PyPI/TestPyPI upload, a pushed
  container image, and the production domain wait on the owner's decision and
  credentials. The artifacts are release-ready (see [PACKAGING.md](PACKAGING.md)).

## Definition of done, for any item above

1. Type checks and lint pass.
2. The change was exercised — a test, a dev server, or both. "It reads
   correctly" is not evidence.
3. A security and a performance pass over the change, with findings either
   fixed or declined in writing with a measurement.
4. No accuracy claim ships without the number behind it.
