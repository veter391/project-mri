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
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from mri.db import fusion_repository as repo
from mri.ingest import claude_code
from mri.models.fusion import Session, SessionEvent, SessionFileTouch

logger = logging.getLogger(__name__)

__all__ = ["ConcurrentIngestError", "IngestResult", "ingest_log", "ingest_workspace"]


class ConcurrentIngestError(RuntimeError):
    """Two ingests raced for one session.

    The UNIQUE (session_id, seq) constraint makes this loud rather than letting
    turns duplicate, which would inflate the session's influence over the code.
    Callers must serialise ingest per session; this exists so that requirement
    fails visibly instead of surfacing as a bare sqlite3 error.
    """


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
    #: Sessions whose log had been rewritten rather than appended to, and were
    #: therefore re-read from the start. Should be rare; a steady stream of them
    #: means an assumption about the log format is wrong.
    rewritten: int = 0

    def __add__(self, other: IngestResult) -> IngestResult:
        return IngestResult(
            sessions=self.sessions + other.sessions,
            events=self.events + other.events,
            touches=self.touches + other.touches,
            unchanged=self.unchanged + other.unchanged,
            unreadable_lines=self.unreadable_lines + other.unreadable_lines,
            rewritten=self.rewritten + other.rewritten,
        )


async def _highest_stored_seq(conn: aiosqlite.Connection, session_id: int) -> int:
    cursor = await conn.execute(
        "SELECT coalesce(max(seq), 0) FROM session_events WHERE session_id = ?", (session_id,)
    )
    row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def _stored_fingerprint(
    conn: aiosqlite.Connection, session_id: int, seq: int
) -> str | None:
    cursor = await conn.execute(
        "SELECT content_hash FROM session_events WHERE session_id = ? AND seq = ?",
        (session_id, seq),
    )
    row = await cursor.fetchone()
    return str(row[0]) if row else None


async def _forget_session(conn: aiosqlite.Connection, session_id: int) -> None:
    """Drop everything derived from a session's log, keeping the session row."""
    await conn.execute("DELETE FROM session_file_touches WHERE session_id = ?", (session_id,))
    await conn.execute("DELETE FROM session_events WHERE session_id = ?", (session_id,))
    await conn.commit()


async def _event_ids_by_seq(
    conn: aiosqlite.Connection, session_id: int, *, after_seq: int
) -> dict[int, int]:
    """Map seq -> event id for the turns just inserted (seq past the watermark).

    Only new touches need linking, and they sit past the watermark. Scoping to
    `seq > after_seq` makes an incremental poll of a long-lived session O(new
    turns), not O(whole session) — measured ~1000x cheaper on an 88k-turn log.
    """
    cursor = await conn.execute(
        "SELECT seq, id FROM session_events WHERE session_id = ? AND seq > ?",
        (session_id, after_seq),
    )
    return {int(seq): int(event_id) for seq, event_id in await cursor.fetchall()}


async def _watermark(
    conn: aiosqlite.Connection, session_id: int, parsed: claude_code.ParsedSession
) -> tuple[int, bool]:
    """How much of this log is already stored, and whether it was rewritten.

    Appending past the highest stored turn is correct only while the log is
    append-only. A log rewritten in place — crash recovery, a checkpoint
    re-emit, an editor — puts different content where we already consider the
    work done, and the edits it now describes are lost while the run reports
    that nothing changed. That was reproduced before this check existed.

    So the turn at the watermark is compared with what is stored there, by a
    fingerprint that covers tool calls and not only prose: two turns can both
    carry no text while writing different files. If they differ, the stored copy
    describes a log that no longer exists and is discarded rather than patched —
    a partial correction would leave the two halves describing different files.
    """
    watermark = await _highest_stored_seq(conn, session_id)
    if watermark == 0:
        return 0, False

    current = next((t for t in parsed.turns if t.seq == watermark), None)
    stored = await _stored_fingerprint(conn, session_id, watermark)
    if current is not None and current.content_hash == stored:
        return watermark, False

    logger.info(
        "session %s: log was rewritten rather than appended to; re-reading it in full",
        session_id,
    )
    await _forget_session(conn, session_id)
    return 0, True


async def ingest_log(
    conn: aiosqlite.Connection,
    log: Path,
    *,
    repo_root: Path,
    project_id: int | None = None,
    store_content: bool = False,
) -> IngestResult:
    """Ingest one session log.

    `project_id` links the session — and every touch derived from it — to the
    scanned project, so authorship evidence for a same-named file in another repo
    cannot blend in. None is allowed (evidence for no project), but a real scan
    should pass it.

    Safe to call again on the same file: an unchanged log is a no-op, a grown
    one costs only its new turns, and a rewritten one is re-read in full. Not
    safe to call concurrently for the same session — see `ConcurrentIngestError`.
    """
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
            project_id=project_id,
            workspace_path=parsed.workspace_path,
            started_at=parsed.started_at,
            ended_at=parsed.ended_at,
            content_stored=store_content,
        ),
    )
    assert session.id is not None  # upsert_session raises rather than returning a session without one

    session_id = session.id
    watermark, rewritten = await _watermark(conn, session_id, parsed)
    new_turns = [t for t in parsed.turns if t.seq > watermark]
    if not new_turns:
        return IngestResult(
            sessions=1,
            unchanged=1,
            unreadable_lines=parsed.unreadable_lines,
            rewritten=int(rewritten),
        )

    # Generators rather than lists: the models are built a chunk at a time
    # instead of all at once. A real 88,824-turn session peaked at 132.6 MB
    # doing the latter, five times what parsing it cost.
    def events() -> Iterator[SessionEvent]:
        for turn in new_turns:
            yield SessionEvent(
                session_id=session_id,
                seq=turn.seq,
                role=turn.role,  # type: ignore[arg-type]
                kind=turn.kind,
                content=turn.content,
                content_hash=turn.content_hash,
                occurred_at=turn.occurred_at,
            )

    try:
        events_written = await repo.insert_session_events(conn, events())
        # Map each stored turn's seq to its row id so a touch can point at the
        # turn that produced it — the link the schema always promised and never
        # populated until now.
        seq_to_event_id = await _event_ids_by_seq(conn, session_id, after_seq=watermark)

        def touches() -> Iterator[SessionFileTouch]:
            for touch in parsed.touches:
                if touch.seq <= watermark:
                    continue
                yield SessionFileTouch(
                    session_id=session_id,
                    project_id=project_id,
                    event_id=seq_to_event_id.get(touch.seq),
                    file_path=touch.file_path,
                    touch_kind=touch.touch_kind,  # type: ignore[arg-type]
                    confidence=touch.confidence,
                    occurred_at=touch.occurred_at,
                )

        touches_written = await repo.insert_session_file_touches(conn, touches())
    except sqlite3.IntegrityError as exc:
        # UNIQUE (session_id, seq) fired: another ingest wrote these turns
        # between our watermark read and our insert. The constraint did its job
        # — nothing was duplicated — and this makes the cause legible.
        raise ConcurrentIngestError(
            f"another ingest is running for session {parsed.external_id}; "
            "ingest must be serialised per session"
        ) from exc

    return IngestResult(
        sessions=1,
        events=events_written,
        touches=touches_written,
        unreadable_lines=parsed.unreadable_lines,
        rewritten=int(rewritten),
    )


async def ingest_workspace(
    conn: aiosqlite.Connection,
    workspace: Path,
    *,
    project_id: int | None = None,
    store_content: bool = False,
    home: Path | None = None,
) -> IngestResult:
    """Ingest every session recorded against this workspace.

    `project_id` links every ingested session to the scanned project so its
    authorship evidence stays scoped to that project. Returns an empty result
    when no logs are found, which is the common case: most repositories were
    never touched by an agent, and that is a real answer rather than a failure.
    """
    root = await asyncio.to_thread(workspace.resolve)
    # Discovery opens every candidate log to read its recorded cwd — blocking,
    # and proportional to how many sessions the machine has recorded.
    logs = await asyncio.to_thread(claude_code.logs_for_workspace, root, home=home)
    total = IngestResult()
    for log in logs:
        total += await ingest_log(
            conn, log, repo_root=root, project_id=project_id, store_content=store_content
        )
    logger.info(
        "ingested %d session(s) from %s: %d event(s), %d touch(es), %d unchanged",
        total.sessions, root, total.events, total.touches, total.unchanged,
    )
    return total
