"""The `mri scan` CLI, exercised through the real Click runner.

Regression cover for a Windows-only crash: the CLI moved the generated report
onto the user's --output path with Path.rename, which raises FileExistsError on
Windows when the target already exists — so a second scan to the same path (the
common case: re-scan, same report file) crashed. The fix is replace(), the
atomic cross-platform overwrite; this pins that a repeated scan succeeds.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from click.testing import CliRunner

from mri.cli import cli


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)


def _fixture_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "t")
    (path / "app.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", "init")
    return path


def test_repeated_scan_to_the_same_output_path_succeeds(tmp_path: Path):
    """Two scans writing to one report path must both succeed — the second must
    overwrite, not crash on a pre-existing target (the Windows rename bug)."""
    repo = _fixture_repo(tmp_path / "repo")
    out = tmp_path / "report.html"
    env = {"MRI_DB": str(tmp_path / "mri.db")}

    first = CliRunner().invoke(cli, ["scan", str(repo), "--output", str(out), "-q"], env=env)
    assert first.exit_code == 0, first.output
    assert out.exists()

    second = CliRunner().invoke(cli, ["scan", str(repo), "--output", str(out), "-q"], env=env)
    assert second.exit_code == 0, second.output
    assert out.exists()
