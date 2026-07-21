# Security & Performance Audit

The record of the whole-repo audit gate (Master plan Phase 6). Every number here
was produced by running the tool, not asserted. Re-run the commands to reproduce.

**Last run:** 2026-07-21, against the `chore/modernize-tree-sitter` branch.

---

## Security

### Static analysis — bandit

```
bandit -r src/mri -ll
```

**Result: 0 medium-or-higher findings.** Four findings were raised and each was
verified by hand to be a false positive, then suppressed inline with a documented
`# nosec` reason so the gate stays live for any new real finding:

| Test | Location | Why it is a false positive |
|------|----------|----------------------------|
| B608 | `db/fusion_repository.py` | SQL built from a module-constant column list + `?` placeholders; values are bound. |
| B608 | `fusion/authorship.py` | `IN` list is `",".join("?"*n)` — only placeholders interpolated, values bound. |
| B608 | `fusion/decisions.py` | Same variable-length `IN` placeholder expansion. |
| B613 | `utils/__init__.py` | The bidi control characters are `clean_text`'s own strip-range regex — the trojan-source *defense*, not a trojan. |

### Dependency vulnerabilities — pip-audit

```
pip-audit -r requirements.txt
```

**Result: no known vulnerabilities found.** `requirements.txt` is hash-pinned and
generated from `uv.lock`.

### Security controls (verified by tests, not just present)

- **SSRF guard on cloning** — host allowlist + private/loopback/link-local/metadata
  rejection (`services/repo_cloner.py`), exercised by a real rejection matrix in
  `tests/test_clone_ssrf.py` (the guard is hit, not monkeypatched away).
- **Clone sandbox** — shallow-depth default + on-disk size/file quota, fail-closed
  delete on breach (`tests/test_clone_quota.py`).
- **Fail-closed auth posture** — loopback is trusted, a non-loopback bind without
  auth is refused ([ADR-013](adr/ADR-013-auth-posture-fail-closed-local-first.md),
  `tests/test_bind_posture.py`).
- **Zero network egress** — a socket tripwire proves ingest + a full local scan
  make no non-loopback connection (`tests/test_no_network.py`), including a
  self-test that the tripwire actually fires.
- **No stored XSS in the HTML report** — Jinja autoescape is forced on
  (`services/report_generator.py`); `tests/test_report_fusion.py` asserts a
  `<script>` payload renders escaped.
- **Over-claim guard** — the honesty invariants run as a hard assertion in the
  eval harness (`eval/guard.py`, `tests/test_eval_harness.py`).

CI runs `bandit -r src/mri -ll`, `pip-audit`, `ruff`, `mypy` (blocking), and the
full `pytest` suite on every push.

---

## Performance

Measured by scanning **project-mri's own repository** (270 files) on the dev
machine:

```
Scanner().scan(".")  →  270 files, 98 findings, overall health 60.0, ~2.5 s
```

No unbounded hotspot was observed: the git-history walk is bounded
(`MAX_COMMITS`), the consequence commit walk is capped (`commit_max_count=2000`),
the authorship SQL chunks large path lists under the SQLite variable limit, and
the report-view fusion loop is bounded (top-25 hotspots).

**Scaling study** — synthetic repos (Python files across 20 packages, rotating
churn), scan time only:

| Files | Commits | Scan time |
|------:|--------:|----------:|
| 200   | 60      | 2.4 s |
| 800   | 200     | 9.7 s |
| 1600  | 400     | 13.2 s |

4× the size (200→800) costs ~4× the time — roughly **linear**; doubling again
(800→1600) costs only ~1.4× — **sub-linear**, because the history walk is capped.
No quadratic blow-up. A single 10k-commit-repo data point (rather than this
scaling study) is still worth capturing when a representative real corpus is
available, but the shape is bounded.

---

## Open / follow-up

- The scaling study above (to 1600 files / 400 commits) shows bounded, roughly-
  linear behaviour; a single data point on a real 10k+-commit repository is still
  worth capturing when a representative corpus is available. No timing regression
  budget is enforced in CI yet (the golden baseline guards analyzer *output*, not
  wall-clock).
- An independent third-party threat-model review has not been commissioned.
