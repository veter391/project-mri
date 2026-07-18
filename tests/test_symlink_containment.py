"""A scanned repository is untrusted input.

`mri scan <url>` clones and analyses whatever repository it is pointed at, and
git stores a symlink as an ordinary blob — so `notes.py -> /etc/passwd` is
something an attacker can simply commit. `os.walk` declines to descend into
symlinked *directories*, but a symlinked file still appears in the listing, and
both `stat` and `open` follow it.

These tests pin that neither the walk nor the shared cache will read outside the
project root.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from mri.analyzers.base import ScanContext
from mri.services.scanner import Scanner

SECRET = "SECRET-OUTSIDE-THE-REPO\n"


@pytest.fixture
def repo_with_symlink(tmp_path: Path) -> tuple[Path, Path]:
    """A project containing a symlink that points at a file outside it."""
    outside = tmp_path / "outside.txt"
    outside.write_text(SECRET, encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    (project / "real.py").write_text("x = 1\n", encoding="utf-8")
    link = project / "leak.py"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create symlinks on this platform: {exc}")
    return project, outside


def test_walk_does_not_list_symlinked_files(repo_with_symlink):
    project, _ = repo_with_symlink
    walked = {f["rel_path"] for f in Scanner._walk_files(project)}
    assert "real.py" in walked
    assert "leak.py" not in walked, "a symlinked file was walked and its target read"


def test_read_text_refuses_to_follow_a_symlink(repo_with_symlink):
    project, _ = repo_with_symlink
    ctx = ScanContext(project_path=project, branch="main", files=[], git=None)
    assert ctx.read_text("leak.py") is None
    assert ctx.read_text("real.py") == "x = 1\n"


def test_read_text_refuses_to_escape_the_project_root(tmp_path: Path):
    """Even without symlinks, a relative path must not climb out."""
    outside = tmp_path / "outside.txt"
    outside.write_text(SECRET, encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()

    ctx = ScanContext(project_path=project, branch="main", files=[], git=None)
    assert ctx.read_text("../outside.txt") is None


def test_secret_never_reaches_the_shared_cache(repo_with_symlink):
    project, _ = repo_with_symlink
    ctx = ScanContext(project_path=project, branch="main", files=[], git=None)
    for entry in Scanner._walk_files(project):
        ctx.read_text(entry["rel_path"])
    assert all(SECRET.strip() not in text for text in ctx._content.values()), (
        "content from outside the project was cached for the analyzers to consume"
    )
