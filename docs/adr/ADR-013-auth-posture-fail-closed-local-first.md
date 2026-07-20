# ADR-013 — Auth posture: loopback is trusted, non-loopback fails closed

- **Status:** Accepted
- **Date:** 2026-07-21
- **Relates to:** the plan's Phase 1.2 (H2, "auth-on by default everywhere
  including the container"), `src/mri/security.py` (`assert_safe_bind`,
  `is_auth_enabled`, `is_loopback_host`), and the container entrypoint.

## Context

The rebuilding plan's H2 item reads "auth-on by default everywhere including the
container." Taken literally that means every request, even a local one on
127.0.0.1, must carry a token. For a **local-first** tool that is the wrong
default: the primary user runs `mri serve` on their own machine and talks to it
over loopback, and forcing a login on that path is friction with no threat model
behind it — nothing on the loopback interface is reachable by another host.

The real danger H2 was written against is *accidental network exposure*: a
server bound to `0.0.0.0` (the reflexive container default) with no auth would
put scan/clone/delete endpoints on the network for anyone to hit. "Auth-on
everywhere" is one way to prevent that; it is not the only one, and it taxes the
common local case to cover the uncommon exposed one.

## Decision

**Trust loopback; fail closed on everything else.** `assert_safe_bind` is called
before the server binds and enforces:

- **Loopback host** (`127.0.0.1`, `::1`, `localhost`) → allowed with no auth. The
  local-first default stays frictionless.
- **Non-loopback host** (`0.0.0.0`, a LAN/public IP) → **refused** with a
  `RuntimeError` *unless* auth is configured (an API key or a dashboard user
  created by `mri init`), or the operator sets `MRI_ALLOW_INSECURE=1` to state,
  knowingly, that the interface is on a trusted network behind its own auth.

So a server can never be *accidentally* exposed unauthenticated: the only ways to
bind to a public interface are with auth on, or with an explicit "I know" flag.
The container inherits this — a bare `docker run` binding `0.0.0.0` without auth
**crashes at startup** rather than serving in the open. When auth *is* enabled,
`AuthMiddleware` requires a valid token on every non-public route (public paths:
health, demo), which is already covered by tests.

This **supersedes the literal "auth-on by default" wording of H2.** It meets H2's
actual goal — no unauthenticated network exposure — while keeping the local-first
default usable. `is_auth_enabled()` returning False on a fresh install is
therefore correct, not a hole: on loopback it is safe, and off loopback the bind
guard refuses to start.

## Consequences

- The local `mri serve` / `mri ui` path needs no login; the exposed path cannot
  start unauthenticated. Both halves are covered by tests (`assert_safe_bind`
  matrix; the existing protected-route 401 tests).
- `MRI_ALLOW_INSECURE=1` is the single, auditable escape hatch for "auth is
  terminated upstream" deployments — documented, not silent.
- The container's default posture is fail-closed: it refuses rather than exposes.

## When to revisit

If a first-run admin-token bootstrap is added (auto-generating a token on `mri
init` and printing it once), the container could ship *authenticated*-by-default
instead of *fail-closed*, which is strictly friendlier for the self-host case.
That is an additive enhancement, not a correction — the fail-closed guard stays
as the backstop regardless.
