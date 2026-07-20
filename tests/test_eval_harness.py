"""The evaluation harness (block 1.6 / plan Phase 10).

Two things must be true for the harness to mean anything: the calibration must
match known ground truth, and the over-claim guard must actually CATCH bad data
— a guard that never fails is theatre. Both are pinned here, plus the `mri eval`
CLI gate.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from mri.db.migrator import migrate
from mri.db.repository import connect_sync, get_connection
from mri.eval import audit_project, run_eval


async def test_calibration_matches_known_ground_truth(tmp_path: Path):
    """The whole point: on a repo whose true AI-authorship is constructed, the
    computed share matches — 100% for an agent-written file, 0% for a human one,
    50% for a half-and-half file."""
    report = await run_eval(tmp_path)
    assert report.calibration["ai_all.py"][1] == pytest.approx(100.0, abs=2.0)
    assert report.calibration["human_all.py"][1] == pytest.approx(0.0, abs=2.0)
    assert report.calibration["mixed.py"][1] == pytest.approx(50.0, abs=2.0)
    assert report.correlation_recall == 1.0
    assert report.violations == []
    assert report.passed


async def test_the_guard_catches_a_causation_claim(tmp_path: Path):
    """A guard that cannot fail is worthless. Inject a consequence claiming
    causation and assert the guard flags it."""
    db = tmp_path / "g.db"
    migrate(db)
    async with get_connection(db) as conn:
        pid = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('p','/p')")).lastrowid)
        did = int((await conn.execute(
            "INSERT INTO decisions (summary, source, project_id) VALUES ('d','commit',?)", (pid,)
        )).lastrowid)
        await conn.execute(
            "INSERT INTO consequences (decision_id, metric, window_start, window_end, delta, causal_claim)"
            " VALUES (?, 'risk', '2026-01-01', '2026-02-01', 20.0, 'causation')",
            (did,),
        )
        await conn.commit()
        violations = await audit_project(conn, pid)
    rules = {v.rule for v in violations}
    assert "never_causation" in rules


async def test_the_guard_catches_a_human_share_from_the_blame_method(tmp_path: Path):
    """The DB allows a human share (other methods use it), so a blame-derived row
    claiming one is a real over-claim the guard must catch — absence of AI
    evidence is unattributed, never human."""
    db = tmp_path / "g.db"
    migrate(db)
    conn = connect_sync(db)
    try:
        pid = conn.execute("INSERT INTO projects (name, path) VALUES ('p','/p')").lastrowid
        conn.execute(
            "INSERT INTO authorship_shares (project_id, file_path, share_ai, share_human,"
            " share_unattributed, method, confidence)"
            " VALUES (?, 'a.py', 40, 20, 40, 'blame_session_commit', 0.5)",
            (pid,),
        )
        conn.commit()
    finally:
        conn.close()
    async with get_connection(db) as conn:
        violations = await audit_project(conn, pid)
    assert "no_human_from_blame" in {v.rule for v in violations}


async def test_the_guard_catches_full_confidence(tmp_path: Path):
    db = tmp_path / "g.db"
    migrate(db)
    conn = connect_sync(db)
    try:
        pid = conn.execute("INSERT INTO projects (name, path) VALUES ('p','/p')").lastrowid
        conn.execute(
            "INSERT INTO authorship_shares (project_id, file_path, share_ai, share_human,"
            " share_unattributed, method, confidence) VALUES (?, 'a.py', 100, 0, 0, 'x', 1.0)",
            (pid,),
        )
        conn.commit()
    finally:
        conn.close()
    async with get_connection(db) as conn:
        violations = await audit_project(conn, pid)
    assert "confidence_below_1" in {v.rule for v in violations}


async def test_a_clean_project_has_no_violations(tmp_path: Path):
    db = tmp_path / "g.db"
    migrate(db)
    async with get_connection(db) as conn:
        pid = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('p','/p')")).lastrowid)
        await conn.commit()
        assert await audit_project(conn, pid) == []


def test_mri_eval_cli_passes_and_gates(tmp_path: Path):
    """The `mri eval` command runs the harness and exits 0 when calibrated and
    clean — the CI gate."""
    from mri.cli import cli

    out = tmp_path / "eval.json"
    result = CliRunner().invoke(cli, ["eval", "--json-out", str(out)])
    assert result.exit_code == 0, result.output
    assert "eval passed" in result.output
    import json
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["calibration"]["ai_all.py"]["computed"] == pytest.approx(100.0, abs=2.0)
