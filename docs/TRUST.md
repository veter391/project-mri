# Trust

project-mri makes claims about your code and about who wrote it. This document
lists the guarantees behind those claims and, for each one, points at the code or
test that makes it verifiable rather than merely asserted. The rule the whole
product is built to hold:

> **No accuracy claim ships without the number behind it.**

If a value is not measured, it is reported as not measured — never estimated,
never defaulted to a confident-looking zero. What follows is how that rule is
enforced, and how you can check each guarantee yourself.

---

## 1. Local-first and zero-telemetry — proven, not asserted

project-mri runs entirely on your machine. There is no SaaS, no account, no
phone-home, and no analytics beacon anywhere in the core (ADR-002). This is not a
promise in prose — it is a **test that fails the build if any code path reaches
the network**.

**Proof:** `tests/test_no_network.py`. The `no_network` fixture replaces
`socket.socket.connect`, `connect_ex`, and `socket.create_connection` so that any
attempt to open a **non-loopback** connection raises `AssertionError("… MRI must
stay local")`. With that tripwire armed, the suite runs:

- `test_a_full_local_scan_makes_no_outbound_connection` — a complete local scan
  of a real git repo, asserting it runs to completion with the network sealed.
- `test_session_ingest_makes_no_outbound_connection` — a full session-log ingest,
  asserting that reading local agent logs never touches the network.

Crucially, the file also contains `test_the_egress_tripwire_actually_fires`,
which opens a real outbound connection to `8.8.8.8:443` and asserts it is
blocked. That guards against a vacuous pass: the locality tests prove locality
because the tripwire is proven to fire. (Loopback is allowed, because asyncio's
own event-loop self-pipe uses it; egress means a *non*-loopback connection.)

**The only permitted network access** is what you explicitly ask for: cloning a
remote repository you named, and delivering a webhook you configured
(`docs/QUALITY-BARS.md` §4). Nothing else, on any path.

---

## 2. Privacy by default — session content is off unless you turn it on

project-mri reads agent session logs to attribute authorship. Those logs
"routinely contain pasted credentials" (`src/mri/ingest/claude_code.py`), so the
default is to **keep none of their content**.

**The flag:** `store_content`, which defaults to `False` at every layer that
handles it — `parse_log` (`ingest/claude_code.py`), the ingest service
(`ingest/service.py`), the fusion pipeline (`fusion/pipeline.py`), and the CLI.
The `mri fusion --store-content` help text reads: *"Retain agent prompt/response
text (off by default; logs can hold secrets)"* (`src/mri/cli.py`). With it off,
every turn is stored with `content = None` and its hash — enough to correlate and
deduplicate turns without keeping what was said.

**Enforced in the schema, not just the code path.** Migration
`0003_content_retention.sql` adds database triggers so the guarantee holds even
for a caller that never goes through this package:

- Inserting or updating `session_events.content` to a non-null value for a session
  whose `content_stored = 0` is **aborted** by the database.
- Turning retention *off* on a session that had stored content is a **redaction,
  not a relabelling**: an `AFTER UPDATE` trigger nulls the stored content. As the
  migration puts it, leaving the rows while the flag says otherwise "would make
  the flag a lie in the one direction users would rely on it most — 'I turned that
  off'." The hashes stay, so correlation still works.

---

## 3. MIT, forever — no paid gating, no telemetry (ADR-002)

The entire core — backend, analyzers, CLI, dashboard, MCP server, report
generator, CI integrations — is MIT-licensed, permanently. There is **no paid
gating** of any kind: no feature held back, no "enterprise" tier inside the core,
no open-core split where the interesting analysis sits behind a wall. **Zero
telemetry** is part of the same decision: no analytics SDK, no usage beacon
anywhere in the core.

**Verify:** `LICENSE` (MIT), `docs/adr/ADR-002-license-mit-forever.md` for the
reasoning. The license is deliberately tied to the product's positioning so the
two "cannot drift apart" — the guarantee is meant to be provable, not a marketing
line. §1 above is the executable half of the zero-telemetry claim.

---

## 4. Fail-closed auth posture (ADR-013)

The server trusts loopback and **fails closed on everything else.**
`assert_safe_bind` (`src/mri/security.py`) runs before the server binds:

- **Loopback** (`127.0.0.1`, `::1`, `localhost`) → allowed with no auth. The
  local-first path stays frictionless, and nothing on the loopback interface is
  reachable by another host.
- **Non-loopback** (`0.0.0.0`, a LAN or public IP) → **refused with a
  `RuntimeError`** unless auth is configured (an API key or a dashboard user from
  `mri init`), or the operator explicitly sets `MRI_ALLOW_INSECURE=1` to state
  knowingly that the interface is on a trusted network.

So a server can never be *accidentally* exposed unauthenticated. A bare
`docker run` binding `0.0.0.0` without auth **crashes at startup** rather than
serving in the open. When auth is enabled, `AuthMiddleware` requires a valid token
on every non-public route. `MRI_ALLOW_INSECURE=1` is the single, auditable escape
hatch — documented, not silent.

**Verify:** `docs/adr/ADR-013-auth-posture-fail-closed-local-first.md`,
`src/mri/security.py`. The MCP surface (ADR-014) is stdio-transport — a subprocess
with no listening port — so its security boundary is the OS process, exactly like
the CLI; networked reads of the same data go through the auth-gated HTTP route.

---

## 5. The over-claim guard — the trust claims as executable assertions

Every honesty rule the fusion layers enforce at write time is **re-checked
independently** over the stored data by `audit_project`
(`src/mri/eval/guard.py`). It returns every violation it finds; **zero violations
is the pass condition.** The invariants:

| Invariant | Guarantee |
|---|---|
| `shares_sum_to_100` / `share_in_range` | An authorship split accounts for the whole file, in range. |
| `confidence_below_1` | No authorship, touch, decision, or consequence confidence ever reaches 1.0. |
| `never_causation` | No consequence is ever labelled causation — only correlation or nothing. |
| `inconclusive_claims_nothing` | A sub-noise move (|delta| < 1.0) claims nothing, never correlation. |
| `no_human_from_blame` | A blame-derived share never asserts a human portion — absence of AI evidence is *unattributed*, not *human*. |

These run inside `run_eval` (`src/mri/eval/runner.py`) over a labelled corpus, and
`EvalReport.passed` requires **no violations, worst calibration error within
tolerance, and a zero consequence false-positive rate**.

**Enforced in CI.** The backend-tests job runs `python -m pytest tests/`
(`.github/workflows/ci.yml`). That suite includes `tests/test_eval_harness.py`,
which asserts `report.passed` (hence zero guard violations, correlation recall
1.0, and a zero false-positive rate) and `tests/test_no_network.py` (§1). So the
guard and the locality guarantee are checked on every run, as part of the test
suite. (`docs/QUALITY-BARS.md` §5 additionally tracks a dedicated, separately
named hard-assertion gate as a planned hardening step; the assertions themselves
already run today via the suite above.)

---

## 6. No accuracy claim ships without the number behind it

The product's accuracy is measured, published, and reproducible — not asserted.

**The numbers** come from `run_eval` over a deterministic labelled corpus
(`src/mri/eval/corpus.py`), whose ground truth is constructed rather than guessed.
Reproduced by running the eval directly against this repository:

| Metric | Result |
|---|---|
| Worst calibration error (computed AI share vs. known truth) | **0.0** |
| Correlation recall (touches linked vs. touches that should link) | **1.0** |
| Consequence false-positive rate | **0.0** |
| Over-claim violations | **none** |

Because blame is exact and the corpus deterministic, the computed authorship
shares land exactly on the ground truth (100% / 0% / 50% for the three corpus
files), giving a worst calibration error of 0.0. See `docs/METHODOLOGY.md` §7 for
the full breakdown and the corpus construction.

**Unmeasured is reported as unmeasured.** This principle runs top to bottom:

- A crashed analyzer is **excluded from the overall score, not counted as zero**
  (`src/mri/scoring/__init__.py`); the all-unscored placeholder (50) is always
  flagged `is_measured = False`.
- `comment_ratio`, `median_cyclomatic`, `max_cyclomatic` report `null`, not `0`,
  when nothing was scanned (`src/mri/analyzers/complexity.py`) — a `0` "would
  falsely read as 'documented nothing'."
- A consequence that cannot be measured returns absence (`None`), never a zero
  delta dressed as a finding (`src/mri/fusion/consequences.py`).
- Provenance (AI-authorship) is a **reported dimension, never folded into the risk
  score** (ADR-011): the headline risk number means one thing — what the analyzers
  measured — and is never inflated by who wrote the code.

---

## 7. Attribution hygiene

Consistent with a product about honest authorship, project-mri claims no
authorship it cannot support — including its own. There is **no AI-authorship
attribution anywhere** in the repository: not in source, docs, commit messages, or
metadata. This is enforced by the `attribution-hygiene` CI job
(`.github/workflows/ci.yml`), which scans both the working tree and the commit
range and fails the build on any match (`docs/QUALITY-BARS.md` §6).

---

## 8. Checklist — verify every claim yourself

| Guarantee | Check |
|---|---|
| Zero network egress | `tests/test_no_network.py` (incl. the tripwire self-test) |
| Session content off by default | `store_content=False`, `src/mri/ingest/claude_code.py`, `src/mri/cli.py` |
| Content retention enforced in the DB | `src/mri/db/migrations/0003_content_retention.sql` |
| MIT forever, zero paid gating, zero telemetry | `LICENSE`, `docs/adr/ADR-002-license-mit-forever.md` |
| Fail-closed on non-loopback bind | `src/mri/security.py`, `docs/adr/ADR-013-auth-posture-fail-closed-local-first.md` |
| Over-claim guard invariants | `src/mri/eval/guard.py` |
| Accuracy numbers | `src/mri/eval/runner.py`, `tests/test_eval_harness.py` |
| Provenance not folded into risk | `docs/adr/ADR-011-base-risk-composition.md` |
| No AI-authorship attribution | `attribution-hygiene` job in `.github/workflows/ci.yml` |
