"""The fusion HTTP endpoint, exercised through the real FastAPI TestClient.

The heavy fusion run happens elsewhere; this endpoint reads stored results. The
tests seed fusion data into the isolated DB and assert the endpoint reassembles
the per-file explanation, 404s an unknown project, and honestly returns an empty
list for a project with no scored files.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mri.api.app import create_app
from mri.db.migrator import migrate
from mri.db.repository import connect_sync


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "api-mri.db"
    monkeypatch.setenv("MRI_DB", str(path))
    migrate(path)
    return path


@pytest.fixture
def client(db_path: Path) -> TestClient:
    with TestClient(create_app()) as c:
        yield c


def _seed_project_with_fusion(db_path: Path) -> int:
    """A project with a hotspot finding and a stored blame-derived AI share."""
    conn = connect_sync(db_path)
    try:
        pid = conn.execute(
            "INSERT INTO projects (path, name, default_branch) VALUES ('/p', 'demo', 'HEAD')"
        ).lastrowid
        sid = conn.execute(
            "INSERT INTO scans (project_id, scan_uuid, status) VALUES (?, 'u1', 'completed')",
            (pid,),
        ).lastrowid
        rid = conn.execute(
            "INSERT INTO analyzer_runs (scan_id, analyzer_name, status, score_value, score_label)"
            " VALUES (?, 'git_history', 'completed', 50.0, 'git_health')",
            (sid,),
        ).lastrowid
        conn.execute(
            "INSERT INTO findings (run_id, analyzer_name, severity, category, title, target_path, score)"
            " VALUES (?, 'git_history', 'high', 'hotspot', 'churn', 'app.py', 82.0)",
            (rid,),
        )
        conn.execute(
            "INSERT INTO authorship_shares (project_id, file_path, share_ai, share_human,"
            " share_unattributed, method, confidence) VALUES (?, 'app.py', 90, 0, 10,"
            " 'blame_session_commit', 0.9)",
            (pid,),
        )
        conn.commit()
        return int(pid)
    finally:
        conn.close()


def test_fusion_endpoint_returns_the_stored_explanation(client: TestClient, db_path: Path):
    pid = _seed_project_with_fusion(db_path)
    r = client.get(f"/api/projects/{pid}/fusion")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project"] == "demo"
    assert len(body["files"]) == 1
    f = body["files"][0]
    assert f["file"] == "app.py"
    assert "90% of its current lines are AI-authored" in f["prose"]
    assert "risk 82/100" in f["prose"]
    # The machine-readable factors accompany the prose.
    names = {factor["name"] for factor in f["factors"]}
    assert {"risk", "ai_authorship"} <= names


def test_unknown_project_is_404(client: TestClient):
    r = client.get("/api/projects/9999/fusion")
    assert r.status_code == 404


def test_a_project_with_no_scored_files_returns_empty(client: TestClient, db_path: Path):
    conn = connect_sync(db_path)
    try:
        pid = conn.execute(
            "INSERT INTO projects (path, name, default_branch) VALUES ('/q', 'quiet', 'HEAD')"
        ).lastrowid
        conn.commit()
    finally:
        conn.close()
    r = client.get(f"/api/projects/{pid}/fusion")
    assert r.status_code == 200
    assert r.json()["files"] == [], "no hotspots is an honest empty list, not an error"


def test_the_endpoint_is_project_scoped(client: TestClient, db_path: Path):
    """Two projects share a file path with different AI shares; each project's
    endpoint must return only its own — the cross-project isolation the fusion
    layers enforce, verified at the HTTP boundary."""
    conn = connect_sync(db_path)
    try:
        ids = {}
        for name, ai in (("A", 90), ("B", 10)):
            p = conn.execute(
                "INSERT INTO projects (path, name, default_branch) VALUES (?, ?, 'HEAD')",
                (f"/{name}", name),
            ).lastrowid
            s = conn.execute(
                "INSERT INTO scans (project_id, scan_uuid, status) VALUES (?, ?, 'completed')",
                (p, f"u{p}"),
            ).lastrowid
            r = conn.execute(
                "INSERT INTO analyzer_runs (scan_id, analyzer_name, status, score_value, score_label)"
                " VALUES (?, 'git_history', 'completed', 50, 'g')",
                (s,),
            ).lastrowid
            conn.execute(
                "INSERT INTO findings (run_id, analyzer_name, severity, category, title, target_path, score)"
                " VALUES (?, 'git_history', 'high', 'hotspot', 'x', 'README.md', 80)",
                (r,),
            )
            conn.execute(
                "INSERT INTO authorship_shares (project_id, file_path, share_ai, share_human,"
                " share_unattributed, method, confidence)"
                " VALUES (?, 'README.md', ?, 0, ?, 'blame_session_commit', 0.9)",
                (p, ai, 100 - ai),
            )
            ids[name] = int(p)
        conn.commit()
    finally:
        conn.close()

    prose_a = client.get(f"/api/projects/{ids['A']}/fusion").json()["files"][0]["prose"]
    prose_b = client.get(f"/api/projects/{ids['B']}/fusion").json()["files"][0]["prose"]
    assert "90% of its current lines" in prose_a
    assert "10% of its current lines" not in prose_a, "project B's share must not leak into A"
    assert "10% of its current lines" in prose_b


def test_the_endpoint_leads_with_the_agent_attributable_file(client: TestClient, db_path: Path):
    """The HTTP surface orders by authorship-weighted risk like the CLI and MCP
    (ADR-011): an agent-written file at base risk 60 leads an untouched one at
    base risk 95, so a user diffing the API against `mri fusion` sees the same
    top file. Both are still returned."""
    conn = connect_sync(db_path)
    try:
        pid = conn.execute(
            "INSERT INTO projects (path, name, default_branch) VALUES ('/o', 'ord', 'HEAD')"
        ).lastrowid
        sid = conn.execute(
            "INSERT INTO scans (project_id, scan_uuid, status) VALUES (?, 'u1', 'completed')",
            (pid,),
        ).lastrowid
        rid = conn.execute(
            "INSERT INTO analyzer_runs (scan_id, analyzer_name, status, score_value, score_label)"
            " VALUES (?, 'git_history', 'completed', 50, 'g')",
            (sid,),
        ).lastrowid
        for path, score in (("touched.py", 60.0), ("untouched.py", 95.0)):
            conn.execute(
                "INSERT INTO findings (run_id, analyzer_name, severity, category, title,"
                " target_path, score) VALUES (?, 'git_history', 'high', 'hotspot', 'x', ?, ?)",
                (rid, path, score),
            )
        session_id = conn.execute(
            "INSERT INTO sessions (source, external_id, project_id) VALUES ('claude_code', 's1', ?)",
            (pid,),
        ).lastrowid
        # A write touch only on the lower-base-risk file: it gets evidence
        # strength 0.9 (weighted 54), the untouched file weights to 0.
        conn.execute(
            "INSERT INTO session_file_touches (session_id, project_id, file_path, touch_kind,"
            " confidence, occurred_at) VALUES (?, ?, 'touched.py', 'write', 0.9, '2026-05-01T10:00:00Z')",
            (session_id, pid),
        )
        conn.commit()
    finally:
        conn.close()

    files = client.get(f"/api/projects/{pid}/fusion").json()["files"]
    order = [f["file"] for f in files]
    assert order == ["touched.py", "untouched.py"], "agent-attributable risk leads; both present"


def test_top_is_bounded(client: TestClient, db_path: Path):
    pid = _seed_project_with_fusion(db_path)
    assert client.get(f"/api/projects/{pid}/fusion?top=0").status_code == 422
    assert client.get(f"/api/projects/{pid}/fusion?top=101").status_code == 422
    assert client.get(f"/api/projects/{pid}/fusion?top=5").status_code == 200
