"""The `mri fusion` CLI command, exercised through the real Click runner.

Self-review rule 13: a CLI is verified by running the command, not by reading
the diff. This drives the actual command against a synthetic repo that is the
workspace, with a scan (for hotspots) and a session log (for authorship), and
asserts the signature sentence reaches stdout.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from mri.cli import cli
from mri.db.repository import connect_sync


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "app.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "feat: add app.py")
    return r


def _seed_scan_with_hotspot(db_path: Path, project_path: str, file_path: str, score: float) -> None:
    """A minimal completed scan whose one finding flags `file_path` — enough for
    top_risk_files to return it as a hotspot."""
    from mri.db.migrator import migrate

    migrate(db_path)
    conn = connect_sync(db_path)
    try:
        pid = conn.execute(
            "INSERT INTO projects (path, name, default_branch) VALUES (?, 'repo', 'HEAD')",
            (project_path,),
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
            " VALUES (?, 'git_history', 'high', 'hotspot', 'churn', ?, ?)",
            (rid, file_path, score),
        )
        conn.commit()
    finally:
        conn.close()


def test_fusion_command_runs_and_prints_the_signature_sentence(repo: Path, tmp_path: Path):
    db = tmp_path / "mri.db"
    home = tmp_path / "home"
    proj = home / ".claude" / "projects" / "slug"
    proj.mkdir(parents=True)
    cwd = str(repo)
    (proj / "s.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"type": "assistant", "sessionId": "s1", "cwd": cwd,
         "timestamp": "2026-05-01T10:00:00.000Z",
         "message": {"content": [
             {"type": "tool_use", "id": "u1", "name": "Write",
              "input": {"file_path": str(repo / "app.py")}}]}},
        {"type": "user", "sessionId": "s1", "cwd": cwd,
         "timestamp": "2026-05-01T10:01:00.000Z",
         "message": {"content": [{"type": "tool_result", "tool_use_id": "u1", "content": "ok"}]}},
    ]) + "\n", encoding="utf-8")

    _seed_scan_with_hotspot(db, str(repo.resolve()), "app.py", 80.0)

    # HOME/USERPROFILE steer where the session reader looks; MRI_DB isolates the DB.
    env = {"MRI_DB": str(db), "HOME": str(home), "USERPROFILE": str(home)}
    result = CliRunner().invoke(cli, ["fusion", str(repo), "--top", "5"], env=env)

    assert result.exit_code == 0, result.output
    assert "app.py" in result.output
    assert "AI-authored" in result.output, "the signature sentence reached stdout"


def test_fusion_command_json_out(repo: Path, tmp_path: Path):
    db = tmp_path / "mri.db"
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    _seed_scan_with_hotspot(db, str(repo.resolve()), "app.py", 80.0)
    out = tmp_path / "fusion.json"

    env = {"MRI_DB": str(db), "HOME": str(home), "USERPROFILE": str(home)}
    result = CliRunner().invoke(
        cli, ["fusion", str(repo), "--json-out", str(out), "--quiet"], env=env
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "files" in payload
    assert payload["files"][0]["file"] == "app.py"
    assert "prose" in payload["files"][0]
    # 9.1: the payload validates against its model (and carries authored_files,
    # which the old hand-built dict omitted).
    from mri.models.cli_json import FusionJson

    model = FusionJson.model_validate(payload)
    assert model.authored_files == payload["authored_files"]


def test_fusion_on_a_non_git_directory_fails_cleanly(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    db = tmp_path / "mri.db"
    result = CliRunner().invoke(cli, ["fusion", str(plain)], env={"MRI_DB": str(db)})
    assert result.exit_code == 1
    assert "not a git repository" in result.output
