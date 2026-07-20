# ADR-011 — Provenance is not folded into the risk score; authorship-weighted risk is a bounded triage signal

- **Status:** Accepted
- **Date:** 2026-07-20
- **Relates to:** the plan's Phase 6.1 ("compose the fusion signals into the
  per-file risk score"), [ADR-008](ADR-008-authorship-line-shares-deferred.md)
  (authorship-weighted risk, whose "complementary signal" this wires live), and
  the over-claim guard (`src/mri/eval/guard.py`).

## Context

Phase 6.1 was written as "fold the fusion signals — AI-authorship share,
decision density, consequence volatility — back into the analyzer layer's
per-file risk score, so the headline number reflects provenance." Taken
literally that is an over-claim, and the eval guard exists to catch exactly this
class of it.

A file's base risk today is `MAX(findings.score)` per path from the latest scan
(`repository.top_risk_files`) — a composite of static and git-history signals the
analyzers produce. **AI-authorship is neutral provenance, not a risk factor.**
Folding an AI-authored percentage into the risk number asserts "AI-written code
is riskier," which nothing here has measured and which the product explicitly
refuses to claim. Decision density and consequence volatility are likewise not
risk multipliers: a file with many recorded decisions is well-documented, not
dangerous, and consequence measurement is already capped (`confidence ≤ 0.6`)
and noise-gated (`|delta| < 1.0` claims nothing).

The honest form of "composition" was in fact already shipped: `explain_file`
surfaces base risk, authorship, sessions, decisions and consequences as
**separate, evidence-backed factors**, and never lets any of them alter the base
risk number. Conflating them into one score would destroy that separation.

There was one loose end. ADR-008 promised an authorship-weighted risk as "the
complementary, lighter signal" — `weighted_risk = base_risk × evidence_strength`,
documented as strictly ≤ base_risk ("marks where a file's risk sits, does not
amplify it"). It shipped as `weight_hotspots` with a full, honesty-focused test
suite, but was never wired into any surface: tested dead code, which the
Definition of Done forbids.

## Decision

**Do not recompose the base risk score with provenance.** Base risk stays the
analyzers' `MAX(findings.score)`. AI-share, decision density and consequence
volatility are reported as their own factors and never fold into it. Phase 6.1's
literal framing is rejected as an over-claim, not deferred — there is no version
of "AI-authorship raises risk" this project would ship.

**Wire the one honest composition that ADR-008 already defined**, and make its
tested primitive live:

- `explain_file` now emits a `weighted_risk` factor when a file has base risk and
  agent write evidence: "about N of that risk sits under agent-modified code —
  correlation, not blame." It is `base_risk × evidence_strength`, bounded ≤ base
  risk, omitted when it rounds to zero (no evidence to weight is not a fact worth
  stating). All three surfaces (CLI, HTTP, MCP) get it, since all call
  `explain_file`.
- Every surface orders the files it explains by that weighted risk — the fusion
  pipeline (CLI, MCP) and the HTTP route alike — so the moat view leads with the
  file whose risk most sits under agent-modified code, and the same project shows
  the same leading file whichever surface asked. Files with no such evidence are
  kept, ordered last, never dropped — the top-N selection was already made
  upstream by `top_risk_files`.
- The formula lives in one place, `weighted_risk_of`, shared by the per-file
  explanation and the batch `weight_hotspots` ordering, so the ≤-base invariant
  cannot drift between them.

## Consequences

- The headline risk number keeps meaning one thing — what the analyzers measured
  — and is never inflated by who wrote the code.
- The moat gains a genuine triage signal (which risky file is most agent-
  attributable) without a new claim: it is a bounded restatement of two numbers
  the reader can already see, labelled correlation.
- `weight_hotspots` and its test suite now guard a live path; the dead-code
  liability is gone.
- The eval guard's invariants are untouched — shares still sum to 100, no
  confidence reaches 1.0, no path emits causation, and the weighted figure never
  exceeds the base it is derived from.

## When to revisit

If a measured, validated relationship between a fusion signal and defect rate
ever exists — e.g. consequence volatility shown to predict regressions on a
labelled corpus — that signal could earn a place in the base score, as a
weighted term with the measurement behind it and the eval guard extended to
cover it. Until such a number exists, provenance stays a reported dimension, not
a risk multiplier.
