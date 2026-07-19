"""SQLite repository — async wrappers around aiosqlite.

We use one connection per request via FastAPI dependency injection.
Schema is applied automatically on connect if missing.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from mri.db.migrator import migrate

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

# Applied to every connection, sync or async, so the five short-lived sync
# connections scattered around the codebase stop opening with defaults.
#
# `synchronous = NORMAL` is the documented pairing for WAL: the database cannot
# be corrupted, and the only exposure is that a transaction committed in the
# instant before a power cut may roll back. For a local tool storing scan
# results that is the right trade — measured at 1.16 ms/commit against
# 0.02 ms/commit, and a scan commits ~30 times.
#
# `journal_mode` is a property of the file rather than the connection, so
# setting it repeatedly is harmless; `busy_timeout` is per-connection and its
# absence is what turns any contention into an immediate "database is locked".
_PRAGMAS = (
    "PRAGMA foreign_keys = ON",
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA busy_timeout = 5000",
)


def connect_sync(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a synchronous connection with the same settings as the async one.

    Several call sites run outside the event loop — the CLI, the auth helpers,
    the clone recorder, the webhook writer — and each used to open a bare
    connection with SQLite's defaults.
    """
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    for pragma in _PRAGMAS:
        conn.execute(pragma)
    return conn


def default_db_path() -> Path:
    """Return the default SQLite cache path. Override with MRI_DB env var."""
    import os

    env = os.environ.get("MRI_DB")
    if env:
        return Path(env)
    # ~/.cache/project-mri/mri.db on Unix, %LOCALAPPDATA%/project-mri/mri.db on Win
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    path = base / "project-mri" / "mri.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def get_connection(db_path: Path | None = None) -> AsyncIterator[aiosqlite.Connection]:
    """Yield an aiosqlite connection with schema applied.

    Uses WAL journal mode and a short busy_timeout so concurrent reads
    don't block writers. Schema is applied via aiosqlite's async API.
    """
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Bring the schema up to date before handing out a connection. Re-running
    # the full schema here used to be the mechanism, but `CREATE TABLE IF NOT
    # EXISTS` silently no-ops against an existing table, so schema changes would
    # never reach an already-installed user. The migrator is a no-op when the
    # database is current, and takes a write lock only when there is work to do.
    await asyncio.to_thread(migrate, path)
    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    for pragma in _PRAGMAS:
        await conn.execute(pragma)
    try:
        yield conn
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utcnow() -> str:
    """ISO-8601 UTC timestamp without microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_default(o: Any) -> Any:
    """Fallback encoder for non-JSON-native types."""
    if hasattr(o, "model_dump"):
        return o.model_dump()
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


async def upsert_project(conn: aiosqlite.Connection, path: str, name: str, default_branch: str) -> int:
    """Insert or update a project row, returning its id."""
    now = utcnow()
    await conn.execute(
        """
        INSERT INTO projects (path, name, default_branch, first_scanned, last_scanned)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            name = excluded.name,
            default_branch = excluded.default_branch,
            last_scanned = excluded.last_scanned
        """,
        (path, name, default_branch, now, now),
    )
    await conn.commit()
    cursor = await conn.execute("SELECT id FROM projects WHERE path = ?", (path,))
    row = await cursor.fetchone()
    if row is None:
        # Should never happen — we just inserted this row above
        raise RuntimeError(f"project row disappeared after upsert: {path}")
    return int(row[0])


async def create_scan(conn: aiosqlite.Connection, project_id: int, scan_uuid: str) -> int:
    cursor = await conn.execute(
        "INSERT INTO scans (project_id, scan_uuid, status) VALUES (?, ?, 'pending')",
        (project_id, scan_uuid),
    )
    await conn.commit()
    return int(cursor.lastrowid or 0)


async def update_scan_status(
    conn: aiosqlite.Connection,
    scan_id: int,
    status: str,
    *,
    error_message: str = "",
    report: dict | None = None,
    summary: dict | None = None,
    finished: bool = False,
) -> None:
    # Build the SQL safely. The f-string was flagged by bandit B608 because
    # it concatenates `finished_clause` into the query, but the value is
    # always a fixed literal (`", finished_at = ?"` or empty) — never user
    # input. We split into two explicit statements to keep bandit happy
    # AND make the intent obvious to readers.
    report_json = json.dumps(report, default=_json_default) if report is not None else None
    summary_json = json.dumps(summary, default=_json_default) if summary is not None else None
    if finished:
        await conn.execute(
            """
            UPDATE scans
            SET status = ?,
                error_message = ?,
                report_json = COALESCE(?, report_json),
                summary_json = COALESCE(?, summary_json),
                finished_at = ?
            WHERE id = ?
            """,
            (status, error_message, report_json, summary_json, utcnow(), scan_id),
        )
    else:
        await conn.execute(
            """
            UPDATE scans
            SET status = ?,
                error_message = ?,
                report_json = COALESCE(?, report_json),
                summary_json = COALESCE(?, summary_json)
            WHERE id = ?
            """,
            (status, error_message, report_json, summary_json, scan_id),
        )
    await conn.commit()


async def record_event(conn: aiosqlite.Connection, scan_id: int, kind: str, message: str) -> None:
    await conn.execute(
        "INSERT INTO scan_events (scan_id, kind, message) VALUES (?, ?, ?)",
        (scan_id, kind, message),
    )
    await conn.commit()


async def save_analyzer_run(
    conn: aiosqlite.Connection,
    scan_id: int,
    analyzer_name: str,
    *,
    status: str,
    findings: list[dict],
    signals: dict,
    score_value: float | None,
    score_label: str,
    started_at: str,
    finished_at: str,
    error_message: str = "",
) -> int:
    cursor = await conn.execute(
        """
        INSERT INTO analyzer_runs (
            scan_id, analyzer_name, status, started_at, finished_at,
            findings_json, signals_json, score_value, score_label, error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(scan_id, analyzer_name) DO UPDATE SET
            status = excluded.status,
            started_at = excluded.started_at,
            finished_at = excluded.finished_at,
            findings_json = excluded.findings_json,
            signals_json = excluded.signals_json,
            score_value = excluded.score_value,
            score_label = excluded.score_label,
            error_message = excluded.error_message
        """,
        (
            scan_id,
            analyzer_name,
            status,
            started_at,
            finished_at,
            json.dumps(findings, default=_json_default),
            json.dumps(signals, default=_json_default),
            score_value,
            score_label,
            error_message,
        ),
    )
    await conn.commit()
    return int(cursor.lastrowid or 0)


async def insert_findings(
    conn: aiosqlite.Connection, run_id: int, analyzer_name: str, findings: list[dict]
) -> None:
    if not findings:
        return
    rows = [
        (
            run_id,
            analyzer_name,
            f["severity"],
            f["category"],
            f["title"],
            f.get("description", ""),
            f.get("target_path", ""),
            f.get("target_symbol", ""),
            f.get("score"),
            json.dumps(f.get("data", {}), default=_json_default),
        )
        for f in findings
    ]
    await conn.executemany(
        """
        INSERT INTO findings (
            run_id, analyzer_name, severity, category, title, description,
            target_path, target_symbol, score, data_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    await conn.commit()


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def list_projects(conn: aiosqlite.Connection, limit: int = 100) -> list[dict]:
    cursor = await conn.execute(
        """
        SELECT p.*, COUNT(s.id) AS scan_count, MAX(s.started_at) AS last_scan
        FROM projects p
        LEFT JOIN scans s ON s.project_id = p.id
        GROUP BY p.id
        ORDER BY last_scan DESC NULLS LAST, p.last_scanned DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def list_scans(conn: aiosqlite.Connection, limit: int = 100) -> list[dict]:
    # Explicit columns, never `s.*`: report_json holds the entire report (~100 KB
    # per scan on a modest repo) and a list view has no use for it.
    cursor = await conn.execute(
        """
        SELECT s.scan_uuid, s.status, s.started_at, s.finished_at, s.error_message,
               s.summary_json, p.name AS project_name, p.path AS project_path
        FROM scans s
        JOIN projects p ON p.id = s.project_id
        ORDER BY s.started_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_scan_by_uuid(conn: aiosqlite.Connection, scan_uuid: str) -> dict | None:
    cursor = await conn.execute(
        """
        SELECT s.*, p.name AS project_name, p.path AS project_path
        FROM scans s
        JOIN projects p ON p.id = s.project_id
        WHERE s.scan_uuid = ?
        """,
        (scan_uuid,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_scan_runs(conn: aiosqlite.Connection, scan_id: int) -> list[dict]:
    cursor = await conn.execute(
        "SELECT * FROM analyzer_runs WHERE scan_id = ? ORDER BY id",
        (scan_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_findings(
    conn: aiosqlite.Connection, run_id: int, *, severity: str | None = None
) -> list[dict]:
    """Return findings for a run, ordered by score (highest first)."""
    if severity:
        cursor = await conn.execute(
            "SELECT * FROM findings WHERE run_id = ? AND severity = ? ORDER BY score DESC, id",
            (run_id, severity),
        )
    else:
        cursor = await conn.execute(
            "SELECT * FROM findings WHERE run_id = ? ORDER BY score DESC, id",
            (run_id,),
        )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
