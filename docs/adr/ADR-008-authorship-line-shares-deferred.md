# ADR-008 — Per-file authorship line-shares are deferred; risk is weighted by evidence instead

- **Status:** Accepted
- **Date:** 2026-07-19
- **Relates to:** [ADR-007](ADR-007-duckdb-deferred.md) (the fusion layers),
  migration [0002] (`authorship_shares`), the session ingest.

## Context

The product's signature claim is per-file authorship decomposition: of a file's
content, how much is AI-authored, how much human, how much unknown. Migration
0002 built `authorship_shares` for exactly this, with a constraint that the
three shares sum to 100 and `unattributed` is first-class.

The session ingest now populates `session_file_touches`: a record, per file,
that an agent tool reported reading or writing it, at an instant, with a
confidence below one. The obvious next step is to turn those touches into the
line-shares the table was built for. Before building it, the correlation it
would rest on was measured.

## Measurement

A line's authorship could, in principle, be attributed by taking `git blame`
(which gives each current line its authoring commit and time) and asking whether
that time falls inside a window when an AI session was active on the file. That
only works if a session's window is tight enough to mean something.

It is not. On this machine's real logs:

- Session windows, measured `started_at` → `ended_at`, span **10 days to two
  months**. Claude Code appends to one log file across many days, so a
  session's "window" is the life of the log, not an editing burst.
- A commit's authored time routinely lags the edit that produced it — the agent
  writes, the human commits later, sometimes days later.

Attributing every line whose commit falls in a 10-day-to-2-month window to AI
would mark almost the entire recent history as AI-authored. That is precisely
the inflated, indefensible number this product exists not to emit.

The tighter signal that *does* exist — a touch's own `occurred_at`, at the
instant of the tool call, on a named file — records **that** the agent modified
the file, not **which lines** survive in the current version. A `Write`
replaces a whole file; an `Edit` changes a span; subsequent human edits erode
both. Reconstructing current-line provenance from that would require replaying
every edit against the working tree, and the content needed to do it is not
retained by default because it contains secrets.

## Decision

**Do not populate `authorship_shares` with line-share percentages yet.** A
number that cannot be defended is worse than an absent one, and the schema's own
honesty constraints are there to stop it being written.

Ship, instead, **authorship-weighted risk** (`src/mri/fusion/authorship.py`): a
per-file *evidence strength* — the strongest single write touch, 0..1 — used to
weight the risk a scan already computed. It answers a narrower question
truthfully ("there is evidence, at this strength, that an agent modified this
risky file") rather than a broader one falsely ("this fraction of the file is
AI").

`authorship_shares` stays in the schema, unpopulated, for when the correlation
below exists.

## Consequences

- The `ai_influence` number surfaced to users is grounded in a tool's own
  report of writing a file, with a confidence that is never 1.0, and never
  claims a line count it cannot support.
- `share_human` is never emitted. Absence of an AI touch is absence of evidence,
  which is `unattributed` — the distinction the table was built to preserve.
- The weighted risk is never larger than the base risk. Authorship evidence
  marks where a file's risk sits, it does not amplify it.

## When to revisit

Populate `authorship_shares` with real line-shares once **commit-level
attribution** exists: linking a session to the specific commits it produced (by
matching a commit's changed-file set against the session's write touches within
a tight grace window, not by the session's whole span), then blaming current
lines to those attributed commits. That is a defensible content share and is the
natural home for the `commit_sha` columns and `idx_*_commit` indices already
carried by 0002. It is a block of its own, and it is not this one.

[0002]: ../../src/mri/db/migrations/0002_fusion_model.sql
