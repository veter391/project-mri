# Architecture Decision Records

Why the project is built the way it is. Each record states the context, the
decision, and what it costs — including decisions that were later superseded.

| ADR | Decision | Status |
|---|---|---|
| [001](ADR-001-stack.md) | Language and framework stack | Accepted |
| [002](ADR-002-license-mit-forever.md) | MIT forever, zero paid gating | Accepted |
| [003](ADR-003-product-shape-local-first.md) | Local-first, self-hosted product shape | Accepted |
| [004](ADR-004-repo-structure-workflow-stack.md) | Repo structure, workflow, and web stack | Accepted, amended |
| [005](ADR-005-schema-migrations.md) | Schema migrations for the local SQLite database | Accepted |
| [006](ADR-006-oss-adoption.md) | Which libraries we adopt, and which we do not | Accepted |
| [007](ADR-007-duckdb-deferred.md) | DuckDB is deferred, not adopted | Accepted |
| [008](ADR-008-authorship-line-shares-deferred.md) | Authorship line-shares: deferred, then resolved via 5.2 | Resolved |
| [009](ADR-009-cursor-aider-ingest-deferred.md) | Cursor/aider ingest deferred until real logs exist | Accepted |
| [010](ADR-010-git-notes-provenance-deferred.md) | git-notes/Agent Trace deferred; commit trailers are the verifiable slice | Accepted |

## Conventions

- One decision per record, numbered sequentially, never renumbered.
- A record is never deleted. When a decision changes, mark the old one
  superseded and link forward.
- When the implementation deviates from an accepted record, amend the record in
  the same change that introduces the deviation. An undocumented deviation is a
  defect, not a shortcut.
