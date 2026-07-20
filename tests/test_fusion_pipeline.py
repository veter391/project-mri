"""The fusion pipeline end to end (the orchestration a surface calls).

A synthetic repo that IS the workspace, with a session log whose cwd is that
repo, so the whole moat runs as one call: ingest -> correlate -> authorship ->
decisions -> link -> explain, and the signature sentence comes out with real,
nonzero numbers.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from mri.db.migrator import migrate
from mri.db.repository import get_connection
from mri.fusion import run_fusion


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "pipe.db"
    migrate(path)
    return path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)


def _turn(seq: int, role: str, cwd: str, parts: list[dict], sid: str = "sess-p") -> dict:
    return {
        "type": role, "sessionId": sid, "cwd": cwd,
        "timestamp": f"2026-05-{seq + 1:02d}T10:00:00.000Z",
        "message": {"content": parts},
    }


def _use(tool: str, file_path: str, use_id: str) -> dict:
    return {"type": "tool_use", "id": use_id, "name": tool, "input": {"file_path": file_path}}


def _result(use_id: str) -> dict:
    return {"type": "tool_result", "tool_use_id": use_id, "content": "ok"}


async def test_the_whole_loop_runs_and_explains_from_one_call(db: Path, tmp_path: Path):
    import git

    # A real repo that is also the workspace.
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "app.py").write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "feat: add app.py per ADR-001")
    adr_dir = repo / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-x.md").write_text(
        "# ADR-001 — First\n\n- **Status:** Accepted\n\n## Decision\nDo it.\n", encoding="utf-8"
    )

    # A session log whose cwd is the repo, writing app.py before the commit.
    home = tmp_path / "home"
    proj = home / ".claude" / "projects" / "slug"
    proj.mkdir(parents=True)
    cwd = str(repo)
    log = proj / "sess-p.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in [
        _turn(0, "assistant", cwd, [_use("Write", str(repo / "app.py"), "u1")]),
        _turn(1, "user", cwd, [_result("u1")]),
    ]) + "\n", encoding="utf-8")

    # The log's timestamp (May) is before the real commit time (now), so the
    # write touch correlates forward to the commit that carried it.
    async with get_connection(db) as conn:
        pid = int((await conn.execute(
            "INSERT INTO projects (name, path) VALUES ('p', ?)", (cwd,)
        )).lastrowid)
        await conn.commit()

        report = await run_fusion(
            conn, git.Repo(repo), repo, project_id=pid,
            hotspots={"app.py": 70.0}, adr_dir=adr_dir, home=home,
        )

    assert report.ingest.sessions == 1, "the session under this cwd was ingested"
    assert report.ingest.touches == 1
    assert report.correlation.linked == 1, "the write touch correlated to the commit"
    assert report.adrs == 1
    assert report.commits == 1
    assert report.authored_files == 1
    assert len(report.explanations) == 1

    prose = report.explanations[0].prose
    assert "app.py" in prose
    assert "100% of its current lines are AI-authored" in prose, (
        "the whole file was written in the correlated commit"
    )
    assert "risk 70/100" in prose
    assert "1 decision(s) touch it" in prose or "decision(s) touch it" in prose


async def test_no_sessions_still_runs_cleanly(db: Path, tmp_path: Path):
    """A repo no agent ever touched: the loop still ingests commits and returns,
    with honest zeros, not an error."""
    import git

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.py").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add a")

    home = tmp_path / "empty_home"
    home.mkdir()
    async with get_connection(db) as conn:
        pid = int((await conn.execute(
            "INSERT INTO projects (name, path) VALUES ('p', ?)", (str(repo),)
        )).lastrowid)
        await conn.commit()
        report = await run_fusion(conn, git.Repo(repo), repo, project_id=pid, home=home)

    assert report.ingest.sessions == 0
    assert report.commits == 1
    assert report.explanations == [], "no hotspots asked about, so no explanations"
