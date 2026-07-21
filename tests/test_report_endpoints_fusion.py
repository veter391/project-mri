"""HTTP-level cover for the fusion enrichment of report.html and report.sarif.

The unit tests exercise render_html / _to_sarif directly with hand-built data;
these go through the real endpoints with a seeded scan + authorship row, so the
endpoint's own query and per-file loop (and the SARIF GROUP-BY-equivalent helper)
are exercised, not bypassed.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mri.api.app import create_app
from mri.db import repository
from mri.db.migrator import migrate
from mri.db.repository import connect_sync, persist_report
from mri.services.scanner import Scanner, ScanOptions
from tests.golden import build_fixture_repo


@pytest.fixture
def fused_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A persisted scan with a hotspot finding + a stored AI share on app.py."""
    db = tmp_path / "e.db"
    monkeypatch.setenv("MRI_DB", str(db))
    repository._DEFAULT_PATH = None
    migrate(db)

    repo = build_fixture_repo(tmp_path / "repo")
    report = asyncio.run(Scanner().scan(str(repo), opts=ScanOptions()))
    persist_report(report)

    conn = connect_sync(db)
    try:
        pid = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()[0]
        sid = conn.execute(
            "SELECT id FROM scans WHERE project_id=? ORDER BY id DESC LIMIT 1", (pid,)
        ).fetchone()[0]
        uuid = conn.execute("SELECT scan_uuid FROM scans WHERE id=?", (sid,)).fetchone()[0]
        rid = conn.execute(
            "INSERT INTO analyzer_runs (scan_id, analyzer_name, status, score_value, score_label)"
            " VALUES (?, 'git_history', 'completed', 50, 'g')", (sid,)
        ).lastrowid
        conn.execute(
            "INSERT INTO findings (run_id, analyzer_name, severity, category, title, target_path, score)"
            " VALUES (?, 'git_history', 'high', 'hotspot', 'x', 'app.py', 82)", (rid,)
        )
        conn.execute(
            "INSERT INTO authorship_shares (project_id, file_path, share_ai, share_human,"
            " share_unattributed, method, confidence) VALUES (?, 'app.py', 88, 0, 12,"
            " 'blame_session_commit', 0.9)", (pid,)
        )
        conn.commit()
    finally:
        conn.close()
    return uuid


def test_report_html_endpoint_includes_the_fusion_section(fused_scan: str):
    with TestClient(create_app()) as c:
        r = c.get(f"/api/scans/{fused_scan}/report.html")
    assert r.status_code == 200
    assert "AI provenance" in r.text
    assert "88% of its current lines are AI-authored" in r.text
    assert 'fusion__path">app.py' in r.text


async def test_latest_authorship_shares_reads_real_rows_and_picks_the_newest(tmp_path: Path):
    """The batched helper the SARIF export uses, exercised against real rows (the
    audit flagged the query was never run against a seeded share). Two shares for
    one file: the newest (by computed_at, id) wins, and every file is keyed once."""
    from datetime import datetime, timezone

    from mri.db.fusion_repository import insert_authorship_share, latest_authorship_shares
    from mri.db.migrator import migrate as _migrate
    from mri.db.repository import get_connection
    from mri.models.fusion import AuthorshipShare

    db = tmp_path / "la.db"
    _migrate(db)
    async with get_connection(db) as conn:
        pid = int((await conn.execute("INSERT INTO projects (name,path) VALUES ('p','/p')")).lastrowid)
        await conn.commit()
        older = datetime(2026, 1, 1, tzinfo=timezone.utc)
        newer = datetime(2026, 2, 1, tzinfo=timezone.utc)
        await insert_authorship_share(conn, AuthorshipShare(
            project_id=pid, file_path="a.py", share_ai=40, share_human=0,
            share_unattributed=60, method="blame_session_commit", confidence=0.5, computed_at=older))
        await insert_authorship_share(conn, AuthorshipShare(
            project_id=pid, file_path="a.py", share_ai=90, share_human=0,
            share_unattributed=10, method="blame_session_commit", confidence=0.9, computed_at=newer))
        await insert_authorship_share(conn, AuthorshipShare(
            project_id=pid, file_path="b.py", share_ai=10, share_human=0,
            share_unattributed=90, method="blame_session_commit", confidence=0.3, computed_at=newer))
        await conn.commit()
        shares = await latest_authorship_shares(conn, pid)
    assert set(shares) == {"a.py", "b.py"}
    assert shares["a.py"].share_ai == 90, "the newest share for a file wins"
    assert shares["b.py"].share_ai == 10
