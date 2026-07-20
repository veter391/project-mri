# ADR-012 — Mining a decision's "why" from agent reasoning is deferred; citation-linking of stored reasoning is the verifiable slice

- **Status:** Accepted
- **Date:** 2026-07-20
- **Relates to:** the plan's Phase 7.2 ("session-reasoning mining"), the decision
  layer (`src/mri/fusion/decisions.py`, sources `adr` and `commit`), the opt-in
  content store (`session_events.content`, `store_content`), and
  [ADR-009](ADR-009-cursor-aider-ingest-deferred.md) /
  [ADR-010](ADR-010-git-notes-provenance-deferred.md) (same rule: a miner ships
  only for signal validated on real data).

## Context

Phase 7.2 asks the fusion layer to recover *why* an agent made a change from the
reasoning in its session log, and attach that rationale to the decision the
change implements. The raw material exists: when a user opts in with
`store_content`, `session_events.content` holds the assistant's message text
(`ingest/claude_code.py:_text_of`). Decisions today carry a rationale only when
one is explicit — an ADR's "Decision" section, or a commit body — and leave it
null otherwise (`decisions.py`), which is the project's honesty rule for the
"why": recovered, never invented.

Agent reasoning is free-form prose. Turning it into "the reason for this change"
is **inference**, and two hard constraints apply:

1. **No validated corpus.** There is no labelled set of (reasoning → true
   rationale) pairs on this machine to measure a miner against. The Definition
   of Done forbids shipping an accuracy claim without the number behind it, and
   a "why" extracted from prose is precisely such a claim. This is the same
   blocker that deferred the Cursor/aider parsers (ADR-009) and the git-notes
   schema (ADR-010): the source is real, the *validated* extraction is not.

2. **Fabrication risk is the product's core failure mode.** A summariser that
   condenses an agent's monologue into a crisp "why" will produce a fluent,
   plausible sentence whether or not it reflects a real decision. That is the
   exact over-claim the decision layer, the consequence loop, and the eval guard
   are all built to prevent. A wrong "why" that reads convincingly is worse than
   an honest null.

3. **Privacy gate.** Reasoning text is retained only under an explicit opt-in
   because logs can hold secrets. Any 7.2 feature is dormant for the default
   install, so it cannot be a load-bearing part of the moat.

## Decision

**Defer free-form reasoning-to-rationale mining** until there is a validated
corpus to measure extraction accuracy against and a way to express its
confidence honestly (a recovered-vs-inferred flag, never a bare sentence). This
is a measurement-grounded deferral, not a rejection — the agent's stated intent
is genuinely valuable provenance.

**Build the verifiable slice first, when 7.2 is picked up:** deterministic
**citation-linking**. When content is stored, scan a session's reasoning for
explicit references to decisions the project already records — an `ADR-\d+`
identifier (a pattern this repo defines and uses) or an issue key — and link the
session to that decision as corroborating provenance ("the agent that did this
work cited ADR-007 in session X"). This is an exact-match citation, not an
inference: it adds no new decision and invents no rationale, it only records that
a stored reasoning turn named an existing one. It is testable without a labelled
corpus (the reference either appears in the text or it does not) and stays inside
the honesty rule.

## Consequences

- The decision layer keeps its guarantee: a rationale is present only when it was
  explicitly stated, never summarised into existence.
- 7.2's high-value part (the agent's intent behind a change) is named and scoped,
  not silently dropped — a future pick-up starts from the citation slice and adds
  free-form mining only behind a validated accuracy number and a confidence flag.
- No code ships here; the roadmap moves 7.2 from an open plan item to a deferral
  with its buildable slice named, matching ADR-009 and ADR-010.

## When to revisit

When `store_content` is in real use and a corpus of stored reasoning exists to
inspect: build the citation-linking slice first (deterministic, testable now),
and only attempt rationale extraction once there is a labelled set to calibrate
it against and the eval guard is extended to cover a fabricated-why check.
