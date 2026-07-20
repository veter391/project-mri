"""Red->green regressions for the Phase 1 P1 fixes that lacked one (H1, H5).

H1 — git churn must count each changed line once; the original bug double-counted
deletions, so a facts-first tool reported inflated churn.
H5 — the ACTIVE_SCANS gauge must be symmetric (inc on entry, dec in finally) so a
scan, success or failure, leaves it where it started and never drives it negative.
"""
from __future__ import annotations

import asyncio
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest

from mri import metrics
from mri.analyzers.git_history import GitHistoryAnalyzer
from mri.services.scanner import ScanContext, Scanner, ScanOptions


def _git(repo: Path, *args: str) -> None:
    subprocess.check_call(["git", *args], cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _lines(n: int) -> str:
    return "".join(f"x{i} = 1\n" for i in range(n))


def test_churn_counts_each_line_once_and_does_not_double_count_deletions(tmp_path: Path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f.py").write_text(_lines(10), encoding="utf-8", newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add 10 lines")
    (repo / "f.py").write_text(_lines(5), encoding="utf-8", newline="\n")  # delete the last 5
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "delete 5 lines")

    from git import Repo

    g = Repo(repo)
    branch = g.active_branch.name
    ctx = ScanContext(project_path=repo, branch=branch, files=[], git=g)
    file_churn: dict[str, int] = {}
    file_commits: dict[str, int] = {}
    GitHistoryAnalyzer._collect_churn(
        g, ctx, branch=branch,
        file_churn=file_churn, file_commits=file_commits,
        file_authors=defaultdict(set), author_total={}, commit_dates=[],
    )
    # 10 lines added + 5 removed = 15 changed lines, each counted once. The
    # double-count bug reported the deletions twice (would be 20+).
    assert file_churn["f.py"] == 15
    assert file_commits["f.py"] == 2


def _fixture_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t")
    _git(path, "config", "user.name", "t")
    (path / "app.py").write_text("def a():\n    return 1\n", encoding="utf-8", newline="\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", "init")
    return path


def test_active_scans_gauge_is_symmetric_across_success_and_failure(tmp_path: Path):
    baseline = metrics.ACTIVE_SCANS._value.get()

    repo = _fixture_repo(tmp_path / "ok")
    asyncio.run(Scanner().scan(str(repo), opts=ScanOptions()))
    assert metrics.ACTIVE_SCANS._value.get() == baseline, "a successful scan must leave the gauge as it found it"

    with pytest.raises(ValueError):
        asyncio.run(Scanner().scan(str(tmp_path / "does-not-exist"), opts=ScanOptions()))
    assert metrics.ACTIVE_SCANS._value.get() == baseline, "a failed scan must still decrement (finally)"
    assert metrics.ACTIVE_SCANS._value.get() >= 0, "the gauge must never go negative"
