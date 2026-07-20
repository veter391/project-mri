"""Async accessors for the fusion tables.

Separate from `repository.py` because that module is already the scan pipeline's
storage and these are a different subsystem — sessions, attribution, decisions,
consequences. Same patterns: aiosqlite, bound parameters, models in and models
out, so callers never handle raw rows.

Every insert returns the stored model with its assigned id, and every query
returns models rather than dicts. The point is that the guarantees in
`models/fusion.py` — shares summing to 100, a consequence being about something,
a causal claim being declared — hold on the way out of the database as well as
on the way in.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import Any

import aiosqlite

from mri.models.fusion import (
    AuthorshipShare,
    Consequence,
    Decision,
    Session,
    SessionEvent,
    SessionFileTouch,
)
from mri.utils import utc_iso

__all__ = [
    "CrossProjectSessionError",
    "authorship_for_file",
    "insert_session_events",
    "insert_session_file_touches",
    "consequences_for_decision",
    "decisions_affecting_file",
    "decisions_for_file",
    "events_for_session",
    "get_session",
    "insert_authorship_share",
    "insert_consequence",
    "insert_decision",
    "insert_decisions_ignoring_duplicates",
    "insert_session_event",
    "insert_decision_link",
    "insert_session_file_touch",
    "link_decision_files",
    "related_decisions",
    "replace_decisions_of_source",
    "set_touch_commit",
    "touches_for_file",
    "uncommitted_write_touches",
    "upsert_session",
]


logger = logging.getLogger(__name__)

#: Ceiling on rows returned by any query here. The per-function defaults are the
#: sensible page size; this is the backstop for a caller that passes its own
#: `limit` straight through from a request. Clamping belongs here rather than at
#: the call site, because there will be more than one call site.
MAX_ROWS = 5_000

#: Rows per executemany during bulk ingest. The whole batch used to be
#: materialised at once: a real 88,824-turn session measured a 132.6 MB peak,
#: five times the parse itself, purely from building every model up front.
#: Chunking bounds that while keeping one transaction, so the insert is still
#: all-or-nothing.
INSERT_CHUNK = 2_000

#: Stored when `confounders` cannot be parsed. An empty list would read as "no
#: alternative explanations were considered", which is a claim, and the wrong
#: one — the caveat on the finding is damaged, not absent, and a reader has to
#: be able to tell those apart.
UNREADABLE_CONFOUNDERS = "<unreadable: the stored value was not valid JSON>"


#: Two fixed statements rather than one assembled from a flag. Nothing here is
#: user input, but a query built by string concatenation is a pattern worth not
#: having in the file at all — the next edit is the one that interpolates a
#: value.
_EVENTS_WITH_CONTENT = (
    "SELECT * FROM session_events WHERE session_id = ? ORDER BY seq LIMIT ?"
)
_EVENTS_WITHOUT_CONTENT = (
    "SELECT id, session_id, seq, role, kind, NULL AS content, content_hash,"
    " occurred_at, created_at"
    " FROM session_events WHERE session_id = ? ORDER BY seq LIMIT ?"
)


def _chunks(items: Iterable[Any], size: int) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _limit(value: int) -> int:
    return max(1, min(value, MAX_ROWS))


def _iso(value: Any) -> str | None:
    """Serialise a timestamp for storage: datetimes as canonical UTC, other
    date-like values by their own isoformat, everything else unchanged.

    A bare `date` (which has `isoformat` but no tz) is stringified rather than
    passed through, because Python 3.14 dropped the default sqlite3 date adapter
    and a raw `date` would otherwise fail to bind."""
    if isinstance(value, datetime):
        return utc_iso(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _confounders(raw: Any, *, row_id: Any) -> list[str]:
    """Decode the stored JSON, surviving a row that was written badly.

    Every write here goes through a validated model, so this should be
    unreachable. It exists because a backfill, a fixup script, or a future
    importer could put something else in the column, and one damaged row must
    not take down the whole read — the other consequences are still true.
    """
    try:
        decoded = json.loads(raw or "[]")
    except (TypeError, ValueError):
        logger.warning("consequence %s has unreadable confounders; reporting it as damaged", row_id)
        return [UNREADABLE_CONFOUNDERS]
    if not isinstance(decoded, list):
        logger.warning("consequence %s stored confounders as %s, not a list", row_id, type(decoded).__name__)
        return [UNREADABLE_CONFOUNDERS]
    return [str(item) for item in decoded]


class CrossProjectSessionError(RuntimeError):
    """A session id already recorded under one project was re-ingested under
    another. A real agent-session id is globally unique and belongs to one
    workspace, so this only happens through a forged or corrupted log — and
    silently reassigning it hijacked (and, via rewrite-detection, could delete)
    the first project's data. It is refused rather than obeyed."""


async def upsert_session(conn: aiosqlite.Connection, session: Session) -> Session:
    """Record a session, or return the existing one.

    Sessions are keyed by (source, external_id): a real agent-session id is a
    globally-unique UUID that happened in exactly one workspace, so identity is
    global and re-ingesting the same log is idempotent.

    Two project transitions are handled explicitly rather than by a blind
    `project_id = excluded.project_id`, which an audit showed could hijack or
    delete another project's data:

      * unclaimed -> claimed (project_id was NULL, now real): the session is
        *adopted* by the project, and its already-stored touches are backfilled
        to it so a scan-then-register workflow does not strand them at NULL;
      * one real project -> a different real project: refused. A globally-unique
        id cannot legitimately belong to two projects, so this is forgery or
        corruption, not a re-scan.
    """
    existing = await get_session(conn, session.source, session.external_id)
    if (
        existing is not None
        and existing.project_id is not None
        and session.project_id is not None
        and existing.project_id != session.project_id
    ):
        raise CrossProjectSessionError(
            f"session {session.source}/{session.external_id} is already recorded under "
            f"project {existing.project_id}; refusing to move it to {session.project_id}"
        )

    # Keep an existing project link if this ingest did not supply one, so a
    # metadata-only re-run cannot un-claim a session.
    effective_project = session.project_id if session.project_id is not None else (
        existing.project_id if existing else None
    )
    await conn.execute(
        """
        INSERT INTO sessions
            (source, external_id, project_id, workspace_path, started_at, ended_at, content_stored)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, external_id) DO UPDATE SET
            project_id     = excluded.project_id,
            workspace_path = excluded.workspace_path,
            started_at     = COALESCE(excluded.started_at, sessions.started_at),
            ended_at       = COALESCE(excluded.ended_at, sessions.ended_at),
            content_stored = excluded.content_stored
        """,
        (
            session.source,
            session.external_id,
            effective_project,
            session.workspace_path,
            _iso(session.started_at),
            _iso(session.ended_at),
            int(session.content_stored),
        ),
    )
    stored = await get_session(conn, session.source, session.external_id)
    if stored is None:  # pragma: no cover - the row was just written
        raise RuntimeError(f"session vanished after upsert: {session.source}/{session.external_id}")

    # Adoption: a session that was unclaimed and is now claimed backfills the
    # project onto touches written while it was unclaimed, so they become
    # visible to the project's file-keyed reads instead of stranded at NULL.
    if existing is not None and existing.project_id is None and effective_project is not None:
        await conn.execute(
            "UPDATE session_file_touches SET project_id = ? WHERE session_id = ? AND project_id IS NULL",
            (effective_project, stored.id),
        )
    await conn.commit()
    return stored


async def get_session(
    conn: aiosqlite.Connection, source: str, external_id: str
) -> Session | None:
    cursor = await conn.execute(
        "SELECT * FROM sessions WHERE source = ? AND external_id = ?", (source, external_id)
    )
    row = await cursor.fetchone()
    return Session(**dict(row)) if row else None


async def insert_session_event(
    conn: aiosqlite.Connection, event: SessionEvent
) -> SessionEvent:
    cursor = await conn.execute(
        """
        INSERT INTO session_events
            (session_id, seq, role, kind, content, content_hash, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.session_id,
            event.seq,
            event.role,
            event.kind,
            event.content,
            event.content_hash,
            _iso(event.occurred_at),
        ),
    )
    await conn.commit()
    return event.model_copy(update={"id": int(cursor.lastrowid or 0)})


async def insert_session_events(
    conn: aiosqlite.Connection, events: Iterable[SessionEvent]
) -> int:
    """Insert many turns in one transaction.

    Ingest reads a whole log at once, and committing per row makes the fsync
    cost dominate: measured at 50,000 events, 18.6 s row-by-row against 8.0 s
    in a single transaction. The single-row writers stay as they are — they are
    correct for interactive use, where a commit per call is the point.
    """
    written = 0
    for batch in _chunks(events, INSERT_CHUNK):
        await conn.executemany(
            """
            INSERT INTO session_events
                (session_id, seq, role, kind, content, content_hash, occurred_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (e.session_id, e.seq, e.role, e.kind, e.content, e.content_hash,
                 _iso(e.occurred_at))
                for e in batch
            ],
        )
        written += len(batch)
    if written:
        await conn.commit()
    return written


async def insert_session_file_touches(
    conn: aiosqlite.Connection, touches: Iterable[SessionFileTouch]
) -> int:
    """Insert many file touches in one transaction. See `insert_session_events`."""
    written = 0
    for batch in _chunks(touches, INSERT_CHUNK):
        await conn.executemany(
            """
            INSERT INTO session_file_touches
                (session_id, project_id, event_id, file_path, commit_sha, touch_kind,
                 confidence, occurred_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (t.session_id, t.project_id, t.event_id, t.file_path, t.commit_sha,
                 t.touch_kind, t.confidence, _iso(t.occurred_at))
                for t in batch
            ],
        )
        written += len(batch)
    if written:
        await conn.commit()
    return written


async def events_for_session(
    conn: aiosqlite.Connection, session_id: int, *, limit: int = 500,
    include_content: bool = True,
) -> list[SessionEvent]:
    """Turns in a session, oldest first.

    `include_content=False` omits the content column. When retention is on,
    content is the bulk of the row: a 500-turn page measured 4.5 ms and ~2.4 MB
    with it, 2.3 ms without. Anything that lists or counts turns rather than
    displaying them should pass False — and gets `content=None`, which is
    honest, since it did not ask for the content rather than found none.
    """
    query = _EVENTS_WITH_CONTENT if include_content else _EVENTS_WITHOUT_CONTENT
    cursor = await conn.execute(query, (session_id, _limit(limit)))
    return [SessionEvent(**dict(r)) for r in await cursor.fetchall()]


async def insert_session_file_touch(
    conn: aiosqlite.Connection, touch: SessionFileTouch
) -> SessionFileTouch:
    cursor = await conn.execute(
        """
        INSERT INTO session_file_touches
            (session_id, project_id, event_id, file_path, commit_sha, touch_kind,
             confidence, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            touch.session_id,
            touch.project_id,
            touch.event_id,
            touch.file_path,
            touch.commit_sha,
            touch.touch_kind,
            touch.confidence,
            _iso(touch.occurred_at),
        ),
    )
    await conn.commit()
    return touch.model_copy(update={"id": int(cursor.lastrowid or 0)})


async def uncommitted_write_touches(
    conn: aiosqlite.Connection, project_id: int
) -> list[SessionFileTouch]:
    """Write/create touches in a project not yet linked to a commit and with a
    time to correlate on. These are the input to session->commit correlation:
    a read is not authorship, and a touch with no time cannot be placed against
    commit history.
    """
    cursor = await conn.execute(
        "SELECT * FROM session_file_touches"
        " WHERE project_id = ? AND commit_sha IS NULL AND occurred_at IS NOT NULL"
        "   AND touch_kind IN ('write', 'create', 'delete')"
        " ORDER BY occurred_at",
        (project_id,),
    )
    return [SessionFileTouch(**dict(r)) for r in await cursor.fetchall()]


async def set_touch_commit(conn: aiosqlite.Connection, touch_id: int, commit_sha: str) -> None:
    """Link one touch to the commit that materialised it."""
    await conn.execute(
        "UPDATE session_file_touches SET commit_sha = ? WHERE id = ?", (commit_sha, touch_id)
    )


async def touches_for_file(
    conn: aiosqlite.Connection, file_path: str, *, project_id: int, limit: int = 200
) -> list[SessionFileTouch]:
    """Touches on a file in one project, most recent first.

    `project_id` is required, not optional: a file path is only unique within a
    project, and two repos in one database sharing a name like "README.md" would
    otherwise blend their touches. SQLite sorts NULLs last under DESC, so touches
    with no `occurred_at` fall to the end — an untimed touch is not recent, it is
    unplaced.
    """
    cursor = await conn.execute(
        "SELECT * FROM session_file_touches WHERE project_id = ? AND file_path = ?"
        " ORDER BY occurred_at DESC LIMIT ?",
        (project_id, file_path, _limit(limit)),
    )
    return [SessionFileTouch(**dict(r)) for r in await cursor.fetchall()]


async def insert_authorship_share(
    conn: aiosqlite.Connection, share: AuthorshipShare
) -> AuthorshipShare:
    cursor = await conn.execute(
        """
        INSERT INTO authorship_shares
            (project_id, file_path, commit_sha, share_ai, share_human, share_unattributed,
             method, confidence, computed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            share.project_id,
            share.file_path,
            share.commit_sha,
            share.share_ai,
            share.share_human,
            share.share_unattributed,
            share.method,
            share.confidence,
            _iso(share.computed_at),
        ),
    )
    await conn.commit()
    return share.model_copy(update={"id": int(cursor.lastrowid or 0)})


async def authorship_for_file(
    conn: aiosqlite.Connection, file_path: str, *, project_id: int, limit: int = 50
) -> list[AuthorshipShare]:
    cursor = await conn.execute(
        "SELECT * FROM authorship_shares WHERE project_id = ? AND file_path = ?"
        " ORDER BY computed_at DESC LIMIT ?",
        (project_id, file_path, _limit(limit)),
    )
    return [AuthorshipShare(**dict(r)) for r in await cursor.fetchall()]


_DECISION_COLUMNS = (
    "summary, rationale, source, source_ref, session_id, project_id, file_path, "
    "commit_sha, decided_at, status, confidence"
)
# Built once from a module constant of literal column names — no value is ever
# interpolated, so the S608 warning is a false positive here. Concentrated to
# these two lines rather than repeated at each call site.
_DECISION_PLACEHOLDERS = "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?"
_INSERT_DECISION_SQL = (
    f"INSERT INTO decisions ({_DECISION_COLUMNS}) VALUES ({_DECISION_PLACEHOLDERS})"  # noqa: S608
)
_INSERT_OR_IGNORE_DECISION_SQL = (
    f"INSERT OR IGNORE INTO decisions ({_DECISION_COLUMNS}) VALUES ({_DECISION_PLACEHOLDERS})"  # noqa: S608, E501
)


def _decision_row(decision: Decision) -> tuple[Any, ...]:
    return (
        decision.summary,
        decision.rationale,
        decision.source,
        decision.source_ref,
        decision.session_id,
        decision.project_id,
        decision.file_path,
        decision.commit_sha,
        _iso(decision.decided_at),
        decision.status,
        decision.confidence,
    )


async def insert_decision(conn: aiosqlite.Connection, decision: Decision) -> Decision:
    cursor = await conn.execute(_INSERT_DECISION_SQL, _decision_row(decision))
    await conn.commit()
    return decision.model_copy(update={"id": int(cursor.lastrowid or 0)})


async def replace_decisions_of_source(
    conn: aiosqlite.Connection,
    source: str,
    decisions: list[Decision],
    *,
    project_id: int | None = None,
) -> int:
    """Atomically swap the decisions of one source for a new set.

    The old delete-then-insert-in-a-loop left the table empty for any reader
    that looked mid-refresh, and lost everything if an insert failed partway —
    an audit reproduced a crafted ADR wiping the provenance it was meant to
    record. Delete and re-insert now share one transaction: it either replaces
    the set whole or leaves the previous set untouched.

    When `project_id` is given the swap is scoped to that project, so refreshing
    one repo's ADRs does not wipe another's. When it is None the whole source is
    replaced, preserving the single-project default.
    """
    try:
        await conn.execute("BEGIN")
        if project_id is None:
            await conn.execute("DELETE FROM decisions WHERE source = ?", (source,))
        else:
            await conn.execute(
                "DELETE FROM decisions WHERE source = ? AND project_id IS ?",
                (source, project_id),
            )
        await conn.executemany(_INSERT_DECISION_SQL, [_decision_row(d) for d in decisions])
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    return len(decisions)


async def insert_decisions_ignoring_duplicates(
    conn: aiosqlite.Connection, decisions: list[Decision]
) -> int:
    """Insert decisions, skipping any whose (source, source_ref) already exists.

    One transaction, and the skip is the database's job via the natural-key
    unique index (migration 0005), not a read-then-write check — so two ingests
    racing cannot both decide a commit is new and both insert it.
    """
    if not decisions:
        return 0
    before = (await (await conn.execute("SELECT count(*) FROM decisions")).fetchone())[0]
    try:
        await conn.execute("BEGIN")
        await conn.executemany(
            _INSERT_OR_IGNORE_DECISION_SQL, [_decision_row(d) for d in decisions]
        )
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    after = (await (await conn.execute("SELECT count(*) FROM decisions")).fetchone())[0]
    return int(after - before)


async def decisions_for_file(
    conn: aiosqlite.Connection, file_path: str, *, project_id: int, limit: int = 50
) -> list[Decision]:
    cursor = await conn.execute(
        "SELECT * FROM decisions WHERE project_id = ? AND file_path = ?"
        " ORDER BY decided_at DESC LIMIT ?",
        (project_id, file_path, _limit(limit)),
    )
    return [Decision(**dict(r)) for r in await cursor.fetchall()]


async def insert_decision_link(
    conn: aiosqlite.Connection, decision_id: int, related_decision_id: int,
    project_id: int | None, relation: str,
) -> bool:
    """Record that two decisions describe the same choice. Idempotent, and a
    self-link is impossible (the CHECK enforces it). Returns True only when a
    new link was actually written, so a caller can count real links rather than
    attempts."""
    if decision_id == related_decision_id:
        return False
    cursor = await conn.execute(
        "INSERT OR IGNORE INTO decision_links"
        " (decision_id, related_decision_id, project_id, relation) VALUES (?, ?, ?, ?)",
        (decision_id, related_decision_id, project_id, relation),
    )
    await conn.commit()
    return bool(cursor.rowcount)


async def related_decisions(
    conn: aiosqlite.Connection, decision_id: int, *, project_id: int
) -> list[Decision]:
    """Decisions linked to this one as the same choice, either direction."""
    cursor = await conn.execute(
        "SELECT * FROM decisions WHERE project_id = ? AND id IN ("
        "  SELECT related_decision_id FROM decision_links WHERE decision_id = ?"
        "  UNION SELECT decision_id FROM decision_links WHERE related_decision_id = ?)"
        " ORDER BY decided_at DESC",
        (project_id, decision_id, decision_id),
    )
    return [Decision(**dict(r)) for r in await cursor.fetchall()]


async def link_decision_files(
    conn: aiosqlite.Connection, decision_id: int, project_id: int | None, file_paths: list[str]
) -> None:
    """Record the files a decision concerns (a commit changes many). Idempotent
    via the (decision_id, file_path) unique key, so re-linking is a no-op."""
    if not file_paths:
        return
    await conn.executemany(
        "INSERT OR IGNORE INTO decision_files (decision_id, project_id, file_path)"
        " VALUES (?, ?, ?)",
        [(decision_id, project_id, path) for path in file_paths],
    )
    await conn.commit()


async def decisions_affecting_file(
    conn: aiosqlite.Connection, file_path: str, *, project_id: int, limit: int = 50
) -> list[Decision]:
    """Decisions that concern a file, by its own `file_path` (an ADR naming it)
    or by a `decision_files` link (a commit that changed it). The union is what
    the per-file explanation needs — a commit's decision reaches its files
    through the link table, an ADR's through the column."""
    cursor = await conn.execute(
        "SELECT d.* FROM decisions d"
        " WHERE d.project_id = ? AND ("
        "   d.file_path = ?"
        "   OR d.id IN (SELECT decision_id FROM decision_files"
        "               WHERE project_id = ? AND file_path = ?))"
        " ORDER BY d.decided_at DESC LIMIT ?",
        (project_id, file_path, project_id, file_path, _limit(limit)),
    )
    return [Decision(**dict(r)) for r in await cursor.fetchall()]


async def insert_consequence(
    conn: aiosqlite.Connection, consequence: Consequence
) -> Consequence:
    cursor = await conn.execute(
        """
        INSERT INTO consequences
            (decision_id, session_id, metric, file_path, window_start, window_end,
             baseline_value, observed_value, delta, causal_claim, confounders, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            consequence.decision_id,
            consequence.session_id,
            consequence.metric,
            consequence.file_path,
            _iso(consequence.window_start),
            _iso(consequence.window_end),
            consequence.baseline_value,
            consequence.observed_value,
            consequence.delta,
            consequence.causal_claim,
            json.dumps(consequence.confounders),
            consequence.confidence,
        ),
    )
    await conn.commit()
    return consequence.model_copy(update={"id": int(cursor.lastrowid or 0)})


async def consequences_for_decision(
    conn: aiosqlite.Connection, decision_id: int, *, project_id: int, limit: int = 100
) -> list[Consequence]:
    """Consequences of one decision, scoped to its project.

    `project_id` is required and checked against the owning decision, so a
    future endpoint that accepts a decision id from a request cannot read
    another project's consequences by guessing an id (the ids are sequential).
    """
    cursor = await conn.execute(
        "SELECT c.* FROM consequences c JOIN decisions d ON d.id = c.decision_id"
        " WHERE c.decision_id = ? AND d.project_id = ?"
        " ORDER BY c.window_end DESC LIMIT ?",
        (decision_id, project_id, _limit(limit)),
    )
    out: list[Consequence] = []
    for row in await cursor.fetchall():
        data = dict(row)
        # Stored as JSON; the model works with the list.
        data["confounders"] = _confounders(data.get("confounders"), row_id=data.get("id"))
        out.append(Consequence(**data))
    return out
