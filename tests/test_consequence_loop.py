"""The consequence loop.

The layer most able to lie about cause and effect, so the tests are about what
it refuses: no causation, no finding when it cannot measure, confounders always
named, confidence never high. A metric moving after a decision is correlation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from mri.db import fusion_repository as repo
from mri.db.migrator import migrate
from mri.db.repository import get_connection
from mri.fusion import measure_consequence, measure_decision_consequences
from mri.models.fusion import Decision


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "cl.db"
    migrate(path)
    return path


async def _project(conn) -> int:
    cur = await conn.execute("INSERT INTO projects (name, path) VALUES ('p', '/p')")
    await conn.commit()
    return int(cur.lastrowid)


async def _scan_with_score(conn, project_id: int, started_at: datetime, metric: str, value: float):
    cur = await conn.execute(
        "INSERT INTO scans (project_id, scan_uuid, status, started_at) VALUES (?, ?, 'completed', ?)",
        (project_id, f"u-{started_at.isoformat()}-{metric}", started_at.isoformat()),
    )
    scan_id = int(cur.lastrowid)
    await conn.execute(
        "INSERT INTO analyzer_runs (scan_id, analyzer_name, status, score_value, score_label)"
        " VALUES (?, ?, 'completed', ?, ?)",
        (scan_id, metric, value, metric),
    )
    await conn.commit()


async def _decision(
    conn, when: datetime, summary: str = "did a thing", *, project_id: int | None = None
) -> Decision:
    d = await repo.insert_decision(
        conn,
        Decision(summary=summary, source="commit", source_ref=summary[:8],
                 project_id=project_id, decided_at=when, confidence=0.6),
    )
    return d


def _dt(day: int) -> datetime:
    return datetime(2026, 3, day, tzinfo=timezone.utc)


async def test_it_measures_a_before_and_after_delta(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(1), "architecture", 60.0)   # before
        decision = await _decision(conn, _dt(10))
        await _scan_with_score(conn, pid, _dt(20), "architecture", 75.0)  # after

        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert c is not None
    assert c.baseline_value == 60.0
    assert c.observed_value == 75.0
    assert c.delta == 15.0


async def test_it_only_ever_claims_correlation(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(1), "architecture", 60.0)
        decision = await _decision(conn, _dt(10))
        await _scan_with_score(conn, pid, _dt(20), "architecture", 90.0)
        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert c.causal_claim == "correlation"


async def test_no_scan_before_the_decision_is_not_measurable(db: Path):
    """A metric with no baseline before the decision cannot yield a delta. That
    is absence, returned as None — not a zero delta presented as a finding."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        decision = await _decision(conn, _dt(10))
        await _scan_with_score(conn, pid, _dt(20), "architecture", 75.0)  # only after
        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert c is None


async def test_no_scan_after_the_decision_in_the_window_is_not_measurable(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(1), "architecture", 60.0)
        decision = await _decision(conn, _dt(10))
        # The only later scan is far outside the 30-day window.
        await _scan_with_score(conn, pid, datetime(2026, 8, 1, tzinfo=timezone.utc), "architecture", 75.0)
        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert c is None


async def test_a_dateless_decision_is_not_measurable(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(1), "architecture", 60.0)
        decision = await repo.insert_decision(
            conn, Decision(summary="undated", source="manual", decided_at=None)
        )
        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert c is None


async def test_other_decisions_in_the_window_are_named_as_confounders(db: Path):
    """The honest caveat: something else changed in the same span. Each other
    decision is listed, and the confidence falls as they accumulate."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(1), "architecture", 60.0)
        decision = await _decision(conn, _dt(10), "the decision under test", project_id=pid)
        await _decision(conn, _dt(12), "a confounding change", project_id=pid)
        await _decision(conn, _dt(15), "another confounding change", project_id=pid)
        await _scan_with_score(conn, pid, _dt(20), "architecture", 75.0)

        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert len(c.confounders) == 2, "the two co-occurring decisions, not the one under test"
    assert all("confounding" in note for note in c.confounders)


async def test_confidence_is_never_high_and_drops_with_confounders(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(1), "architecture", 60.0)
        alone = await _decision(conn, _dt(10), "alone in its window", project_id=pid)
        await _scan_with_score(conn, pid, _dt(20), "architecture", 75.0)
        c_alone = await measure_consequence(conn, alone, "architecture", project_id=pid)

        crowded = await _decision(conn, _dt(11), "crowded", project_id=pid)
        await _decision(conn, _dt(12), "noise one", project_id=pid)
        await _decision(conn, _dt(13), "noise two", project_id=pid)
        c_crowded = await measure_consequence(conn, crowded, "architecture", project_id=pid)

    assert c_alone.confidence <= 0.6, "a before/after over a window is never certain"
    assert c_crowded.confidence < c_alone.confidence, "more confounders, less confidence"


async def test_the_decision_under_test_is_not_its_own_confounder(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(1), "architecture", 60.0)
        decision = await _decision(conn, _dt(10), "the only decision")
        await _scan_with_score(conn, pid, _dt(20), "architecture", 75.0)
        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert c.confounders == []


async def test_measure_many_metrics_skips_the_unmeasurable_and_persists_the_rest(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(1), "architecture", 60.0)
        # 'complexity' has no baseline before the decision, so it is unmeasurable.
        decision = await _decision(conn, _dt(10))
        await _scan_with_score(conn, pid, _dt(20), "architecture", 70.0)
        await _scan_with_score(conn, pid, _dt(20), "complexity", 40.0)

        results = await measure_decision_consequences(
            conn, decision, ["architecture", "complexity"], project_id=pid
        )
        assert [c.metric for c in results] == ["architecture"], "complexity had no baseline"
        assert results[0].id is not None, "measured consequences are persisted by default"

        cur = await conn.execute("SELECT count(*) FROM consequences")
        assert (await cur.fetchone())[0] == 1


async def test_measurements_can_be_computed_without_persisting(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(1), "architecture", 60.0)
        decision = await _decision(conn, _dt(10))
        await _scan_with_score(conn, pid, _dt(20), "architecture", 70.0)

        results = await measure_decision_consequences(
            conn, decision, ["architecture"], project_id=pid, persist=False
        )
        assert len(results) == 1
        cur = await conn.execute("SELECT count(*) FROM consequences")
        assert (await cur.fetchone())[0] == 0, "persist=False stores nothing"


async def test_a_regression_is_reported_as_a_negative_delta(db: Path):
    """The loop reports what happened, good or bad. A metric that fell after a
    decision is a negative delta, not a suppressed one."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(1), "architecture", 80.0)
        decision = await _decision(conn, _dt(10))
        await _scan_with_score(conn, pid, _dt(20), "architecture", 55.0)
        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert c.delta == -25.0


# ---------------------------------------------------------------------------
# What the block-8 audits found
# ---------------------------------------------------------------------------


async def test_another_projects_decision_is_not_a_confounder(db: Path):
    """Cross-project leak: a decision in project B was counted as a confounder
    for project A and leaked B's summary. Confounders are scoped to the project."""
    async with get_connection(db) as conn:
        a = await _project(conn)
        b = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('B', '/b')")).lastrowid)
        await conn.commit()
        await _scan_with_score(conn, a, _dt(1), "architecture", 60.0)
        decision = await _decision(conn, _dt(10), "A under test", project_id=a)
        await _decision(conn, _dt(12), "B private decision", project_id=b)  # other project
        await _scan_with_score(conn, a, _dt(20), "architecture", 75.0)

        c = await measure_consequence(conn, decision, "architecture", project_id=a)
    assert c.confounders == [], "another project's decision must not appear"
    assert c.confidence == 0.6, "and must not drag this project's confidence down"


async def test_a_commit_authored_outside_utc_is_ordered_by_its_instant(db: Path):
    """The critical bug: ISO strings with different offsets sort lexically, so a
    +09:00 commit date sorted between two UTC scans and a post-decision scan was
    picked as the baseline. Timestamps are normalised to UTC before comparison."""
    from datetime import timedelta

    async with get_connection(db) as conn:
        pid = await _project(conn)
        # Decision authored at +09:00 on the 10th 01:00 == 09th 16:00 UTC.
        local = datetime(2026, 3, 10, 1, 0, tzinfo=timezone(timedelta(hours=9)))
        await _scan_with_score(conn, pid, datetime(2026, 3, 9, 10, 0, tzinfo=timezone.utc), "architecture", 50.0)   # true before
        await _scan_with_score(conn, pid, datetime(2026, 3, 9, 18, 0, tzinfo=timezone.utc), "architecture", 999.0)  # after the decision
        await _scan_with_score(conn, pid, datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc), "architecture", 1000.0) # true after
        decision = await _decision(conn, local, "tz decision", project_id=pid)

        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert c.baseline_value == 50.0, "the true pre-decision scan, not one after it"
    assert c.delta == 950.0


async def test_a_scan_exactly_at_the_decision_moment_is_the_baseline(db: Path):
    """Boundary: <= for the baseline, > for the observed, so a scan at the exact
    decision instant is the state going in, not the effect coming out."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(10), "architecture", 60.0)  # exactly at decision
        decision = await _decision(conn, _dt(10), project_id=pid)
        await _scan_with_score(conn, pid, _dt(20), "architecture", 70.0)
        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert c.baseline_value == 60.0
    assert c.observed_value == 70.0


async def test_the_closest_scan_before_the_decision_is_the_baseline(db: Path):
    """With several pre-decision scans, the most recent one is the state going
    in — not the oldest."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(1), "architecture", 10.0)  # old
        await _scan_with_score(conn, pid, _dt(8), "architecture", 60.0)  # closest before
        decision = await _decision(conn, _dt(10), project_id=pid)
        await _scan_with_score(conn, pid, _dt(20), "architecture", 70.0)
        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert c.baseline_value == 60.0, "the closest pre-decision scan, not the oldest"


async def test_the_latest_scan_in_the_window_is_the_observed(db: Path):
    """The effect is read at the end of the window: the latest in-window scan,
    not the first."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(1), "architecture", 60.0)
        decision = await _decision(conn, _dt(10), project_id=pid)
        await _scan_with_score(conn, pid, _dt(15), "architecture", 65.0)  # early in window
        await _scan_with_score(conn, pid, _dt(25), "architecture", 80.0)  # latest in window
        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert c.observed_value == 80.0, "the latest in-window scan, not the earliest"


async def test_a_non_finite_score_is_not_a_measurement(db: Path):
    """An inf score from an upstream analyzer bug must not be stored as a real
    delta. It is dropped like any unmeasurable metric."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        sid = int((await conn.execute(
            "INSERT INTO scans (project_id, scan_uuid, status, started_at) VALUES (?, 'u-inf', 'completed', ?)",
            (pid, _dt(1).isoformat()),
        )).lastrowid)
        await conn.execute(
            "INSERT INTO analyzer_runs (scan_id, analyzer_name, status, score_value, score_label)"
            " VALUES (?, 'architecture', 'completed', ?, 'architecture')",
            (sid, float("inf")),
        )
        await conn.commit()
        decision = await _decision(conn, _dt(10), project_id=pid)
        await _scan_with_score(conn, pid, _dt(20), "architecture", 70.0)
        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert c is None, "a non-finite baseline yields no consequence, not an inf delta"


async def test_confounders_are_capped_with_a_truthful_remainder(db: Path):
    """A window with thousands of decisions gets a sample plus an honest count,
    not a multi-megabyte list written into one row."""
    from mri.fusion.consequences import MAX_CONFOUNDERS_LISTED

    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _scan_with_score(conn, pid, _dt(1), "architecture", 60.0)
        decision = await _decision(conn, _dt(10), "under test", project_id=pid)
        for i in range(MAX_CONFOUNDERS_LISTED + 20):
            await _decision(conn, _dt(11), f"noise {i}", project_id=pid)
        await _scan_with_score(conn, pid, _dt(20), "architecture", 70.0)

        c = await measure_consequence(conn, decision, "architecture", project_id=pid)
    assert len(c.confounders) == MAX_CONFOUNDERS_LISTED + 1, "sample plus a remainder line"
    assert "more decision(s)" in c.confounders[-1]
    # Confidence reflects the TRUE count, not the truncated sample.
    assert c.confidence < 0.6 / MAX_CONFOUNDERS_LISTED
