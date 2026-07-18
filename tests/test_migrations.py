"""Schema migration tests.

The database lives on each user's own disk, so a broken migration is
unrecoverable for them — these tests pin the guarantees the runner makes.
"""
from __future__ import annotations

import sqlite3
import threading
from importlib.resources import files as pkg_files
from pathlib import Path

import pytest

from mri.db import migrator
from mri.db.migrator import (
    Migration,
    MigrationError,
    applied_migrations,
    migrate,
    pending_migrations,
)

BASELINE = "0001_initial_schema.sql"
CORE_TABLES = {"scans", "projects", "findings", "analyzer_runs", "users"}


def _baseline_sql() -> str:
    """The baseline DDL, read from the installed package rather than a path
    relative to the working directory."""
    return (
        pkg_files("mri").joinpath("db", "migrations", BASELINE).read_text(encoding="utf-8")
    )


def _tables(db: Path) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "mri.db"


def test_fresh_database_gets_the_baseline(db: Path):
    assert migrate(db) == [BASELINE]
    assert CORE_TABLES <= _tables(db)
    assert applied_migrations(db) == {BASELINE}


def test_migrate_is_idempotent(db: Path):
    migrate(db)
    assert migrate(db) == []
    assert pending_migrations(db) == []


def test_applied_migrations_are_timestamped(db: Path):
    migrate(db)
    conn = sqlite3.connect(db)
    try:
        name, applied_at = conn.execute(
            "SELECT name, applied_at FROM schema_migrations"
        ).fetchone()
    finally:
        conn.close()
    assert name == BASELINE
    assert applied_at.endswith("+00:00")


def test_pre_migrations_database_is_stamped_not_rebuilt(db: Path):
    """A v0.3.x database already has the tables and real user data. The baseline
    must be recorded, never re-run, and the data must survive untouched."""
    conn = sqlite3.connect(db)
    try:
        # v0.3.x created its tables straight from this DDL and had no tracking
        # table at all.
        conn.executescript(_baseline_sql())
        conn.execute("INSERT INTO projects (name, path) VALUES ('legacy', '/tmp/legacy')")
        conn.commit()
    finally:
        conn.close()

    assert migrate(db) == []  # stamped, nothing executed
    assert applied_migrations(db) == {BASELINE}

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT name FROM projects").fetchone()[0] == "legacy"
    finally:
        conn.close()


def test_failed_migration_leaves_no_trace(db: Path, monkeypatch: pytest.MonkeyPatch):
    """Atomicity. A migration that fails partway must roll back completely and
    must not be recorded, so the next run retries it."""
    real_discover = migrator._discover

    def with_broken() -> list[Migration]:
        return real_discover() + [
            Migration("0002_broken.sql", "CREATE TABLE half_applied(x);\nCREATE TABLE oops( ;\n")
        ]

    monkeypatch.setattr(migrator, "_discover", with_broken)

    with pytest.raises(MigrationError, match="0002_broken.sql"):
        migrate(db)

    assert "half_applied" not in _tables(db)
    assert applied_migrations(db) == {BASELINE}


def test_concurrent_migrations_apply_exactly_once(db: Path):
    """CLI and server can start at the same moment. `BEGIN IMMEDIATE` plus a
    re-read of the applied set inside the lock must make the loser a no-op
    rather than a double-apply or an error."""
    results: list[list[str]] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            results.append(migrate(db))
        except BaseException as exc:  # noqa: BLE001 - recorded and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"concurrent migration errored: {errors}"
    applied = [name for r in results for name in r]
    assert applied == [BASELINE], f"baseline applied {len(applied)} times, expected once"
    assert CORE_TABLES <= _tables(db)


def test_statement_splitter_matches_the_baseline_objects():
    """The runner cannot use executescript (it commits and would break
    atomicity), so it splits statements itself. Guard that the split stays
    faithful to the migration's contents."""
    statements = list(migrator._statements(_baseline_sql()))
    # Leading comments attach to the statement that follows them, which SQLite
    # accepts — so assert on content, not on the first characters.
    assert all("CREATE" in s.upper() for s in statements), "a comment-only chunk was emitted"
    assert sum("CREATE TABLE" in s.upper() for s in statements) == 9
    assert sum("CREATE INDEX" in s.upper() for s in statements) == 13
    assert len(statements) == 22


def test_a_partial_database_is_not_mistaken_for_a_v030_one(db: Path):
    """`mri restore` accepts a user-supplied .tar.gz and moves the database
    inside it into place. A file carrying only the three marker tables must not
    be stamped as pre-migrations — that would skip the baseline and leave the
    install without users, findings and the rest, failing at runtime instead of
    at setup."""
    conn = sqlite3.connect(db)
    try:
        conn.executescript(
            "CREATE TABLE scans (id INTEGER PRIMARY KEY);"
            "CREATE TABLE projects (id INTEGER PRIMARY KEY);"
            "CREATE TABLE analyzer_runs (id INTEGER PRIMARY KEY);"
        )
        conn.commit()
    finally:
        conn.close()

    # Refused with something the user can act on, rather than stamped into a
    # half-schema install or crashing with a bare SQL error.
    with pytest.raises(MigrationError, match="does not match any known schema"):
        migrate(db)
    assert applied_migrations(db) == set(), "a partial database must not be recorded"


def test_a_genuine_v030_database_is_still_stamped(db: Path):
    """The real upgrade path must keep working: a complete v0.3.x database is
    recorded, not rebuilt, and its data survives."""
    conn = sqlite3.connect(db)
    try:
        conn.executescript(_baseline_sql())
        conn.execute("INSERT INTO projects (name, path) VALUES ('legacy', '/tmp/legacy')")
        conn.commit()
    finally:
        conn.close()

    assert migrate(db) == []
    assert applied_migrations(db) == {BASELINE}
