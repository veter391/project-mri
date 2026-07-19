"""The consequence loop — what measurably changed after a decision.

This is the layer most able to lie, so it is the one most constrained. It takes
a decision with a date, a metric with a scan history, and a window, and reports
how the metric moved from just before the decision to the end of the window.

What it says, and does not say:

* It reports **correlation**, always. A metric moving after a decision is not
  the decision having moved it, and `causal_claim` is fixed to `correlation` —
  the schema will not even store `causation` from this path.
* It reports the **confounders** it can see: every other decision whose date
  falls in the same window is an alternative explanation, listed by name, and
  the more of them there are the lower the confidence.
* It reports **nothing** when it cannot measure — no scan before the decision,
  or none after it in the window. A missing measurement is absence, returned as
  None, not a zero delta dressed as a finding.

Confidence is never high. A single before-and-after pair across a noisy window,
with other changes landing in it, is weak evidence by construction, and the
number says so.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import aiosqlite

from mri.db import fusion_repository as repo
from mri.models.fusion import Consequence, Decision

__all__ = ["measure_consequence", "measure_decision_consequences"]

#: A before/after pair over a window is correlation over noise. Even with no
#: other decision in the window, it is not certainty — so confidence is capped
#: well below one and falls as confounders accumulate.
_MAX_CONFIDENCE = 0.6
#: How long after a decision to look for its effect, by default. Long enough for
#: a refactor to land and be re-scanned, short enough that half the project's
#: later history is not swept in as "the consequence".
DEFAULT_WINDOW_DAYS = 30


@dataclass(slots=True, frozen=True)
class _ScorePoint:
    value: float
    at: datetime


async def _score_before(
    conn: aiosqlite.Connection, project_id: int, metric: str, moment: datetime
) -> _ScorePoint | None:
    """The most recent scored value of a metric at or before a moment."""
    cursor = await conn.execute(
        """
        SELECT r.score_value, s.started_at
        FROM analyzer_runs r
        JOIN scans s ON s.id = r.scan_id
        WHERE s.project_id = ? AND r.analyzer_name = ? AND r.score_value IS NOT NULL
              AND s.started_at <= ?
        ORDER BY s.started_at DESC
        LIMIT 1
        """,
        (project_id, metric, moment.isoformat()),
    )
    row = await cursor.fetchone()
    return _ScorePoint(float(row[0]), datetime.fromisoformat(row[1])) if row else None


async def _score_within(
    conn: aiosqlite.Connection, project_id: int, metric: str, start: datetime, end: datetime
) -> _ScorePoint | None:
    """The latest scored value of a metric strictly after `start`, up to `end`."""
    cursor = await conn.execute(
        """
        SELECT r.score_value, s.started_at
        FROM analyzer_runs r
        JOIN scans s ON s.id = r.scan_id
        WHERE s.project_id = ? AND r.analyzer_name = ? AND r.score_value IS NOT NULL
              AND s.started_at > ? AND s.started_at <= ?
        ORDER BY s.started_at DESC
        LIMIT 1
        """,
        (project_id, metric, start.isoformat(), end.isoformat()),
    )
    row = await cursor.fetchone()
    return _ScorePoint(float(row[0]), datetime.fromisoformat(row[1])) if row else None


async def _confounders_in_window(
    conn: aiosqlite.Connection, start: datetime, end: datetime, *, exclude_id: int | None
) -> list[str]:
    """Other decisions dated inside the window — the alternative explanations.

    Their presence is the honest caveat on any claim that *this* decision moved
    the metric: something else changed in the same span, and we name it.
    """
    cursor = await conn.execute(
        """
        SELECT id, summary FROM decisions
        WHERE decided_at IS NOT NULL AND decided_at >= ? AND decided_at <= ?
        ORDER BY decided_at
        """,
        (start.isoformat(), end.isoformat()),
    )
    return [
        f"{summary} ({source_id})"
        for source_id, summary in await cursor.fetchall()
        if source_id != exclude_id
    ]


async def measure_consequence(
    conn: aiosqlite.Connection,
    decision: Decision,
    metric: str,
    *,
    project_id: int,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> Consequence | None:
    """Measure how one metric moved after one decision, or None if it cannot.

    Returns None — an honest absence — when the decision has no date, or there is
    no scan of the metric before the decision, or none after it within the
    window. None of those are a zero delta; they are "not measurable", which is a
    different statement and must not be stored as a finding.
    """
    if decision.decided_at is None or decision.id is None:
        return None

    window_start = decision.decided_at
    window_end = window_start + timedelta(days=window_days)

    baseline = await _score_before(conn, project_id, metric, window_start)
    observed = await _score_within(conn, project_id, metric, window_start, window_end)
    if baseline is None or observed is None:
        return None

    confounders = await _confounders_in_window(
        conn, window_start, window_end, exclude_id=decision.id
    )
    # One other change in the window halves the confidence; more, more so. Alone,
    # it is still only correlation over a window, so it is capped, never certain.
    confidence = round(_MAX_CONFIDENCE / (1 + len(confounders)), 3)

    return Consequence(
        decision_id=decision.id,
        metric=metric,
        file_path=decision.file_path,
        window_start=window_start,
        window_end=window_end,
        baseline_value=round(baseline.value, 3),
        observed_value=round(observed.value, 3),
        delta=round(observed.value - baseline.value, 3),
        causal_claim="correlation",  # never causation from this path
        confounders=confounders,
        confidence=confidence,
    )


async def measure_decision_consequences(
    conn: aiosqlite.Connection,
    decision: Decision,
    metrics: list[str],
    *,
    project_id: int,
    window_days: int = DEFAULT_WINDOW_DAYS,
    persist: bool = True,
) -> list[Consequence]:
    """Measure every metric that can be measured for one decision.

    Metrics with no before-and-after in the window are skipped, not stored as
    zero. When `persist` is true the measurable ones are written; the returned
    list is exactly what was measured, whether or not it was stored.
    """
    measured: list[Consequence] = []
    for metric in metrics:
        consequence = await measure_consequence(
            conn, decision, metric, project_id=project_id, window_days=window_days
        )
        if consequence is None:
            continue
        if persist:
            consequence = await repo.insert_consequence(conn, consequence)
        measured.append(consequence)
    return measured
