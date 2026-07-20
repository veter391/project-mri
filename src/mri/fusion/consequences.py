"""The consequence loop — what measurably changed after a decision or a session.

This is the layer most able to lie, so it is the one most constrained. It takes
an anchor (a decision with a date, or an agent session), a metric with a scan
history, and a window, and reports how the metric moved from just before the
anchor to the end of the window.

What it says, and does not say:

* It reports **correlation**, never causation — the schema will not store
  `causation` from this path. And a move within the re-scoring **noise floor**
  claims nothing: it is recorded with `causal_claim='none'` and zero confidence,
  because "followed by no discernible change" is a real finding, not a link.
* It reports the **confounders** it can see: every other decision whose date
  falls in the same window is an alternative explanation, listed by name, and
  the more of them there are the lower the confidence.
* It reports **nothing** when it cannot measure — no scan before the anchor, or
  none after it in the window. A missing measurement is absence, returned as
  None, not a zero delta dressed as a finding.

Confidence is never high. A single before-and-after pair across a noisy window,
with other changes landing in it, is weak evidence by construction, and the
number says so.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import aiosqlite

from mri.db import fusion_repository as repo
from mri.models.fusion import Consequence, Decision, Session
from mri.utils import utc_iso

__all__ = [
    "measure_consequence",
    "measure_decision_consequences",
    "measure_session_consequences",
]

#: A before/after pair over a window is correlation over noise. Even with no
#: other decision in the window, it is not certainty — so confidence is capped
#: well below one and falls as confounders accumulate.
_MAX_CONFIDENCE = 0.6
#: How long after a decision to look for its effect, by default. Long enough for
#: a refactor to land and be re-scanned, short enough that half the project's
#: later history is not swept in as "the consequence".
DEFAULT_WINDOW_DAYS = 30
#: Confounders are a caveat, not a catalogue. A window with thousands of
#: decisions does not need thousands listed on the row; a sample plus the true
#: count says as much without writing a multi-megabyte blob per consequence.
MAX_CONFOUNDERS_LISTED = 50
#: A movement smaller than this (on the 0..100 score scale) is within the noise
#: of re-scoring and is not a correlation to claim. The measurement is still
#: recorded — "this decision was followed by no discernible change" is a real,
#: useful finding — but its causal_claim is 'none', not 'correlation'.
NOISE_THRESHOLD = 1.0


#: Normalise a moment to canonical UTC before comparing it against stored
#: timestamps. Shared with the storage layer (fusion_repository.utc_iso) so a
#: window bound computed in memory and a timestamp written to the DB are on the
#: identical footing — a divergence here silently picks the wrong baseline scan.
_utc_iso = utc_iso


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
        (project_id, metric, _utc_iso(moment)),
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
        (project_id, metric, _utc_iso(start), _utc_iso(end)),
    )
    row = await cursor.fetchone()
    return _ScorePoint(float(row[0]), datetime.fromisoformat(row[1])) if row else None


async def _confounders_in_window(
    conn: aiosqlite.Connection,
    start: datetime,
    end: datetime,
    *,
    project_id: int,
    exclude_id: int | None,
) -> list[str]:
    """Other decisions in this project dated inside the window.

    These are the alternative explanations for the metric moving — the honest
    caveat that something else changed in the same span. Scoped to the project:
    a decision in another repo cannot explain this one's metric, and counting it
    would both mislead and leak another project's decision summaries.

    Bounded: a huge window returns a sample plus a truthful "and N more" rather
    than a list of thousands written into one row.
    """
    cursor = await conn.execute(
        """
        SELECT id, summary FROM decisions
        WHERE project_id = ? AND decided_at IS NOT NULL
              AND decided_at >= ? AND decided_at <= ?
        ORDER BY decided_at
        """,
        (project_id, _utc_iso(start), _utc_iso(end)),
    )
    others = [
        summary for decision_id, summary in await cursor.fetchall() if decision_id != exclude_id
    ]
    return others


def _sample_confounders(all_confounders: list[str]) -> list[str]:
    """A caveat, not a catalogue: at most a sample, with a truthful remainder."""
    if len(all_confounders) <= MAX_CONFOUNDERS_LISTED:
        return all_confounders
    hidden = len(all_confounders) - MAX_CONFOUNDERS_LISTED
    return [
        *all_confounders[:MAX_CONFOUNDERS_LISTED],
        f"... and {hidden} more decision(s) in this window",
    ]


def _build_consequence(
    metric: str, baseline: _ScorePoint, observed: _ScorePoint,
    window_start: datetime, window_end: datetime, confounders: list[str],
    *, decision_id: int | None = None, session_id: int | None = None,
    file_path: str | None = None,
) -> Consequence | None:
    """Assemble a consequence, or None if the scores are not real measurements.

    Anchored to a decision or a session (exactly one). A non-finite score is an
    upstream analyzer bug, not a finding: an inf delta would be persisted and
    round-tripped as if it meant something. It is dropped the same way an
    unmeasurable metric is — absence, not a fabricated number.
    """
    if not (math.isfinite(baseline.value) and math.isfinite(observed.value)):
        return None

    # The confidence reflects the true number of co-occurring decisions, not the
    # truncated sample: one other change halves it, more lowers it further, and
    # it is capped below one because a before/after over a window is correlation.
    confidence = round(_MAX_CONFIDENCE / (1 + len(confounders)), 3)
    delta = observed.value - baseline.value
    # A movement within the re-scoring noise is not a correlation to claim. The
    # measurement is kept — "followed by no discernible change" is a real finding
    # — but it claims nothing, and its confidence is not inflated by confounders
    # it is not asserting a link through.
    within_noise = abs(delta) < NOISE_THRESHOLD
    return Consequence(
        decision_id=decision_id,
        session_id=session_id,
        metric=metric,
        file_path=file_path,
        window_start=window_start,
        window_end=window_end,
        baseline_value=round(baseline.value, 3),
        observed_value=round(observed.value, 3),
        delta=round(delta, 3),
        causal_claim="none" if within_noise else "correlation",  # never causation
        confounders=_sample_confounders(confounders),
        confidence=0.0 if within_noise else confidence,
    )


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
        conn, window_start, window_end, project_id=project_id, exclude_id=decision.id
    )
    return _build_consequence(
        metric, baseline, observed, window_start, window_end, confounders,
        decision_id=decision.id, file_path=decision.file_path,
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
    if decision.decided_at is None or decision.id is None:
        return []

    window_start = decision.decided_at
    window_end = window_start + timedelta(days=window_days)
    # The confounders are the same for every metric of this decision — one
    # window, one project — so the query runs once, not once per metric.
    confounders = await _confounders_in_window(
        conn, window_start, window_end, project_id=project_id, exclude_id=decision.id
    )

    measured: list[Consequence] = []
    for metric in metrics:
        baseline = await _score_before(conn, project_id, metric, window_start)
        observed = await _score_within(conn, project_id, metric, window_start, window_end)
        if baseline is None or observed is None:
            continue
        consequence = _build_consequence(
            metric, baseline, observed, window_start, window_end, confounders,
            decision_id=decision.id, file_path=decision.file_path,
        )
        if consequence is None:
            continue
        if persist:
            consequence = await repo.insert_consequence(conn, consequence)
        measured.append(consequence)
    return measured


async def measure_session_consequences(
    conn: aiosqlite.Connection,
    session: Session,
    metrics: list[str],
    *,
    project_id: int,
    window_days: int = DEFAULT_WINDOW_DAYS,
    persist: bool = True,
) -> list[Consequence]:
    """Measure how metrics moved across and after an agent session.

    The baseline is the metric before the session began; the observed value is
    the latest scan from the session's end through the window. This is the
    session-anchored twin of `measure_decision_consequences`, and the same
    honesty holds: correlation never causation, None when unmeasurable, a
    sub-noise move claims nothing.
    """
    if session.started_at is None or session.id is None:
        return []

    window_start = session.started_at
    window_end = (session.ended_at or session.started_at) + timedelta(days=window_days)
    confounders = await _confounders_in_window(
        conn, window_start, window_end, project_id=project_id, exclude_id=None
    )

    measured: list[Consequence] = []
    for metric in metrics:
        baseline = await _score_before(conn, project_id, metric, window_start)
        observed = await _score_within(conn, project_id, metric, window_start, window_end)
        if baseline is None or observed is None:
            continue
        consequence = _build_consequence(
            metric, baseline, observed, window_start, window_end, confounders,
            session_id=session.id,
        )
        if consequence is None:
            continue
        if persist:
            consequence = await repo.insert_consequence(conn, consequence)
        measured.append(consequence)
    return measured
