"""Tests for v0.3.0 watch mode + CLI commands."""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from mri.cli import cli
from mri.services.watcher import RepoWatcher


class TestWatcher:
    def test_debounce_merges_rapid_changes(self, tmp_path: Path):
        """3 file changes within 0.2s should produce 1 rescan (with 0.5s debounce)."""
        (tmp_path / "test.py").write_text("x = 1")
        calls = []

        def on_change():
            calls.append(time.time())

        watcher = RepoWatcher(str(tmp_path), on_change=on_change, debounce_seconds=0.5)
        thread = threading.Thread(target=watcher.start, daemon=True)
        thread.start()
        time.sleep(0.3)

        # Rapid changes
        for i in range(5):
            (tmp_path / "test.py").write_text(f"x = {i}")
            time.sleep(0.05)

        # Wait for debounce to fire
        time.sleep(1.0)
        watcher.stop()
        thread.join(timeout=2)

        # Should be 1-2 rescans (rapid changes get merged)
        assert 1 <= len(calls) <= 2, f"expected 1-2 rescans, got {len(calls)}"

    def test_ignores_matched_globs(self, tmp_path: Path):
        """Files matching ignore_globs should not trigger rescans."""
        (tmp_path / "test.py").write_text("x = 1")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lib.js").write_text("// js")

        calls = []

        def on_change():
            calls.append(time.time())

        watcher = RepoWatcher(
            str(tmp_path),
            on_change=on_change,
            debounce_seconds=0.2,
            ignore_globs=["**/node_modules/**"],
        )
        thread = threading.Thread(target=watcher.start, daemon=True)
        thread.start()
        time.sleep(0.3)

        # Modify ignored file — should NOT trigger
        (tmp_path / "node_modules" / "lib.js").write_text("// js2")
        time.sleep(0.5)
        # Modify real file — SHOULD trigger
        (tmp_path / "test.py").write_text("x = 2")
        time.sleep(0.5)

        watcher.stop()
        thread.join(timeout=2)

        # Should have exactly 1 rescan (only the test.py change)
        assert len(calls) == 1, f"expected 1 rescan, got {len(calls)}"

    def test_invalid_path_raises(self, tmp_path: Path):
        with pytest.raises(ValueError):
            RepoWatcher(str(tmp_path / "nonexistent"), on_change=lambda: None)


class TestCLIInit:
    def test_init_creates_user(self, tmp_path: Path, monkeypatch):
        """mri init --yes creates a user and config."""
        db_path = tmp_path / "test.db"
        cfg_path = tmp_path / "config.yml"
        monkeypatch.setenv("MRI_DB", str(db_path))
        from mri.db import repository
        repository._DEFAULT_PATH = None

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["init", "--username", "admin", "--password", "test12345678", "--yes",
             "--config-path", str(cfg_path)],
        )
        assert result.exit_code == 0, result.output
        assert "user 'admin' created" in result.output
        assert cfg_path.exists()
        assert db_path.exists()

    def test_init_rejects_duplicate_user(self, tmp_path: Path, monkeypatch):
        db_path = tmp_path / "test.db"
        cfg_path = tmp_path / "config.yml"
        monkeypatch.setenv("MRI_DB", str(db_path))
        from mri.db import repository
        repository._DEFAULT_PATH = None

        runner = CliRunner()
        # First init
        r1 = runner.invoke(
            cli,
            ["init", "--username", "admin", "--password", "test12345678", "--yes",
             "--config-path", str(cfg_path)],
        )
        assert r1.exit_code == 0
        # Second init with same user (without confirmation)
        r2 = runner.invoke(
            cli,
            ["init", "--username", "admin", "--password", "another123456", "--yes",
             "--config-path", str(cfg_path)],
            input="n\n",  # decline the "create another?" prompt
        )
        assert r2.exit_code == 0


class TestCLIList:
    def test_list_empty(self, tmp_path: Path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("MRI_DB", str(db_path))
        from mri.db import repository
        repository._DEFAULT_PATH = None

        runner = CliRunner()
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "no scans" in result.output.lower() or "(no scans yet)" in result.output


class TestCLIBackupRestore:
    def test_backup_creates_file(self, tmp_path: Path, monkeypatch):
        db_path = tmp_path / "test.db"
        backup_path = tmp_path / "backup.tar.gz"
        cfg_path = tmp_path / "config.yml"
        monkeypatch.setenv("MRI_DB", str(db_path))
        from mri.db import repository
        repository._DEFAULT_PATH = None
        monkeypatch.setattr(
            "pathlib.Path.home",
            lambda: tmp_path,  # so config goes to tmp_path/.config/project-mri/
        )
        # Easier: just create the user first so DB exists
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["init", "--username", "admin", "--password", "test12345678", "--yes",
             "--config-path", str(cfg_path)],
        )
        assert result.exit_code == 0

        # Now backup
        result = runner.invoke(cli, ["backup", str(backup_path)])
        assert result.exit_code == 0
        assert backup_path.exists()
        assert backup_path.stat().st_size > 0
