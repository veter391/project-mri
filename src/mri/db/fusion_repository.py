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
from datetime import timezone
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

_UTC = timezone.utc

__all__ = [
    "authorship_for_file",
    "insert_session_events",
    "insert_session_file_touches",
    "consequences_for_decision",
    "decisions_for_file",
    "events_for_session",
    "get_session",
    "insert_authorship_share",
    "insert_consequence",
    "insert_decision",
    "insert_decisions_ignoring_duplicates",
    "insert_session_event",
    "insert_session_file_touch",
    "replace_decisions_of_source",
    "touches_for_file",
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
    """Canonical UTC ISO-8601, so stored timestamps sort chronologically.

    Timestamps in this database are compared as strings by SQLite, which is only
    correct when they share one offset. A commit authored at +09:00 and a scan
    stored at +00:00 would otherwise sort by their written offset, not their
    instant — an audit showed that picking a post-decision scan as the baseline
    and fabricating a delta. Everything is normalised to UTC; a naive datetime
    is assumed to already be UTC rather than guessed at.
    """
    tzinfo = getattr(value, "tzinfo", None)
    if not hasattr(value, "isoformat"):
        return value
    if tzinfo is not None:
        value = value.astimezone(_UTC)
    elif hasattr(value, "replace") and hasattr(value, "hour"):
        value = value.replace(tzinfo=_UTC)  # a naive datetime; take it as UTC
    return value.isoformat()


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


async def upsert_session(conn: aiosqlite.Connection, session: Session) -> Session:
    """Record a session, or return the existing one.

    Sessions are keyed by (source, external_id) so re-ingesting the same log is
    idempotent — a scan that runs twice must not double-count a session's
    influence on attribution.
    """
    await conn.execute(
        """
        INSERT INTO sessions
            (source, external_id, workspace_path, started_at, ended_at, content_stored)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, external_id) DO UPDATE SET
            workspace_path = excluded.workspace_path,
            started_at     = COALESCE(excluded.started_at, sessions.started_at),
            ended_at       = COALESCE(excluded.ended_at, sessions.ended_at),
            content_stored = excluded.content_stored
        """,
        (
            session.source,
            session.external_id,
            session.workspace_path,
            _iso(session.started_at),
            _iso(session.ended_at),
            int(session.content_stored),
        ),
    )
    await conn.commit()
    stored = await get_session(conn, session.source, session.external_id)
    if stored is None:  # pragma: no cover - the row was just written
        raise RuntimeError(f"session vanished after upsert: {session.source}/{session.external_id}")
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
                (session_id, event_id, file_path, commit_sha, touch_kind, confidence,
                 occurred_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (t.session_id, t.event_id, t.file_path, t.commit_sha, t.touch_kind,
                 t.confidence, _iso(t.occurred_at))
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
            (session_id, event_id, file_path, commit_sha, touch_kind, confidence, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            touch.session_id,
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


async def touches_for_file(
    conn: aiosqlite.Connection, file_path: str, *, limit: int = 200
) -> list[SessionFileTouch]:
    """Touches on a file, most recent first.

    SQLite sorts NULLs last under DESC, so touches with no `occurred_at` — ones
    not yet correlated to a time — fall to the end and drop off the page once a
    file has `limit` timestamped touches. That is the intended reading of "most
    recent": an untimed touch is not recent, it is unplaced.
    """
    cursor = await conn.execute(
        "SELECT * FROM session_file_touches WHERE file_path = ? ORDER BY occurred_at DESC LIMIT ?",
        (file_path, _limit(limit)),
    )
    return [SessionFileTouch(**dict(r)) for r in await cursor.fetchall()]


async def insert_authorship_share(
    conn: aiosqlite.Connection, share: AuthorshipShare
) -> AuthorshipShare:
    cursor = await conn.execute(
        """
        INSERT INTO authorship_shares
            (file_path, commit_sha, share_ai, share_human, share_unattributed,
             method, confidence, computed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
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
    conn: aiosqlite.Connection, file_path: str, *, limit: int = 50
) -> list[AuthorshipShare]:
    cursor = await conn.execute(
        "SELECT * FROM authorship_shares WHERE file_path = ? ORDER BY computed_at DESC LIMIT ?",
        (file_path, _limit(limit)),
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
    conn: aiosqlite.Connection, file_path: str, *, limit: int = 50
) -> list[Decision]:
    cursor = await conn.execute(
        "SELECT * FROM decisions WHERE file_path = ? ORDER BY decided_at DESC LIMIT ?",
        (file_path, _limit(limit)),
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
    conn: aiosqlite.Connection, decision_id: int, *, limit: int = 100
) -> list[Consequence]:
    cursor = await conn.execute(
        "SELECT * FROM consequences WHERE decision_id = ? ORDER BY window_end DESC LIMIT ?",
        (decision_id, _limit(limit)),
    )
    out: list[Consequence] = []
    for row in await cursor.fetchall():
        data = dict(row)
        # Stored as JSON; the model works with the list.
        data["confounders"] = _confounders(data.get("confounders"), row_id=data.get("id"))
        out.append(Consequence(**data))
    return out
