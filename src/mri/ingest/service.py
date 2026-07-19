"""Persist parsed sessions into the fusion tables.

Ingest is expected to run repeatedly against logs that are still being written
to, so it appends rather than replaces: the highest turn already stored for a
session is the watermark, and only turns past it are written. Re-running over an
unchanged log is a no-op, and re-running over a grown one costs only the new
turns.

File touches follow the same watermark. They are derived from turns, so tying
both to one number is what keeps a re-ingest from double-counting a session's
influence — which would quietly inflate every authorship number downstream.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from mri.db import fusion_repository as repo
from mri.ingest import claude_code
from mri.models.fusion import Session, SessionEvent, SessionFileTouch

logger = logging.getLogger(__name__)

__all__ = ["IngestResult", "ingest_log", "ingest_workspace"]


@dataclass(slots=True)
class IngestResult:
    """What an ingest run actually did — reported, not summarised away."""

    sessions: int = 0
    events: int = 0
    touches: int = 0
    #: Sessions seen whose turns were all already stored.
    unchanged: int = 0
    #: Lines that were not valid JSON, summed across logs.
    unreadable_lines: int = 0

    def __add__(self, other: IngestResult) -> IngestResult:
        return IngestResult(
            sessions=self.sessions + other.sessions,
            events=self.events + other.events,
            touches=self.touches + other.touches,
            unchanged=self.unchanged + other.unchanged,
            unreadable_lines=self.unreadable_lines + other.unreadable_lines,
        )


async def _highest_stored_seq(conn: aiosqlite.Connection, session_id: int) -> int:
    cursor = await conn.execute(
        "SELECT coalesce(max(seq), 0) FROM session_events WHERE session_id = ?", (session_id,)
    )
    row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def ingest_log(
    conn: aiosqlite.Connection,
    log: Path,
    *,
    repo_root: Path,
    store_content: bool = False,
) -> IngestResult:
    """Ingest one session log. Safe to call again on the same file."""
    # Reading and parsing a log is blocking filesystem work — real logs reach
    # tens of megabytes and take about a second. The API serves requests on this
    # loop, so it happens off it.
    parsed = await asyncio.to_thread(
        claude_code.parse_log, log, repo_root=repo_root, store_content=store_content
    )
    if parsed is None:
        logger.debug("no session records in %s", log.name)
        return IngestResult()

    session = await repo.upsert_session(
        conn,
        Session(
            source=claude_code.SOURCE,
            external_id=parsed.external_id,
            workspace_path=parsed.workspace_path,
            started_at=parsed.started_at,
            ended_at=parsed.ended_at,
            content_stored=store_content,
        ),
    )
    assert session.id is not None  # upsert_session raises rather than returning a session without one

    watermark = await _highest_stored_seq(conn, session.id)
    new_turns = [t for t in parsed.turns if t.seq > watermark]
    if not new_turns:
        return IngestResult(sessions=1, unchanged=1, unreadable_lines=parsed.unreadable_lines)

    events_written = await repo.insert_session_events(
        conn,
        [
            SessionEvent(
                session_id=session.id,
                seq=turn.seq,
                role=turn.role,  # type: ignore[arg-type]
                kind=turn.kind,
                content=turn.content,
                content_hash=turn.content_hash,
                occurred_at=turn.occurred_at,
            )
            for turn in new_turns
        ],
    )

    touches_written = await repo.insert_session_file_touches(
        conn,
        [
            SessionFileTouch(
                session_id=session.id,
                file_path=touch.file_path,
                touch_kind=touch.touch_kind,  # type: ignore[arg-type]
                confidence=touch.confidence,
                occurred_at=touch.occurred_at,
            )
            for touch in parsed.touches
            if touch.seq > watermark
        ],
    )

    return IngestResult(
        sessions=1,
        events=events_written,
        touches=touches_written,
        unreadable_lines=parsed.unreadable_lines,
    )


async def ingest_workspace(
    conn: aiosqlite.Connection,
    workspace: Path,
    *,
    store_content: bool = False,
    home: Path | None = None,
) -> IngestResult:
    """Ingest every session recorded against this workspace.

    Returns an empty result when no logs are found, which is the common case:
    most repositories were never touched by an agent, and that is a real answer
    rather than a failure.
    """
    root = await asyncio.to_thread(workspace.resolve)
    # Discovery opens every candidate log to read its recorded cwd — blocking,
    # and proportional to how many sessions the machine has recorded.
    logs = await asyncio.to_thread(claude_code.logs_for_workspace, root, home=home)
    total = IngestResult()
    for log in logs:
        total += await ingest_log(conn, log, repo_root=root, store_content=store_content)
    logger.info(
        "ingested %d session(s) from %s: %d event(s), %d touch(es), %d unchanged",
        total.sessions, root, total.events, total.touches, total.unchanged,
    )
    return total
