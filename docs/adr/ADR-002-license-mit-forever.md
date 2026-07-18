# ADR-002 — MIT License, Forever, Zero Paid Gating

- **Status:** Accepted
- **Date:** 2026-07-10
- **Deciders:** MRI core

## Context

MRI's positioning is not "no rival per feature" — that claim is false and we reject it. The honest, defensible position is that MRI is **the only complete, trustworthy, free, self-hostable system that closes the whole loop**: session-log-native AI attribution → authorship-decomposed risk → decision provenance → guardrailed consequence loop → human + agent surfaces.

The closest rival, **Repowise**, is **AGPL + paid**, attributes AI code from **git metadata only** (no session logs), and has **no consequence loop**. Two of MRI's three defensible wedges are therefore about *trust and openness*, not just features: (2) the decision→consequence loop, and (3) **true MIT-forever + zero-telemetry + full explainability**. A copyleft or open-core-with-paid-tier license would directly dissolve wedge (3) and make MRI indistinguishable in kind from the incumbent it is positioned against.

MRI's manifesto — "open core forever" — is a product commitment, and license is how that commitment becomes enforceable rather than aspirational.

## Decision

- License **the entire core** — backend, analyzers, CLI, dashboard, MCP server, report generator, CI integrations — under **MIT**, permanently.
- **No paid gating** of any kind: no feature held back, no "enterprise" tier inside the core repo, no open-core split where the interesting analysis lives behind a wall.
- **Zero telemetry:** no analytics SDK, no phone-home, no usage beacon anywhere in the core.
- The public **demo/marketing site is a separate app**; it may carry its own concerns, but it can never gate or instrument the self-hostable core.

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| **AGPL** (Repowise's choice) | Copyleft deters the exact audience — companies self-hosting a code-intelligence tool internally — and signals an eventual paid-license upsell. It contradicts "open core forever" and hands the incumbent a same-category defense. |
| **Open-core with a paid/enterprise tier** | The moment the differentiating analysis (consequence loop, session attribution) sits behind a paywall, wedge (3) collapses and MRI becomes "another freemium tool." |
| **BSL / source-available with time-delayed OSS** | Not free, not trustworthy-by-default; the delay and commercial-use restrictions undermine the local-first, no-strings promise. |
| **Apache-2.0** | Acceptable and permissive, but MIT is shorter, more universally understood, and already the stated locked choice; no patent-grant need here outweighs the simplicity. |

## Consequences

**Positive**
- Wedge (3) — true MIT-forever + zero-telemetry + full explainability — becomes a *provable* differentiator against AGPL-and-paid rivals, not a marketing line.
- Maximum adoption surface: companies can self-host internally with zero legal review friction.
- Aligns the license with the manifesto so the two cannot drift apart.

**Negative / trade-offs**
- **No direct license revenue** from the core; any future monetization must come from adjacent, clearly-separated offerings (e.g. a hosted convenience service) that never gate or instrument the OSS core.
- MIT permits closed-source forks/repackaging by others; accepted as the cost of maximal openness. The moat is the *live loop, the data model, and the trust posture*, not license restriction.
- Contributions must be accepted under terms compatible with permanent MIT (clear inbound=outbound), requiring a stated contribution policy.
