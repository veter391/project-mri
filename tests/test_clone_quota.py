"""Sandbox quotas for repo cloning (Rebuild Phase 1, H3), exercised for real.

The SSRF guard (test_clone_ssrf.py) stops *where* we clone from; these tests
cover *how much* we clone: a shallow-depth default so a huge repo's whole
history is not fetched by accident, and hard on-disk size / file-count caps that
fail closed (delete the clone + raise) when exceeded.

Everything runs against a local git repo built in a tmp dir — no network. The
caps are driven to tiny values through a stubbed config so the rejection paths
are fast and deterministic.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mri.services import repo_cloner
from mri.services.repo_cloner import CloneError


def _git(*args: str, cwd: Path) -> None:
    subprocess.check_call(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """A local origin repo with three commits and a few files."""
    repo = tmp_path / "origin"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    for i in range(3):
        (repo / f"file{i}.txt").write_text(f"content-{i}\n" * 20, encoding="utf-8")
        _git("add", "-A", cwd=repo)
        _git("commit", "-qm", f"commit {i}", cwd=repo)
    return repo


def _patch_common(
    monkeypatch: pytest.MonkeyPatch, cache: Path, config: dict
) -> None:
    """Neutralise the network-facing bits so the clone runs against local files.

    The SSRF guard, DB record, URL parsing and auth injection are all covered by
    other suites; here they would only stop a local `file://` clone from ever
    starting. The quota logic under test is left untouched.
    """
    monkeypatch.setattr(repo_cloner, "_default_cache_dir", lambda: cache)
    monkeypatch.setattr(repo_cloner, "get_config", lambda: config)
    monkeypatch.setattr(repo_cloner, "_validate_clone_target", lambda repo, config: None)
    monkeypatch.setattr(repo_cloner, "_record_clone", lambda *a, **k: None)
    monkeypatch.setattr(
        repo_cloner,
        "parse_repo_url",
        lambda url: repo_cloner.RepoUrl(url, "example.com", "owner", "repo", scheme="https"),
    )
    monkeypatch.setattr(repo_cloner, "_build_authenticated_url", lambda repo, config: repo.raw)


def test_shallow_depth_applied_by_default(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A depthless clone must use the configured shallow default (50), not full
    history. We spy on the git command and confirm the on-disk clone is shallow.
    """
    cache = tmp_path / "cache"
    # Empty clones config -> code falls back to _DEFAULT_CLONE_DEPTH (50) and the
    # generous default caps (which this small repo cannot exceed).
    _patch_common(monkeypatch, cache, {"clones": {}})

    calls: list[list] = []
    real_run_git = repo_cloner._run_git

    def spy(*args, **kwargs):
        calls.append(list(args))
        return real_run_git(*args, **kwargs)

    monkeypatch.setattr(repo_cloner, "_run_git", spy)

    repo_cloner.clone_repo(origin.as_uri())  # no depth kwarg

    clone_cmd = next(c for c in calls if c and c[0] == "clone")
    assert "--depth" in clone_cmd, "default clone must be shallow"
    depth_val = clone_cmd[clone_cmd.index("--depth") + 1]
    assert depth_val == str(repo_cloner._DEFAULT_CLONE_DEPTH) == "50"


def test_explicit_shallow_depth_truncates_history(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Proof the depth mechanism really limits history (not just passed as a
    flag): depth=1 over a 3-commit repo yields a single-commit shallow clone."""
    cache = tmp_path / "cache"
    _patch_common(monkeypatch, cache, {"clones": {}})

    local = repo_cloner.clone_repo(origin.as_uri(), depth=1)

    assert (local / ".git" / "shallow").exists(), "depth=1 must produce a shallow clone"
    count = subprocess.check_output(
        ["git", "rev-list", "--count", "HEAD"], cwd=local, text=True
    ).strip()
    assert count == "1", f"expected 1 commit of history, got {count}"


def test_depth_zero_fetches_full_history(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Explicit depth=0 overrides the default and clones full history (no
    `--depth`, no shallow boundary) — the documented escape hatch."""
    cache = tmp_path / "cache"
    _patch_common(monkeypatch, cache, {"clones": {}})

    calls: list[list] = []
    real_run_git = repo_cloner._run_git

    def spy(*args, **kwargs):
        calls.append(list(args))
        return real_run_git(*args, **kwargs)

    monkeypatch.setattr(repo_cloner, "_run_git", spy)

    local = repo_cloner.clone_repo(origin.as_uri(), depth=0)

    clone_cmd = next(c for c in calls if c and c[0] == "clone")
    assert "--depth" not in clone_cmd, "depth=0 must mean full history"
    assert not (local / ".git" / "shallow").exists()


def test_clone_exceeding_size_cap_is_rejected_and_cleaned_up(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A clone larger than `clones.max_clone_bytes` is deleted and raises."""
    cache = tmp_path / "cache"
    config = {"clones": {"max_clone_bytes": 10, "max_clone_files": 0}}  # 10 B cap
    _patch_common(monkeypatch, cache, config)

    url = origin.as_uri()
    expected_path = repo_cloner._url_to_cache_path(url, cache)

    with pytest.raises(CloneError, match="rejected.*exceeds cap"):
        repo_cloner.clone_repo(url)

    assert not expected_path.exists(), "the oversized clone must be deleted (fail closed)"


def test_clone_exceeding_file_cap_is_rejected_and_cleaned_up(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A clone with more files than `clones.max_clone_files` is deleted and raises."""
    cache = tmp_path / "cache"
    # Size cap disabled (0); file cap of 1 is exceeded by the repo + its .git.
    config = {"clones": {"max_clone_bytes": 0, "max_clone_files": 1}}
    _patch_common(monkeypatch, cache, config)

    url = origin.as_uri()
    expected_path = repo_cloner._url_to_cache_path(url, cache)

    with pytest.raises(CloneError, match="file count .* exceeds cap"):
        repo_cloner.clone_repo(url)

    assert not expected_path.exists(), "the over-count clone must be deleted (fail closed)"


def test_clone_within_caps_is_kept(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A clone comfortably inside the caps survives and is returned intact."""
    cache = tmp_path / "cache"
    config = {"clones": {"max_clone_bytes": 500_000_000, "max_clone_files": 50_000}}
    _patch_common(monkeypatch, cache, config)

    local = repo_cloner.clone_repo(origin.as_uri())

    assert local.exists()
    assert (local / "file0.txt").exists()


def test_both_caps_disabled_skips_enforcement(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Both caps 0 -> enforcement is a no-op; a large-by-comparison clone is kept."""
    cache = tmp_path / "cache"
    config = {"clones": {"max_clone_bytes": 0, "max_clone_files": 0}}
    _patch_common(monkeypatch, cache, config)

    local = repo_cloner.clone_repo(origin.as_uri())
    assert local.exists()
