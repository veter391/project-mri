# ADR-001 — Technology Stack

- **Status:** Accepted
- **Date:** 2026-07-10
- **Deciders:** MRI core

## Context

MRI is a local-first, MIT-forever, explainable, agent-native codebase-intelligence system. It must run fully offline on a developer laptop, keep every emitted claim traceable to a stored fact, hold ~70% of an existing codebase (`backend/mri/**`, `dashboard/`, `ts/`) without a rewrite, and avoid any dependency whose license or ownership could compromise the open-core promise. The remaining work is mostly *fusion glue* — session-log ingest, provenance normalization, decisions/consequence tables, an MCP server, authorship-weighted risk — not net-new infrastructure.

The stack must therefore favor **reuse of mature OSS**, a **single local runtime**, and **an embeddable, inspectable store**.

## Decision

- **Backend:** Python 3.12+ with **FastAPI**, serving the JSON API, the static dashboard, and the MCP server from one process.
- **CLI:** Click/Typer + Rich for typed commands and explainable terminal output.
- **Store:** SQLite (via aiosqlite) as primary; **optional** DuckDB as a rebuildable temporal-analytics mirror.
- **Adopted OSS:** PyDriller (git mining), py-tree-sitter + tree-sitter-language-pack (polyglot AST), lizard (multi-language complexity), grimp + import-linter (Python coupling contracts), NetworkX (graphs), argon2-cffi (auth hashing), limits (rate limiting).
- **Frontend:** keep the vanilla-TS terminal-aesthetic dashboard, pre-built to static assets served by FastAPI (no Node at runtime). The public demo/marketing site is a **separate** app.
- **Packaging:** uv/pipx for the Python CLI (uv **dev-time only**, with a documented pip fallback); pnpm for the site.

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| **Node/TypeScript backend** | The strongest git-mining and polyglot-AST libraries are Python-native. A TS backend would force reimplementation or fragile FFI, and would not remove Node from the self-host path anyway. |
| **Client/server database (Postgres/MySQL)** | Requires a running server and operational surface — a direct violation of local-first. SQLite is a single file the user can copy, inspect, or delete. |
| **DuckDB as primary store** | Excellent for OLAP, weaker as a transactional single-writer store for the ingest path. Used as an optional mirror instead; SQLite stays authoritative. |
| **SPA framework (React/Vue) for the dashboard** | Adds a Node runtime and a large dependency tree to the self-host bundle for a UI that is intentionally terminal-minimal. Vanilla TS pre-built to static assets is smaller and Node-free. |
| **Hand-rolled git miner / complexity engine** | Re-solves solved problems. MRI's value is the fusion layer; PyDriller and lizard are adopted so effort goes into the wedge. |
| **uv as a runtime requirement** | uv is OpenAI-owned; making it mandatory imports an ownership dependency. Kept dev-time only with a pip fallback. |

## Consequences

**Positive**
- Self-hosting needs **no Node runtime**; the whole store is one SQLite file.
- ~70% of the existing codebase is retained; new effort concentrates on the differentiating fusion layer.
- One FastAPI process serves humans (API/dashboard/report) and agents (MCP) — one auth surface, one port.
- Explainability is preserved because every adopted library outputs facts we persist, not opaque scores.

**Negative / trade-offs**
- Python's packaging story is imperfect; mitigated by pipx isolation and a documented pip fallback.
- The uv caveat must be documented on every install path so no user is silently steered onto an OpenAI-owned tool.
- Optional DuckDB adds a second (rebuildable) file for users who enable temporal analytics; kept strictly derived to protect the single-file guarantee.
- Adopting PyDriller means correcting its aggregation at our boundary (the H1 deletion double-count is fixed in MRI's own churn logic, not upstream).
