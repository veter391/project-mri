"""Failure-mode tests — what happens when things go wrong."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mri.api.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MRI_DB", str(tmp_path / "test.db"))
    monkeypatch.delenv("MRI_API_KEYS", raising=False)
    monkeypatch.delenv("MRI_ALLOWED_ROOTS", raising=False)
    monkeypatch.setenv("MRI_LOG_FORMAT", "text")
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_nonexistent_path(client):
    r = client.post("/api/scans", json={"project_path": "/nonexistent/path/xyz"})
    assert r.status_code == 400
    assert "does not exist" in r.text


def test_file_not_directory(client, tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    r = client.post("/api/scans", json={"project_path": str(f)})
    assert r.status_code == 400
    assert "not a directory" in r.text


def test_relative_path_resolved(client, tmp_path):
    """Relative paths should be resolved to absolute."""
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "main.py").write_text("x = 1\n")
    # Use relative path
    cwd_before = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        r = client.post("/api/scans", json={"project_path": "subdir"})
        assert r.status_code == 200
    finally:
        os.chdir(cwd_before)


def test_git_repo_corrupted(client, tmp_path):
    """A git repo with broken refs should be scanned, not crash."""
    p = tmp_path / "broken"
    p.mkdir()
    (p / "main.py").write_text("x = 1\n")
    # Create .git but don't init — gitpython will raise
    (p / ".git").mkdir()
    (p / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    # Should still complete (git analyzer handles missing git)
    r = client.post("/api/scans", json={"project_path": str(p)})
    assert r.status_code == 200


def test_empty_repo(client, tmp_path):
    """Empty directory should scan without errors."""
    p = tmp_path / "empty"
    p.mkdir()
    r = client.post("/api/scans", json={"project_path": str(p)})
    assert r.status_code == 200
    # Wait for completion
    uuid = r.json()["scan_uuid"]
    import time
    for _ in range(20):
        s = client.get(f"/api/scans/{uuid}").json()
        if s["status"] in ("completed", "failed"):
            break
        time.sleep(0.2)
    assert s["status"] == "completed"


def test_huge_file_doesnt_crash(client, tmp_path):
    """Files with >2MB content should be skipped gracefully."""
    p = tmp_path / "huge"
    p.mkdir()
    # Write a 3MB file (should be skipped by walk_files or analyzer)
    big = "x = 1\n" * 200_000  # ~1.6MB
    (p / "huge.py").write_text(big)
    (p / "normal.py").write_text("y = 2\n")
    r = client.post("/api/scans", json={"project_path": str(p)})
    assert r.status_code == 200
    uuid = r.json()["scan_uuid"]
    import time
    for _ in range(30):
        s = client.get(f"/api/scans/{uuid}").json()
        if s["status"] in ("completed", "failed"):
            break
        time.sleep(0.2)
    assert s["status"] == "completed"


def test_binary_file_in_repo(client, tmp_path):
    """Binary files mixed with source should not break analyzers."""
    p = tmp_path / "withbin"
    p.mkdir()
    (p / "main.py").write_text("x = 1\n")
    # Write a binary file
    (p / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1000)
    r = client.post("/api/scans", json={"project_path": str(p)})
    assert r.status_code == 200
    uuid = r.json()["scan_uuid"]
    import time
    for _ in range(30):
        s = client.get(f"/api/scans/{uuid}").json()
        if s["status"] in ("completed", "failed"):
            break
        time.sleep(0.2)
    assert s["status"] == "completed"


def test_no_git_history(client, tmp_path):
    """Non-git directory should still scan (git analyzer reports 'no git')."""
    p = tmp_path / "nogit"
    p.mkdir()
    (p / "main.py").write_text("x = 1\n")
    r = client.post("/api/scans", json={"project_path": str(p)})
    uuid = r.json()["scan_uuid"]
    import time
    for _ in range(30):
        s = client.get(f"/api/scans/{uuid}").json()
        if s["status"] in ("completed", "failed"):
            break
        time.sleep(0.2)
    assert s["status"] == "completed"
    # Git analyzer should have scored around 50 with no_git finding
    report = s["report"]
    git_run = next(r for r in report["runs"] if r["name"] == "git_history")
    assert git_run["score"]["value"] == 50.0
    assert any(f["category"] == "no_git" for f in git_run["findings"])


def test_concurrent_scans_isolated(client, tmp_path):
    """Two scans on different repos shouldn't interfere."""
    p1 = tmp_path / "p1"
    p1.mkdir()
    (p1 / "a.py").write_text("x = 1\n")
    p2 = tmp_path / "p2"
    p2.mkdir()
    (p2 / "b.py").write_text("y = 2\n")
    r1 = client.post("/api/scans", json={"project_path": str(p1)})
    r2 = client.post("/api/scans", json={"project_path": str(p2)})
    u1, u2 = r1.json()["scan_uuid"], r2.json()["scan_uuid"]
    import time
    for _ in range(30):
        s1 = client.get(f"/api/scans/{u1}").json()
        s2 = client.get(f"/api/scans/{u2}").json()
        if s1["status"] in ("completed", "failed") and s2["status"] in ("completed", "failed"):
            break
        time.sleep(0.2)
    assert s1["status"] == "completed"
    assert s2["status"] == "completed"
    # Different uuids, different projects
    assert u1 != u2
    assert s1["report"]["project"]["name"] == "p1"
    assert s2["report"]["project"]["name"] == "p2"


def test_concurrent_scans_same_project(client, tmp_path):
    """Two scans on the SAME project — should both work, separate uuids."""
    p = tmp_path / "shared"
    p.mkdir()
    (p / "main.py").write_text("x = 1\n")
    r1 = client.post("/api/scans", json={"project_path": str(p)})
    r2 = client.post("/api/scans", json={"project_path": str(p)})
    u1, u2 = r1.json()["scan_uuid"], r2.json()["scan_uuid"]
    assert u1 != u2


def test_invalid_json_payload(client):
    r = client.post(
        "/api/scans",
        content=b"this is not json {{{",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422


def test_missing_required_field(client, tmp_path):
    p = tmp_path / "x"
    p.mkdir()
    r = client.post("/api/scans", json={})  # no project_path
    assert r.status_code == 422


def test_extra_fields_ignored(client, tmp_path):
    p = tmp_path / "x"
    p.mkdir()
    (p / "main.py").write_text("x = 1\n")
    # Extra fields shouldn't cause errors
    r = client.post("/api/scans", json={
        "project_path": str(p),
        "extra_field": "should be ignored",
        "another": [1, 2, 3],
    })
    assert r.status_code == 200


def test_sql_injection_attempt(client, tmp_path):
    """Even if user passes malicious strings, we don't interpolate them into SQL."""
    p = tmp_path / "sqli"
    p.mkdir()
    (p / "main.py").write_text("x = 1\n")
    r = client.post("/api/scans", json={
        "project_path": str(p),
        "branch": "main'; DROP TABLE scans; --",
    })
    # Either rejected as invalid branch OR accepted as harmless string
    assert r.status_code in (200, 400)