"""Regression test: a re-scan must analyse the branch it was asked for.

`git fetch` updates refs but never touches the working tree, and the analyzers
walk files on disk. Without an explicit checkout, scanning the same URL a second
time with a different branch silently analysed the previously checked-out branch
while the report claimed the requested one — a wrong answer delivered
confidently, which is the worst failure mode for this tool.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mri.services import repo_cloner


def _git(*args: str, cwd: Path) -> None:
    subprocess.check_call(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """A repo with two branches whose file contents differ."""
    repo = tmp_path / "origin"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    (repo / "file.txt").write_text("main-content\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)
    _git("checkout", "-q", "-b", "feature", cwd=repo)
    (repo / "file.txt").write_text("feature-content\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "feat", cwd=repo)
    _git("checkout", "-q", "main", cwd=repo)
    return repo


def test_rescan_with_a_different_branch_checks_it_out(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cache = tmp_path / "cache"
    monkeypatch.setattr(repo_cloner, "_default_cache_dir", lambda: cache)
    # The cloner only accepts allow-listed public hosts; this test drives the
    # cache-update path itself, so the host check is not what is under test.
    monkeypatch.setattr(repo_cloner, "_validate_clone_target", lambda repo, config: None)
    monkeypatch.setattr(repo_cloner, "_record_clone", lambda *a, **k: None)
    # parse_repo_url only understands public https/ssh forms; the cache-update
    # path under test never uses the parsed value beyond validation.
    monkeypatch.setattr(
        repo_cloner,
        "parse_repo_url",
        lambda url: repo_cloner.RepoUrl(url, "example.com", "owner", "repo", scheme="https"),
    )
    # No credentials are involved; clone straight from the local origin.
    monkeypatch.setattr(repo_cloner, "_build_authenticated_url", lambda repo, config: repo.raw)

    url = origin.as_uri()

    first = repo_cloner.clone_repo(url, branch="main", depth=1)
    assert (first / "file.txt").read_text(encoding="utf-8").strip() == "main-content"

    # Same URL, different branch — this is the cache-hit path.
    second = repo_cloner.clone_repo(url, branch="feature", depth=1)
    assert second == first, "expected the cached clone to be reused"
    assert (second / "file.txt").read_text(encoding="utf-8").strip() == "feature-content", (
        "working tree still holds the previous branch — fetch without checkout"
    )


def test_rescan_without_a_branch_picks_up_new_commits(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cache = tmp_path / "cache"
    monkeypatch.setattr(repo_cloner, "_default_cache_dir", lambda: cache)
    monkeypatch.setattr(repo_cloner, "_validate_clone_target", lambda repo, config: None)
    monkeypatch.setattr(repo_cloner, "_record_clone", lambda *a, **k: None)
    # parse_repo_url only understands public https/ssh forms; the cache-update
    # path under test never uses the parsed value beyond validation.
    monkeypatch.setattr(
        repo_cloner,
        "parse_repo_url",
        lambda url: repo_cloner.RepoUrl(url, "example.com", "owner", "repo", scheme="https"),
    )
    # No credentials are involved; clone straight from the local origin.
    monkeypatch.setattr(repo_cloner, "_build_authenticated_url", lambda repo, config: repo.raw)

    url = origin.as_uri()
    local = repo_cloner.clone_repo(url, branch="main", depth=1)
    assert (local / "file.txt").read_text(encoding="utf-8").strip() == "main-content"

    (origin / "file.txt").write_text("main-updated\n", encoding="utf-8")
    _git("add", "-A", cwd=origin)
    _git("commit", "-qm", "update", cwd=origin)

    again = repo_cloner.clone_repo(url, depth=1)
    assert (again / "file.txt").read_text(encoding="utf-8").strip() == "main-updated", (
        "a re-scan reported on a stale commit"
    )
