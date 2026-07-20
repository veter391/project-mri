# ADR-010 — git-notes / Agent Trace provenance is deferred; commit trailers are the verifiable slice

- **Status:** Accepted
- **Date:** 2026-07-20
- **Relates to:** the session ingest (`src/mri/ingest/`), the plan's Phase 5.3
  ("consume external provenance signals: Agent Trace and git-ai git-notes"),
  and [ADR-009](ADR-009-cursor-aider-ingest-deferred.md) (same rule, different
  source).

## Context

Phase 5.3 asks the ingest to consume two external provenance sources as a
higher-trust signal than session-log correlation: **git-ai git-notes** and
**Agent Trace** records. Both attach explicit authorship metadata to commits, so
where present they beat the timestamp/touch correlation the fusion layers infer.

The rule this project holds itself to — a parser ships only for a format
inspected on real data — applies here as it did to Cursor and aider. The git
*mechanism* for notes is well understood and testable (a note can be created
with `git notes add` and read back), but the **content schema** git-ai and Agent
Trace write into those notes is not something there is a real sample or an
authoritative, verified spec for on this machine. Parsing a guessed schema would
produce authorship numbers nobody has checked against the tool that wrote them —
the exact dishonesty the design refuses, and the reason Cursor/aider were
deferred in ADR-009.

## Decision

**Defer the git-ai and Agent Trace note parsers** until a real note written by
each tool is available to inspect and to build a fixture from. This is a
scheduling deferral grounded in the missing verified format, not a rejection:
the sources are genuinely higher-trust and worth having.

**Build the verifiable slice first, when 5.3 is picked up:** commit-message
**trailers** are a documented git convention (`git interpret-trailers`), are
inspectable and testable without any proprietary tool, and already carry
declared authorship in the wild — `Co-Authored-By:` naming an AI tool, and
tool-specific `Assisted-By:` / `Generated-By:` lines. A trailer parser reads a
*declared* (not inferred) authorship source into the same `authorship_shares`
pipeline, at a higher confidence than session correlation, and can be written
against real commits we create in a fixture. That is the honest, testable core
of "higher-trust external provenance"; the proprietary note formats layer on
once a real sample exists.

Note: this project's own commits carry no AI attribution (a hard rule), so its
own history is not a fixture for trailer parsing — the fixture is a synthetic
repo whose commits deliberately carry trailers, which is exactly how such a
parser should be tested anyway.

## Consequences

- Phase 5.3's acceptance criterion (git-notes + Agent Trace) is **not** met, and
  this ADR is the honest record of why, not a silent gap. Phase 5 remains
  partially complete by design.
- The fusion layers already model a `source` per session and a `method` per
  authorship share and a `confidence` throughout, so a declared-authorship
  source is additive: it raises confidence where it exists and changes nothing
  where it does not.
- No authorship is ever fabricated from a note format we have not verified. A
  repo using git-ai simply gets the session-correlation signal until the
  verified parser lands.

## When to revisit

Two independent triggers, either one:
1. A real git-ai or Agent Trace note can be captured and inspected — then build
   that parser against a checked-in fixture.
2. Sooner and unconditionally buildable: implement the commit-trailer parser
   (`Co-Authored-By` / `Assisted-By` / `Generated-By`), tested against a
   synthetic repo, as the first, verifiable half of Phase 5.3.
