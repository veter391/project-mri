# ADR-003 — Product Shape: Local-First, Two Faces

- **Status:** Accepted
- **Date:** 2026-07-10
- **Deciders:** MRI core

## Context

MRI analyzes source history, AI session logs from `~/.claude` and `~/.cursor`, git-notes, and CI metrics — some of the most sensitive artifacts an organization owns. The product must be trustworthy enough that a developer or a security-conscious company runs it against a private repo without hesitation. That trust is incompatible with a cloud-first, upload-your-repo model.

At the same time, MRI needs a public presence to communicate its (genuinely real) demand thesis — "comprehension debt" (Addy Osmani), the OCaml project rejecting a 13k-line AI PR nobody could review, CloudBees' 2026 "81% more prod issues from AI code" — and to let people evaluate it before self-hosting.

These two needs pull in opposite directions: the trustworthy tool must be fully local and hold nothing back, while the evaluation surface must be public and inevitably limited. The existing assets already lean local-first (SQLite store, static vanilla-TS dashboard, CLI), and the P1 audit exposed exactly the places where local-first discipline had slipped (H2 unauthenticated default, H3 unsandboxed clone).

## Decision

Ship **two faces** from one core:

1. **Full self-hostable OSS** — the complete product: dashboard + backend + CLI + MCP server + report generator + CI gate. **Nothing is held back.** It runs entirely on the user's machine, needs no network egress, uses no telemetry, and stores everything in a single SQLite file. This is the primary, trustworthy artifact.
2. **Public multi-page demo site** — a **separate** app: marketing, docs, a **limited** live demo, and a prominent GitHub link. It exists to explain and evaluate, never to run anyone's private data.

Local-first discipline is enforced, not assumed:
- **Secure-by-default (H2):** any non-loopback bind requires auth (argon2-cffi via `security.py` / `api/auth`). The default/containerized deploy is never unauthenticated.
- **Sandbox + quota (H3):** repo clone is URL-allow-listed, sandboxed, and quota-bounded, with `GIT_TERMINAL_PROMPT=0`; clone lifecycle tracking is restored (H5 async-context-manager fix).
- **No Node at runtime:** the dashboard ships pre-built and is served statically by FastAPI, so self-hosting is a single Python process.

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| **Cloud-first / hosted SaaS** | Requires uploading repos and session logs — fatal to the trust posture and to local-first. Directly contradicts the manifesto and the target audience's constraints. |
| **Single app for both faces** (marketing + tool in one deploy) | Couples marketing dependencies and a public attack surface to the self-hostable core; makes the trusted artifact heavier and harder to audit. Separation keeps the self-host bundle lean and its trust boundary clean. |
| **Local tool with an optional cloud sync** | Any always-available sync path re-introduces egress and telemetry risk and muddies the zero-telemetry promise. Deferred entirely; if ever built, it must be an opt-in, clearly-separated adjacent product. |
| **Full product public online with no self-host** | Removes the defining wedge (local-first, private-by-construction) and turns MRI into a category peer of the cloud rivals it is positioned against. |

## Consequences

**Positive**
- The trustworthy artifact and the marketing artifact evolve independently, at their own cadences and with independent risk surfaces.
- Self-hosting is genuinely private-by-construction: no egress, no telemetry, one process, one file.
- The audit backlog's highest-severity items (H2, H3, H5) become *shape requirements*, not optional hardening — local-first is enforced in code.

**Negative / trade-offs**
- Two codebases/deploys to maintain (core in Python, site in TS/pnpm); accepted as the cost of a clean trust boundary.
- The public live demo is necessarily **limited**, so it under-represents the full product; mitigated by clear "this is a limited demo — self-host for the complete system" messaging and a prominent GitHub link.
- Secure-by-default adds first-run friction for non-loopback deployments (credentials required); accepted, and softened by keeping loopback-only local use frictionless.
