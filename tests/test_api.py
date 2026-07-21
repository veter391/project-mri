"""Integration test: scan a tiny git repo via the API."""
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mri.api.app import create_app


@pytest.fixture
def tmp_repo():
    """Create a tiny git repo we can scan."""
    d = tempfile.mkdtemp()
    p = Path(d)
    (p / "main.py").write_text("import os\n\ndef main():\n    print('hi')\n")
    (p / "utils.py").write_text("# TODO: write tests\ndef add(a, b):\n    return a + b\n")
    subprocess.check_call(["git", "init", "-q"], cwd=p)
    subprocess.check_call(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=p)
    subprocess.check_call(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"], cwd=p)
    yield p
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with isolated DB."""
    db_path = tmp_path / "test-mri.db"
    monkeypatch.setenv("MRI_DB", str(db_path))
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["version"]


def test_demo_scan(client):
    r = client.get("/api/demo/scan?slug=test")
    assert r.status_code == 200
    data = r.json()
    assert "scores" in data
    assert len(data["scores"]) == 6
    assert data["overall_health"] > 0


def test_real_scan_end_to_end(client, tmp_repo):
    """POST /api/scans on a real repo, poll for completion."""
    r = client.post("/api/scans", json={"project_path": str(tmp_repo)})
    assert r.status_code == 200
    scan_uuid = r.json()["scan_uuid"]

    # Poll for completion
    for _ in range(30):
        sr = client.get(f"/api/scans/{scan_uuid}")
        assert sr.status_code == 200
        status = sr.json()["status"]
        if status == "completed":
            break
        if status == "failed":
            pytest.fail(f"scan failed: {sr.json()}")
        import time
        time.sleep(0.5)

    sr = client.get(f"/api/scans/{scan_uuid}")
    assert sr.json()["status"] == "completed"
    report = sr.json()["report"]
    assert report["overall_health"] > 0
    assert len(report["runs"]) == 6
    assert report["stats"]["file_count"] >= 2


def test_projects_list(client, tmp_repo):
    client.post("/api/scans", json={"project_path": str(tmp_repo)})
    import time
    time.sleep(2)
    r = client.get("/api/projects")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1
    # Each project carries its id, so a client can address /projects/{id}/fusion.
    assert isinstance(data["projects"][0]["id"], int)


def test_scans_list(client):
    r = client.get("/api/scans")
    assert r.status_code == 200
    assert "scans" in r.json()


def test_openapi_docs(client):
    r = client.get("/api/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert "/api/scans" in spec["paths"]
    assert "/api/demo/scan" in spec["paths"]


def test_report_html(client):
    r = client.get("/api/demo/report.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "project-mri" in r.text


def test_report_json(client):
    r = client.get("/api/demo/report.json")
    assert r.status_code == 200
    data = r.json()
    assert "scores" in data
    assert "overall_health" in data