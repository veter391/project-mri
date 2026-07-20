# ADR-009 — Cursor and aider ingest are deferred until we have real logs to test against

- **Status:** Accepted
- **Date:** 2026-07-20
- **Relates to:** the session ingest (`src/mri/ingest/`), the plan's Phase 5.1
  ("a session-log reader for `~/.claude` and `~/.cursor`").

## Context

The rebuild plan's Phase 5.1 asks for a session-log reader covering both
Claude Code (`~/.claude`) and Cursor (`~/.cursor`), and the vision names aider
and git-notes as further provenance sources. Claude Code shipped, written and
validated against a real 21,750-record log on this machine and a second one
whose edits could be checked by hand. Cursor and aider have not.

The rule this project holds itself to is that a parser ships only for a format
inspected on real data. The numbers these parsers feed — authorship shares,
consequence deltas — are the product; a parser written against documentation,
for a tool whose output we cannot run, would produce attribution nobody has
verified. That is exactly the dishonest number the whole design refuses.

On this machine: `~/.cursor` exists but its session-log format has not been
examined on a real, non-trivial log, and aider is not installed at all, so
there is no sample to write against or test with. Guessing a schema, shipping a
parser, and generating attribution from it would violate the "no guessing,
written against real logs" rule the Claude Code parser was held to.

## Decision

**Defer Cursor and aider ingest** until a real log from each is available to
inspect and to build a fixture from. Claude Code ingest stands on its own — most
of the intended audience uses it, and the fusion layers above are source-
agnostic, so adding a source later is additive, not a rewrite.

The ingest package is already shaped for this: `ingest/claude_code.py` is one
parser behind a `SOURCE` constant and a normalised `ParsedSession`, and
`sessions.source` records which tool produced each row. A second parser is a new
module plus a fixture, not a change to anything downstream.

## Consequences

- Phase 5.1's "both stores" acceptance criterion is **not** met, and this ADR is
  the honest record of why, rather than a silent gap. The plan's Phase 5 is
  therefore partially complete by design, not by oversight.
- No attribution is ever produced for a Cursor or aider session, which is the
  correct failure: absence, not a guessed number. A user on those tools sees no
  fabricated AI-authorship, and `sessions.source` makes the coverage legible.
- git-notes / Agent Trace ingest (Phase 5.3) is a separate, still-open item —
  those are documented, testable formats, so they are deferred on scheduling,
  not on the missing-sample grounds here.

## When to revisit

Build the Cursor parser the moment a real Cursor session log can be captured on
a machine we control — inspect it the way `session-log-formats.md` documents for
Claude Code, check a fixture into `tests/`, and only then ship the parser. Same
for aider once it is installed and has produced a real log.
