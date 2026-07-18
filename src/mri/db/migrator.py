"""Schema migrations for the local SQLite database.

This is deliberately small and dependency-free. The database lives on each
user's own disk, so an upgrade happens whenever they run a newer version — there
is no server-side migration window and no operator to run a deploy step.

Design (see docs/adr/ADR-005-schema-migrations.md):
  * Migrations are plain `.sql` files in `migrations/`, applied in filename order.
  * Applied migrations are recorded by name in `schema_migrations`, which is the
    single source of truth. Name-based tracking (rather than a single
    `user_version` integer) keeps an audit trail and leaves room for the planned
    analyzer plugins to own their own migration sets.
  * Each migration and its tracking row commit together, so a failure leaves the
    migration pending rather than half-applied and forgotten.

Three SQLite behaviours this code depends on, each verified rather than assumed:
  * DDL is transactional — a failed CREATE TABLE rolls back cleanly.
  * `PRAGMA foreign_keys` is silently IGNORED inside a transaction, so it is only
    ever set on the connection before any BEGIN.
  * `BEGIN IMMEDIATE` takes the write lock up front. Two processes starting at
    once (CLI and server) therefore serialise, and the loser re-reads the applied
    set inside its own lock and finds nothing left to do.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.resources import files as _pkg_files
from pathlib import Path

__all__ = ["MigrationError", "applied_migrations", "migrate", "pending_migrations"]

# Tables that a pre-migrations (v0.3.x) database is guaranteed to have. Used to
# tell "brand new database" apart from "existing database that predates this
# module", which must be stamped rather than re-created.
_BASELINE_MARKER_TABLES = ("scans", "projects", "analyzer_runs")
_BASELINE_MIGRATION = "0001_initial_schema.sql"

_LOCK_TIMEOUT_MS = 15_000


class MigrationError(RuntimeError):
    """A migration failed to apply. The database is unchanged."""


@dataclass(frozen=True)
class Migration:
    name: str
    sql: str


def _discover() -> list[Migration]:
    """Load migrations from the package, ordered by filename."""
    root = _pkg_files("mri").joinpath("db", "migrations")
    names = sorted(p.name for p in root.iterdir() if p.name.endswith(".sql"))
    return [Migration(name, root.joinpath(name).read_text(encoding="utf-8")) for name in names]


def _statements(sql: str) -> Iterator[str]:
    """Split a migration into individual statements.

    `Connection.executescript` cannot be used here: it issues an implicit COMMIT
    before running, which would silently end the transaction this runner opened
    and make the atomicity guarantee a fiction. Verified, not assumed — a DDL
    statement run through executescript survived an explicit ROLLBACK.

    `sqlite3.complete_statement` is the stdlib's own answer for finding
    statement boundaries, so semicolons inside string literals and trigger
    bodies do not split incorrectly.
    """
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if statement:
                yield statement
    trailing = buffer.strip()
    if trailing:
        yield trailing


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    # Must be set outside any transaction to have any effect.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {_LOCK_TIMEOUT_MS}")
    return conn


def _ensure_tracking_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name        TEXT PRIMARY KEY,
            applied_at  TEXT NOT NULL
        )
        """
    )


def _applied(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM schema_migrations").fetchall()
    return {r[0] for r in rows}


def _looks_like_pre_migrations_db(conn: sqlite3.Connection) -> bool:
    """True if the database predates this module: it has the v0.3.x tables but
    no record of ever applying a migration."""
    existing = {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    return set(_BASELINE_MARKER_TABLES) <= existing


def applied_migrations(db_path: Path) -> set[str]:
    """Names of migrations already applied to this database."""
    conn = _connect(db_path)
    try:
        _ensure_tracking_table(conn)
        return _applied(conn)
    finally:
        conn.close()


def pending_migrations(db_path: Path) -> list[str]:
    """Names of migrations not yet applied, in the order they would run."""
    done = applied_migrations(db_path)
    return [m.name for m in _discover() if m.name not in done]


def migrate(db_path: Path) -> list[str]:
    """Bring the database up to date. Returns the migrations applied, in order.

    Safe to call concurrently and safe to call when already up to date.
    """
    migrations = _discover()
    if not migrations:  # pragma: no cover - the package always ships migrations
        return []

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        _ensure_tracking_table(conn)
        if not set(m.name for m in migrations) - _applied(conn):
            return []  # fast path: nothing to do, no write lock taken

        applied_now: list[str] = []
        for migration in migrations:
            # Take the write lock BEFORE deciding, so a racing process cannot
            # apply the same migration between our check and our write.
            conn.execute("BEGIN IMMEDIATE")
            try:
                if migration.name in _applied(conn):
                    conn.execute("COMMIT")
                    continue
                if migration.name == _BASELINE_MIGRATION and _looks_like_pre_migrations_db(conn):
                    # The objects already exist from v0.3.x — record, don't re-run.
                    _record(conn, migration.name)
                    conn.execute("COMMIT")
                    continue

                for statement in _statements(migration.sql):
                    conn.execute(statement)
                violations = conn.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise MigrationError(
                        f"{migration.name} left {len(violations)} foreign-key violation(s)"
                    )
                _record(conn, migration.name)
                conn.execute("COMMIT")
            except Exception as exc:
                conn.execute("ROLLBACK")
                if isinstance(exc, MigrationError):
                    raise
                raise MigrationError(f"{migration.name} failed: {exc}") from exc
            applied_now.append(migration.name)
        return applied_now
    finally:
        conn.close()


def _record(conn: sqlite3.Connection, name: str) -> None:
    conn.execute(
        "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
        (name, datetime.now(timezone.utc).replace(microsecond=0).isoformat()),
    )
