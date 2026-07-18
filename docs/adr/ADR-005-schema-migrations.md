# ADR-005 — Schema migrations for the local SQLite database

**Status:** Accepted · 2026-07-18

## Context

The database lives on each user's own disk. An upgrade happens when someone runs
`pip install -U project-mri` and starts the tool again — there is no server-side
migration window, no operator, and no way for us to fix a botched migration
remotely.

Until now there were no migrations at all. `get_connection` re-ran the whole
`schema.sql` on every connection, and every statement in it was
`CREATE TABLE IF NOT EXISTS`. That silently no-ops against an existing table, so
any column added in a future release would simply never appear on an
already-installed user's database, and queries would fail at runtime. `mri
upgrade` printed `"no migrations needed for v0.3.x"` unconditionally. The next
phase adds roughly six tables, so this had to be solved first.

## Decision

A small hand-rolled runner in `src/mri/db/migrator.py`. Plain `.sql` files in
`src/mri/db/migrations/`, applied in filename order, recorded by name in a
`schema_migrations` table.

**Why not a library.** `alembic` requires SQLAlchemy and Mako, which would land
on every user of a tool that otherwise uses raw `aiosqlite` — and it is designed
as a developer-run deploy step. `yoyo-migrations` has not released since August
2024 and would put four bookkeeping tables in a user's personal database.
`sqlite-migrate` is deprecated in favour of `sqlite-utils` 4, which is the one
genuinely tempting option: its `migrations.apply(db)` is explicitly documented
for embedding in end-user applications and Simon Willison has run that pattern in
`llm` for years. It was rejected only because it pulls click, tabulate, pluggy
and dateutil in as runtime dependencies for something we invoke once per release.
Six tables over several releases does not justify that.

**Why a tracking table rather than `PRAGMA user_version`.** `user_version` is a
legitimate, SQLite-endorsed mechanism and would be sufficient for a linear
single-author history. The table was chosen because it keeps an audit trail with
timestamps, tolerates migrations landing out of order, and leaves room for the
planned analyzer plugins to own their own migration sets — none of which a single
integer can express. It is one extra table.

## Consequences and the hazards this had to handle

Each of these was verified against SQLite and CPython directly, not assumed:

- **`executescript` cannot be used.** Python's `sqlite3.executescript` issues an
  implicit COMMIT before running. Inside our explicit transaction it ended it, and
  a DDL statement then survived an explicit ROLLBACK — the atomicity guarantee
  would have been a fiction. The runner splits statements with
  `sqlite3.complete_statement` and executes them one at a time.
- **`PRAGMA foreign_keys` is ignored inside a transaction.** Confirmed: toggling
  it after `BEGIN` left the value unchanged. It is therefore only ever set on the
  connection, before any transaction. Relevant when a future migration needs the
  12-step table rebuild that SQLite requires for anything `ALTER TABLE` cannot do.
- **DDL is transactional in SQLite**, so each migration and its tracking row
  commit together. A failure rolls back both and leaves the migration pending for
  retry rather than half-applied and recorded.
- **Concurrency.** The CLI and the server can start simultaneously. Each
  migration opens `BEGIN IMMEDIATE`, which takes the write lock up front, and
  re-reads the applied set *inside* that lock. The loser finds the work already
  done and does nothing. Verified with four concurrent runners: applied exactly
  once, no errors. No lock file is used — SQLite's own write lock is the mutex.
- **Existing v0.3.x databases** contain the tables but no tracking table. The
  runner detects this and records the baseline as applied instead of re-running
  it, leaving user data untouched.

`schema.sql` is deleted; its contents are now `0001_initial_schema.sql`. Keeping
both would have been two sources of truth that drift apart.

## Follow-ups

- The 12-step rebuild procedure is not implemented, because nothing needs it yet.
  The first migration that must change a column type or drop a constraint should
  either implement it carefully or revisit `sqlite-utils` for `table.transform()`.
- Migrations are forward-only. There is no `downgrade`; on an end-user machine
  the recovery path is restoring a backup (`mri backup`/`mri restore`).
