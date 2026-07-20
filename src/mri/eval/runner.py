"""The eval runner — run fusion over the labeled corpus, score it, guard it.

Produces the numbers the vision's L6 promises: turn "metrics are gameable" into
"here is our validation set, and here is how close we are on it." Three things
come out:

* **calibration** — for each file whose true AI share is known, the absolute
  error between the computed share and the truth. A tool that claimed 91% where
  the truth was 20% would show a large error here.
* **correlation recall** — of the write touches that genuinely belong to a
  commit, how many were linked.
* **over-claim violations** — the guard run over the result. This must be zero;
  it is the honesty gate, not a quality metric.

The runner builds the corpus in a temp dir and a temp database, so it is
self-contained and leaves nothing behind.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from mri.eval.corpus import (
    LabeledCase,
    build_calibration_case,
    seed_consequence_cases,
)
from mri.eval.guard import Violation, audit_project

__all__ = ["EvalReport", "run_eval"]

#: Ordering of causal claims by strength — a consequence over-claims when the
#: claim it makes outranks the strongest one its ground truth permits.
_CLAIM_RANK = {"none": 0, "correlation": 1, "causation": 2}

#: A computed AI share must land within this many points of the known truth.
#: Blame is exact and correlation is deterministic here, so the real tolerance is
#: rounding; the band is generous so a genuine regression, not float noise, trips it.
CALIBRATION_TOLERANCE = 2.0


@dataclass(slots=True)
class EvalReport:
    case: str = ""
    #: file -> (expected_ai_pct, computed_ai_pct, abs_error)
    calibration: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    correlation_recall: float = 0.0
    #: Fraction of seeded consequences that claimed more than their ground truth
    #: allowed (e.g. a sub-noise move claimed as correlation). Must be 0.0.
    consequence_false_positive_rate: float = 0.0
    violations: list[Violation] = field(default_factory=list)

    @property
    def worst_calibration_error(self) -> float:
        return max((e for _, _, e in self.calibration.values()), default=0.0)

    @property
    def passed(self) -> bool:
        """The honesty gate: no over-claim (violations or a consequence
        false-positive), and every share within tolerance."""
        return (
            not self.violations
            and self.worst_calibration_error <= CALIBRATION_TOLERANCE
            and self.consequence_false_positive_rate == 0.0
        )


async def run_eval(base: Path | None = None) -> EvalReport:
    """Build the corpus, run the full fusion loop over it, and score the result."""
    import git

    from mri.db.migrator import migrate
    from mri.db.repository import get_connection
    from mri.fusion import run_fusion

    workdir = base or Path(tempfile.mkdtemp(prefix="mri-eval-"))
    case: LabeledCase = build_calibration_case(workdir)

    db = workdir / "eval.db"
    migrate(db)
    async with get_connection(db) as conn:
        cursor = await conn.execute(
            "INSERT INTO projects (name, path) VALUES ('eval', ?)", (str(case.repo),)
        )
        if cursor.lastrowid is None:  # pragma: no cover - INSERT always sets a rowid
            raise RuntimeError("INSERT did not return a rowid")
        pid = int(cursor.lastrowid)
        await conn.commit()

        report = await run_fusion(
            conn, git.Repo(case.repo), case.workspace, project_id=pid,
            hotspots=case.hotspots, adr_dir=case.adr_dir, home=case.home,
        )

        result = EvalReport(case=case.name)

        # Calibration: computed AI share vs known truth, per file.
        from mri.db import fusion_repository as repo

        for path, expected in case.expected_ai_pct.items():
            shares = await repo.authorship_for_file(conn, path, project_id=pid)
            computed = shares[0].share_ai if shares else 0.0
            result.calibration[path] = (expected, computed, abs(expected - computed))

        # Correlation recall: linked vs the touches that should have linked.
        result.correlation_recall = (
            report.correlation.linked / case.expected_correlated_touches
            if case.expected_correlated_touches else 1.0
        )

        # Consequence false-positive rate: seed cases whose right answer is known
        # (a sub-noise move must claim nothing; a clear move may claim only
        # correlation), measure them, and count any that claim more than allowed.
        # Persisted, so the honesty guard below audits real consequence rows.
        from mri.fusion import measure_decision_consequences

        expectations = await seed_consequence_cases(conn, pid)
        over_claims = 0
        measured = 0
        for exp in expectations:
            for c in await measure_decision_consequences(
                conn, exp.decision, [exp.metric], project_id=pid, persist=True
            ):
                measured += 1
                if _CLAIM_RANK[c.causal_claim] > _CLAIM_RANK[exp.expected_claim]:
                    over_claims += 1
        result.consequence_false_positive_rate = over_claims / measured if measured else 0.0

        # The honesty gate — now over authorship AND the seeded consequences.
        result.violations = await audit_project(conn, pid)

    return result
