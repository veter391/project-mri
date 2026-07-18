# Architecture Decision Records

Why the project is built the way it is. Each record states the context, the
decision, and what it costs — including decisions that were later superseded.

| ADR | Decision | Status |
|---|---|---|
| [001](ADR-001-stack.md) | Language and framework stack | Accepted |
| [002](ADR-002-license-mit-forever.md) | MIT forever, zero paid gating | Accepted |
| [003](ADR-003-product-shape-local-first.md) | Local-first, self-hosted product shape | Accepted |
| [004](ADR-004-repo-structure-workflow-stack.md) | Repo structure, workflow, and web stack | Accepted, amended |

## Conventions

- One decision per record, numbered sequentially, never renumbered.
- A record is never deleted. When a decision changes, mark the old one
  superseded and link forward.
- When the implementation deviates from an accepted record, amend the record in
  the same change that introduces the deviation. An undocumented deviation is a
  defect, not a shortcut.
