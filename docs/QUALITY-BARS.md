# Quality bars

The non-negotiable bars every change must clear. Each bar states what it is, how
it is measured, and whether CI enforces it today or is scheduled to.

A bar is only real if a command proves it. Numbers here are measured, not
aspirational — when a baseline changes, update this file in the same PR.

---

## 1. Test coverage floor

| | |
|---|---|
| **Bar** | Line coverage of `src/mri` must not drop below **75%** |
| **Measured** | `pytest --cov=src/mri --cov-report=term` |
| **Baseline** | 76% (2981 statements, 725 uncovered) — measured 2026-07-18 |
| **Enforced** | Scheduled — CI uploads coverage today; the `--cov-fail-under=75` gate lands with Phase 1 |

The floor ratchets: it may be raised when the baseline rises, never lowered to
accommodate a regression. New modules ship with tests in the same change.

---

## 2. Zero-warning lint and types

| | |
|---|---|
| **Bar** | `ruff check src tests` reports zero findings. No blanket `# noqa`; a suppression needs a scoped rule in `pyproject.toml` with a reason |
| **Measured** | `ruff check src tests`, `mypy src/mri`, `tsc --noEmit` for both Next apps |
| **Status** | ruff enforced and clean; mypy runs advisory (`|| true`) until its backlog is cleared; `tsc` enforced via each app's build |
| **Enforced** | ruff: yes. mypy blocking: scheduled with Phase 1 |

---

## 3. Accessibility — WCAG 2.1 AA

| | |
|---|---|
| **Bar** | Every shipped surface (dashboard, public site, HTML report) passes axe with zero serious/critical violations; text contrast ≥ 4.5:1, large text ≥ 3:1; all interactive elements keyboard-reachable with a visible focus ring |
| **Measured** | Playwright + `@axe-core/playwright`; contrast checked against the token values in `apps/*/app/globals.css` |
| **Enforced** | Scheduled — the axe job is part of the Phase 0 CI expansion; token contrast audit is tracked as Rebuild item 2.8 |

---

## 4. No-network scan guarantee

| | |
|---|---|
| **Bar** | Scanning a **local** path performs zero outbound network I/O. No telemetry, no phone-home, no analytics — ever, on any path |
| **Measured** | A test that runs a full local scan with sockets blocked and asserts no connection attempt |
| **Enforced** | Scheduled — the no-network test lands with the Phase 5 ingest work, where session-log reading makes the guarantee load-bearing |

Network access is permitted only where the user explicitly asks for it: cloning a
remote repository, and delivering a webhook the user configured.

---

## 5. Over-claim guard

| | |
|---|---|
| **Bar** | The product never presents correlation as causation, never reports a metric it did not measure, and never emits a confidence it cannot justify. Unmeasured values are `null`, not `0` |
| **Measured** | Assertions in the eval harness: correlation outputs must carry a correlation-not-causation label and enumerate confounders; attribution must expose an `unattributed` share rather than defaulting |
| **Enforced** | Scheduled — hard CI assertion lands with Rebuild Phase 10 (eval harness) |

Precedent already in the codebase: `comment_ratio` reports `null` when no parser
was available, because a `0.0` would read as "documented nothing" rather than
"not measured".

---

## 6. Attribution hygiene

| | |
|---|---|
| **Bar** | No AI-authorship attribution anywhere in the repository — not in commit messages, source, docs, or metadata |
| **Measured** | A CI grep over the tree and the commit range |
| **Enforced** | Yes — `attribution-hygiene` job in `ci.yml` |

---

## 7. Supply chain

| | |
|---|---|
| **Bar** | Dependency resolution is reproducible and every artifact is hash-verified; no known-vulnerable dependency ships |
| **Measured** | `uv.lock` pins the full graph; `requirements.txt` is generated from it with hashes; `pip-audit --strict` and `bandit -r src/mri -ll` run in CI |
| **Enforced** | Yes |

`pyproject.toml` deliberately declares compatible **ranges** rather than exact
pins, so the published wheel does not over-constrain consumers. Exactness lives
in the lock — see [INSTALL.md](./INSTALL.md#install-from-source-development).

---

## Definition of done for any change

1. The change is exercised, not just written — a test, a run, or both.
2. Bars 1, 2, 6, 7 pass locally before the branch is pushed.
3. Anything measured is measured, not estimated. If a number is unknown, it is
   reported as unknown.
4. No crutches: no commented-out code, no `|| true` masking a real failure, no
   TODO without an issue number.
