# ADR-007 — DuckDB is deferred, not adopted

- **Status:** Accepted
- **Date:** 2026-07-19
- **Supersedes:** nothing. Refines the "optional DuckDB mirror" note in [ADR-001](ADR-001-stack.md).

## Context

ADR-001 left the door open to DuckDB as a rebuildable analytics mirror alongside
the authoritative SQLite file. The fusion data model ([migration 0002]) is where
that door either gets used or gets closed: the consequence loop is the only part
of the product with genuinely analytical queries — rolling windows over metric
history, ranking decisions by their measured effect, weighted aggregates across
a file's whole timeline.

The honest question is not "is DuckDB faster at OLAP" — it is, that is what it
is for. The question is whether SQLite is *too slow at the queries this product
will actually run*, at the scale a single repository will actually reach. A
second storage engine costs a dependency, a second file, a rebuild path, a
divergence failure mode, and a second dialect for every future contributor to
learn. That price is worth paying only against a measured problem.

## Measurement

SQLite 3.50.4, WAL, `synchronous=NORMAL`, on the 0002 schema. The dataset is
deliberately larger than realistic: 20,000 decisions and 120,000 consequences
across 2,000 files. A repository that produced 20,000 mined decisions would be
extraordinary; the intent is to over-estimate and see whether it still holds.

Load: 3.84 s. Database size: 32.8 MB. Best of three runs per query:

| Query (the shapes layer 8 needs) | Time |
|---|---|
| Rolling metric trend per file — `avg() OVER (PARTITION BY … ROWS BETWEEN 4 PRECEDING …)` | **72 ms** |
| Rank decisions by measured effect — join + `GROUP BY` + `rank() OVER` | **517 ms** |
| Metric distribution over time — monthly rollup across four metrics | **102 ms** |
| Worst files by confidence-weighted delta — `GROUP BY` + `HAVING` + sort | **454 ms** |

Window functions have been in SQLite since 3.25; the version this project pins
has them, and all four queries are expressible with no dialect gymnastics.

## Decision

**Do not add DuckDB.** SQLite answers every analytical query the fusion layers
need in well under a second at more than the realistic ceiling, and the whole
dataset is 33 MB. There is no measured problem for a second engine to solve.

## Consequences

- One file remains the whole product's state, which is the local-first promise
  in [ADR-003](ADR-003-product-shape-local-first.md) rather than an
  implementation detail.
- One dialect. Contributors write one kind of SQL, and the migration runner in
  [ADR-005](ADR-005-schema-migrations.md) stays the only schema mechanism.
- No mirror means no divergence: there is no state where the analytics answer
  disagrees with the authoritative store.

## When to revisit

This is a deferral with a trigger, not a permanent refusal. Reopen it if any of
the following is *measured*, not assumed:

1. A dashboard query on real data exceeds ~2 s and cannot be fixed by an index
   or a materialized rollup table.
2. Cross-repository analytics ship — comparing many repositories at once is a
   genuinely different scale from the single-repo case measured here.
3. The consequence loop grows queries SQLite cannot express, rather than
   queries it merely runs slowly.

Until one of those is on the table with a number attached, adding DuckDB would
be buying a solution ahead of the problem.

[migration 0002]: ../../src/mri/db/migrations/0002_fusion_model.sql
