# Methodology

How every number project-mri reports is computed, what evidence backs it, and
where it deliberately stops short of a claim it cannot defend. This document is
meant to be read next to the code: every score and every fusion signal below
cites the file that produces it, so a reader can check the mechanism against the
source rather than trust a description.

The governing rule, stated once and enforced throughout: **every number explains
itself, and a value that cannot be attributed is reported as unattributed rather
than guessed.** The composition layer's own docstring says as much
(`src/mri/scoring/__init__.py`), and the over-claim guard (§4) turns it into an
executable check.

---

## 1. Analyzer scores

Each analyzer produces one 0–100 health score plus a **contributors ledger** — a
list of the exact penalties that moved the score, so the number is never a bare
verdict. A score starts at 100 and subtracts named, bounded penalties. Every
analyzer also carries a fixed **weight** used later by composition (§3).

| Analyzer | Score label | Weight | Source |
|---|---|---|---|
| Git history | `history_health` | 1.0 | `src/mri/analyzers/git_history.py` |
| Complexity | `complexity_health` | 1.0 | `src/mri/analyzers/complexity.py` |
| Tech debt | `debt_index` | 1.0 | `src/mri/analyzers/tech_debt.py` |
| Coupling | `coupling_health` | 0.9 | `src/mri/analyzers/coupling.py` |
| Architecture | `architecture_health` | 1.2 | `src/mri/analyzers/architecture.py` |
| Dependencies | `dependency_health` | 1.0 | `src/mri/analyzers/dependencies.py` |

### 1.1 Git history — `git_history.py`

**Evidence.** A single `git log -<MAX_COMMITS> --numstat --no-renames` over the
resolved branch (`_collect_churn`). One process, not a diff per commit; the
`--numstat` output gives per-file insertions and deletions, and the same output
carries author identity and commit dates, so history is walked once. `MAX_COMMITS`
is 10,000, an upper bound so an old repository cannot make a scan unbounded.

**Hotspots.** For each file, churn = insertions + deletions summed across commits,
and `commits` = number of commits touching it. A file is a hotspot candidate only
when it has at least 3 commits and at least 50 lines of churn (below that it is
noise). Its composite score is:

```
composite = commits * (1 + sqrt(churn) / 10)
```

(`git_history.py`, the `composite` expression). High churn and many commits both
raise it; the square root keeps a single enormous-churn file from dominating.

**Bus factor** is the minimum number of authors whose combined changes cover 80%
of all changes (`BUS_FACTOR_TARGET = 0.80`). **Knowledge islands** are files with
one author and at least 5 commits. **Cadence** compares commit counts in the last
90 days against the prior 90.

**Score.** Starts at 100. The top hotspot subtracts `min(40, composite * 0.4)`;
bus factor of 1 subtracts 35, of 2 subtracts 20, of 3–4 subtracts 8; knowledge
islands subtract `min(15, count * 1.5)`. Each penalty is appended to the ledger
with its value, e.g. `bus_factor = 1 (single point of failure) (-35.0)`.

**Honesty stance.** A directory with no git repository or no commits scores 50
with an explicit info finding ("No git history"), never 0 — absence of history is
not bad code. History that cannot be read (`GitCommandError`) is logged at
warning level and treated as empty, never silently swallowed, because an empty
result is otherwise indistinguishable from a clean one.

### 1.2 Complexity — `complexity.py`

**Evidence.** Function-level metrics come from **lizard**
(`_functions_of` → `lizard.analyze_file.analyze_source_code`), which reports each
function's length, start line, and cyclomatic complexity across ~21 source
extensions (`LIZARD_EXTS`). Files lizard does not parse are skipped, not guessed
at. Comment lines are counted by two regexes (`#` and `//`).

**Thresholds** are the long-standing conventions: cyclomatic complexity > 10 is
flagged (`COMPLEX_FN_CC = 10`, McCabe's original number), long file > 500 LOC
(critical > 1500), long function > 60 lines.

**Score.** Starts at 100. Long files subtract `min(30, count * 4)`; long
functions `min(25, count * 2)`; complex functions `min(20, count * 1.5)`. A
comment ratio below 5% subtracts 10 — **but only when code lines were actually
scanned**.

**Honesty stance.** When lizard is unavailable or no source lines were scanned,
`comment_ratio`, `median_cyclomatic` and `max_cyclomatic` are reported as `null`,
not `0`. The code comments this directly: a `0.0` here "would falsely read as
'documented nothing' rather than 'not measured'." No comment-ratio penalty fires
when no lines were scanned.

### 1.3 Tech debt — `tech_debt.py`

**Evidence.** Seven separately compiled marker patterns, each with a weight:
`TODO` (1.0), `FIXME` (2.0), `HACK` (1.5), `XXX` (1.2), `BUG` (1.0), `DEPRECATED`
(1.8, case-insensitive), `noqa` (0.5, case-insensitive) — see `DEBT_PATTERNS`.
Vendored directories (`node_modules`, `vendor`, `.venv`, `dist`, `build`, …) and
files whose first five lines mark them auto-generated are excluded before
counting.

**Score.** Debt density = weighted marker total per 1,000 LOC. `<= 0.5/kLOC` is
clean (no penalty); `<= 2.0` subtracts 5; `<= 5.0` subtracts 15; above subtracts
30. Ten or more `FIXME`s subtract a further 5. TODOs in test files are downgraded
to severity `info`.

**Honesty stance.** `debt_index` is an inverse signal (higher = more debt); it is
stored as measured and the composition layer treats it as its own health value.
Markers in tests are surfaced but not penalised as core debt.

### 1.4 Coupling — `coupling.py`

**Evidence.** Robert Martin's I/D metrics on the module import graph, built from
`extract_imports`. Per module: afferent coupling `Ca` (modules that depend on
it), efferent `Ce` (modules it depends on), instability `I = Ce / (Ca + Ce)`,
abstractness `A` (a filename heuristic, clamped to `[0, 1]`), and distance from
the main sequence `D = |A + I − 1| / sqrt(2)`.

**Score.** "Painful" modules are stable-and-concrete with real fan-in
(`D > 0.5` and `Ca >= 3`). They subtract `min(35, count*5 + (top_D − 0.5)*30)`.

**Honesty stance.** Abstractness is decided once per file so `abstract_count` can
never exceed `type_count`, keeping `A` inside its documented `[0, 1]` range — a
comment in the code flags this as a deliberate guard against skewing `D`. `A`
is explicitly a heuristic (filename-based), not a claim about semantic
abstractness, and is labelled as such in findings.

### 1.5 Architecture — `architecture.py`

**Evidence.** A module map derived from the filesystem tree: top-level directories
become modules, with per-module file count, LOC, max nesting depth. **God
modules** are those over 5,000 LOC or holding more than half the codebase's LOC;
**deep nesting** is depth > 4.

**Score.** God modules subtract `min(35, count*15 + (top_share − 0.4)*30)`; deep
modules subtract `min(15, count*5)`. Architecture carries the highest weight
(1.2) in composition, reflecting its impact.

**Honesty stance.** Signal lists are capped (`SIGNAL_SAMPLE_LIMIT = 50`) with the
true total reported beside them, so a truncated view can never be mistaken for
the whole — a comment records this as a fix for multi-megabyte reports on large
repos.

### 1.6 Dependencies — `dependencies.py`

**Evidence.** A module-level import graph, cycles detected with an **iterative
Tarjan's SCC** (`_find_cycles`, iterative to survive 10k-module graphs).
Fan-in/fan-out per module; "god consumers" are high fan-in modules.

**Score.** Cycles subtract `min(40, Σ min(20, len*4))`; a god consumer with
fan-in ≥ 15 subtracts `min(15, fanin*0.5)`.

**Honesty stance.** Reported cycles and their members are capped (5 cycles, 25
members each) with the largest-cycle size reported separately, so a single giant
SCC does not become an unbounded report.

---

## 2. What the analyzer scores are *not*

Analyzer scores measure the code the analyzers can see. They do **not** encode who
wrote the code. That separation is the subject of §5 and ADR-011, and it is the
single most important honesty boundary in the product.

---

## 3. Composing the overall score — `scoring/__init__.py`

`compose_overall(runs, weights)` combines analyzer scores into one weighted-mean
health value and returns a `Composition(value, ledger, unscored)`.

**Formula.** For every analyzer that produced a score, `value = Σ(score * weight)
/ Σ(weight)`. The ledger records each contributor as
`label = value (weight w)`, plus a line per excluded analyzer.

**Unmeasured analyzers are excluded, not zeroed.** An analyzer that failed or
produced no score is dropped from the average entirely and listed in the ledger
as `not measured (excluded from the average)`. The docstring states the reason
plainly: "a crashed analyzer means 'not measured', and scoring it as zero would
silently turn a tooling failure into a bad verdict about the user's code."

**The all-unscored case.** When nothing scored, the value is `UNMEASURED_VALUE =
50.0` with an empty ledger, and `Composition.is_measured` returns `False`. The
constant is deliberately mid-range and always reported as unmeasured, "so it can
never read as a real assessment." 50 here is a placeholder, not a finding.

---

## 4. The over-claim guard — `eval/guard.py`

Every honesty rule the fusion layers enforce at write time is **re-checked
independently** against the stored data by `audit_project(conn, project_id)`,
which returns a list of `Violation`s. Zero violations is the pass condition. The
guard exists so the rules can be verified over any real database, not just
trusted to hold. The invariants it asserts:

- **`shares_sum_to_100`** — an authorship split totals 100 (±0.01).
- **`share_in_range`** — each share is within `[0, 100]`.
- **`confidence_below_1`** — no authorship, touch, decision, or consequence
  confidence reaches 1.0. Nothing here is ever certain.
- **`never_causation`** — no consequence's `causal_claim` is `causation`.
- **`inconclusive_claims_nothing`** — a sub-noise consequence (|delta| < 1.0) must
  not claim `correlation`.
- **`no_human_from_blame`** — a blame-derived share never asserts a human
  portion (see §5.1).

These are validated by the eval harness (§7) and asserted by the test suite CI
runs (see TRUST.md §5).

---

## 5. Fusion signals

Fusion correlates git history with agent session logs. Each signal below states
its mechanism, its evidence, and where it refuses to overstate.

### 5.1 Line authorship — `fusion/line_authorship.py`

**Mechanism.** `git blame HEAD <file>` assigns every current line its
last-modifying commit — a fact, not an estimate. Session write/create touches are
linked to commits by the correlation step (§5.2); a line whose last-modifying
commit is one an agent write-touch was linked to is **AI-authored**. The share is
`round(ai_lines / total * 100, 2)`, method tag `blame_session_commit`.

**Unattributed is not human.** Everything not tied to an agent commit is
`share_unattributed`; `share_human` stays `0.0` and is documented "never claimed
from this evidence." The reasoning, straight from the module: a line we cannot tie
to an agent commit "might be human-written, might predate any session, might come
from an agent session we never ingested. Absence of AI evidence is not evidence of
a human." This distinction is exactly what ADR-008 and the schema were built to
preserve, and the guard's `no_human_from_blame` rule enforces it.

**A human rewrite correctly de-attributes.** A line an agent wrote but a human
later rewrote blames to the human's commit and is *not* counted as AI — the share
measures authorship of the current content.

**Confidence is the correlation's, not blame's.** Blame is exact, but "this commit
is agent-attributed" rests on the touch→commit link, whose confidence is below 1.
So a file's share confidence is the strongest write-touch confidence among its
agent-attributed commits, or 0 when there are none.

**Honest absence.** A file that cannot be blamed (absent at HEAD, binary) is
omitted and logged, not emitted as a fabricated zero-row.

### 5.2 Session-to-commit correlation — `fusion/correlation.py`

**Mechanism.** A write touch on file *F* at time *T* is linked to **the earliest
commit that changed *F* at or after *T*** (`_first_commit_at_or_after`, a bisect
over the file's ascending author-time commit list). No fixed time window, no fuzzy
overlap — the commit history itself decides which commit first materialised the
edit. A touch with no later commit changing *F* is left **unlinked** and counted
as `uncommitted`, because that edit is not committed yet.

**Honesty stance.** The link adds *which* commit, not *more certainty*: "The touch
keeps its own sub-1.0 confidence, and nothing here raises it." This is stated as
correlation, not proof — the human may have altered the agent's edit before
committing.

### 5.3 Decision provenance — `fusion/decisions.py`

**Two sources, two confidence levels:**

- An **ADR** is a deliberate decision record — the strongest provenance available
  — recorded at `ADR_CONFIDENCE = 0.95`, never 1.0 because a record can go stale.
- A **commit** with an author-written body states a reason: recorded at
  `COMMIT_WITH_RATIONALE_CONFIDENCE = 0.6`. A commit with only a subject has an
  unrecoverable "why": recorded at `COMMIT_SUBJECT_ONLY_CONFIDENCE = 0.3` with
  `rationale = None`.

**Honesty stance.** When a commit has no body, the rationale stays absent rather
than copying the subject in to look complete — "Fabricating a rationale is the
exact failure a provenance record exists to prevent." ADRs and commits describing
the same decision are **linked, never merged**, and only by *explicit*
cross-reference (a commit naming an ADR, or an ADR body citing a real commit sha);
fuzzy text similarity is deliberately not used, because a wrong merge would
fabricate a relationship.

### 5.4 The consequence loop — `fusion/consequences.py`

The layer "most able to lie, so it is the one most constrained." It takes an
anchor (a dated decision or an agent session), a metric with scan history, and a
window (`DEFAULT_WINDOW_DAYS = 30`), and reports how the metric moved from just
before the anchor to the end of the window.

**Correlation, never causation.** `causal_claim` is only ever `none` or
`correlation`; the string `causation` is never written from this path. The
`_build_consequence` line is annotated `# never causation`, and the guard's
`never_causation` rule audits for it independently.

**Confidence is bounded and falls with confounders.**
`confidence = round(_MAX_CONFIDENCE / (1 + len(confounders)), 3)`, with
`_MAX_CONFIDENCE = 0.6`. Even a lone before/after over a window is not certainty;
each co-occurring confounder lowers it further. The confidence uses the *true*
confounder count, not the truncated display sample.

**Confounders are enumerated, two classes** (`_confounders_in_window`):

1. **Overlapping decisions** — every other decision dated inside the window is an
   alternative explanation, listed by summary.
2. **Concurrent same-file changes** — other agent sessions that wrote the
   decision's file during the window, each named.

Both are project-scoped (another repo's activity cannot explain this one's metric,
and counting it would leak its data). The list is capped at
`MAX_CONFOUNDERS_LISTED = 50` with a truthful "… and N more" remainder — a caveat,
not a catalogue.

**Sub-noise moves claim nothing.** A movement smaller than `NOISE_THRESHOLD = 1.0`
on the 0–100 scale is recorded with `causal_claim = 'none'` and `confidence = 0.0`
— "followed by no discernible change" is a real finding, but it asserts no link,
and its confidence is not inflated by confounders it is not claiming through.

**Absence is returned as absence.** No scan before the anchor, or none after it in
the window, returns `None` — not a zero delta dressed as a finding. A non-finite
score (an upstream analyzer bug) is likewise dropped rather than persisted as a
meaningful `inf` delta.

### 5.5 Authorship-weighted risk — ADR-011, `fusion/explain.py`

`explain_file` surfaces base risk, authorship, sessions, decisions, and
consequences as **separate, evidence-backed factors**. It also emits a
`weighted_risk` factor when a file has base risk and agent write evidence:
`base_risk × evidence_strength`, bounded so it is **never larger than base risk**,
and omitted when it rounds to zero. It is labelled "correlation, not blame," and
is used only to *order* which risky file most sits under agent-modified code.

---

## 6. Provenance is not folded into risk — ADR-011

The single most load-bearing honesty decision. A file's base risk is
`MAX(findings.score)` per path from the latest scan — a composite of the static
and git-history signals in §1. **AI-authorship is neutral provenance, not a risk
factor**, and is never folded into the base risk number.

Folding an AI-authored percentage into risk would assert "AI-written code is
riskier," which nothing in this product has measured and which it explicitly
refuses to claim (ADR-011). Decision density is likewise not a risk multiplier (a
well-documented file is not a dangerous one), and consequence volatility is
already capped and noise-gated. The headline risk number therefore keeps meaning
exactly one thing — what the analyzers measured — and is never inflated by who
wrote the code. Should a *measured, validated* relationship between a fusion
signal and defect rate ever exist, ADR-011 documents the path to earning it a
place in the score; until such a number exists, provenance stays a reported
dimension.

---

## 7. Validation — `eval/runner.py`, `eval/corpus.py`

The product's numbers are only trustworthy where they can be checked against a
known answer. `run_eval` builds a deterministic labelled corpus — a real git
repo, real session logs, real ADRs, all synthesised in a temp directory with the
ground truth constructed rather than guessed — runs the full fusion loop over it,
and scores three things:

- **Calibration** — per file, the absolute error between the computed AI share and
  the known truth. Tolerance is `CALIBRATION_TOLERANCE = 2.0` (blame is exact and
  correlation is deterministic here, so the real tolerance is rounding).
- **Correlation recall** — of the write touches that genuinely belong to a commit,
  how many were linked.
- **Consequence false-positive rate** — seeded cases with known right answers (a
  sub-noise move must claim nothing; a clear move may claim only correlation),
  counting any that claim more than allowed. This must be `0.0`.
- **Over-claim violations** — the guard (§4) run over the result. This must be
  empty; it is the honesty gate, not a quality metric.

**Measured result on the labelled corpus** (reproduced by running `run_eval`
directly against this repository):

| Metric | Result |
|---|---|
| Calibration — `ai_all.py` | expected 100.0, computed 100.0, error **0.0** |
| Calibration — `human_all.py` | expected 0.0, computed 0.0, error **0.0** |
| Calibration — `mixed.py` | expected 50.0, computed 50.0, error **0.0** |
| Worst calibration error | **0.0** |
| Correlation recall | **1.0** |
| Consequence false-positive rate | **0.0** |
| Over-claim violations | **none** |
| `report.passed` | **True** |

The corpus files carry exact provenance by construction: `ai_all.py` is written
wholly in a commit an agent write-touched (100% AI); `human_all.py` is written in
a commit no session touched (0% AI); `mixed.py` splits 2 of its 4 current lines
across an agent commit and a later human commit (50%). Blame is exact and the
scenario deterministic, so the computed shares land exactly on the truth — a worst
calibration error of 0.0. `EvalReport.passed` requires no violations, worst
calibration error within tolerance, and a zero consequence false-positive rate;
`tests/test_eval_harness.py` asserts all of these, and CI runs that suite (see
TRUST.md §5).

> ADR-008 additionally records a repository-scale spot check: "a file this project
> largely wrote measures 91% AI-authored, a barely-touched one 6%, shares summing
> to 100 with `human` at 0." Those two figures depend on this machine's own
> session logs and are reproduced from ADR-008 rather than re-measured here.

---

## 8. Where to check each claim

| Claim | Verify in |
|---|---|
| Hotspot formula `commits*(1+sqrt(churn)/10)` | `src/mri/analyzers/git_history.py` |
| Unmeasured excluded, not zeroed | `src/mri/scoring/__init__.py` (`compose_overall`) |
| `share_human` never emitted from blame | `src/mri/fusion/line_authorship.py` |
| Correlation never causation; confounders lower confidence | `src/mri/fusion/consequences.py` |
| Guard invariants | `src/mri/eval/guard.py` |
| Provenance not folded into risk | `docs/adr/ADR-011-base-risk-composition.md` |
| Line-share method and its deferral history | `docs/adr/ADR-008-authorship-line-shares-deferred.md` |
| Calibration / recall / FP numbers | `src/mri/eval/runner.py`, `src/mri/eval/corpus.py`, `tests/test_eval_harness.py` |
