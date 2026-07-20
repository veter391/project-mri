# ADR-014 — The MCP surface is stdio-transport, not a networked FastAPI service

- **Status:** Accepted
- **Date:** 2026-07-21
- **Relates to:** the plan's Phase 9.5 / Master Phase 4 ("MCP server … FastAPI-
  served … auth-gated … unauthenticated calls rejected"), `src/mri/mcp_server.py`,
  the `mri mcp` command, and the HTTP fusion route
  (`src/mri/api/routes/fusion.py`).

## Context

Phase 9.5 specified the agent-native surface as a **FastAPI-served** MCP endpoint
that is auth-gated, rate-limited, and rejects unauthenticated calls. That framing
predates how coding agents actually consume MCP today: Claude Code, Cursor and
the like **spawn the server as a subprocess and speak over stdio**, not over a
network socket. There is no listening port to authenticate, rate-limit, or
expose.

The shipped surface (`mri mcp`) uses the SDK's **stdio transport**. It exposes
five read/compute tools — `fuse_project`, `explain_file`, `get_authorship`,
`get_decisions`, `get_consequences` — over the same audited fusion layers the
CLI and HTTP surface use.

## Decision

**Keep stdio as the MCP transport, and treat the plan's "auth-gated / rate-
limited / unauth-rejected" language as not applicable to it** — those are
properties of a *network listener*, and a stdio server has none. Security for the
stdio surface is the OS process boundary: it runs as, and with the reach of, the
user who launched it, exactly like the `mri` CLI. The read tools never write
(they look a project up and answer "no evidence" when absent), and `fuse_project`
validates its path — both already covered by tests.

**The networked case is already served, auth-gated, elsewhere.** Remote/dashboard
consumers read the same stored fusion result through
`GET /api/projects/{id}/fusion`, which sits behind the global `AuthMiddleware`
(ADR-013's posture). So the intent behind 9.5's "auth-gated" — no unauthenticated
network access to fusion data — holds; it is simply the HTTP surface that carries
it, not the MCP one.

## Consequences

- The agent-native surface matches how agents integrate in practice (subprocess
  over stdio), with no network attack surface to harden.
- Phase 9.5 / Master Phase 4 hardening reduces to: **tool-contract stability**
  (stable names + argument shapes, contract-tested through a real in-memory
  client↔server session — already in place) and **always emitting honest fields**
  (confidence, correlation-not-causation — the tools return the fusion layer's
  own honest values). Versioning the tool contract, if needed, is additive.
- The plan's "unauthenticated calls rejected" acceptance line is retired for the
  MCP surface and satisfied by the HTTP route for networked reads.

## When to revisit

If a hosted, multi-tenant MCP endpoint is ever wanted (agents on other machines
reaching a shared MRI), that is a *new* networked surface — it would be built on
the HTTP stack with `AuthMiddleware`, versioned tools, and rate limits, and would
not change the local stdio surface this ADR governs.
