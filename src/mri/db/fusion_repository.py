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

__all__ = [
    "authorship_for_file",
    "consequences_for_decision",
    "decisions_for_file",
    "events_for_session",
    "get_session",
    "insert_authorship_share",
    "insert_consequence",
    "insert_decision",
    "insert_session_event",
    "insert_session_file_touch",
    "touches_for_file",
    "upsert_session",
]


logger = logging.getLogger(__name__)

#: Ceiling on rows returned by any query here. The per-function defaults are the
#: sensible page size; this is the backstop for a caller that passes its own
#: `limit` straight through from a request. Clamping belongs here rather than at
#: the call site, because there will be more than one call site.
MAX_ROWS = 5_000

#: Stored when `confounders` cannot be parsed. An empty list would read as "no
#: alternative explanations were considered", which is a claim, and the wrong
#: one — the caveat on the finding is damaged, not absent, and a reader has to
#: be able to tell those apart.
UNREADABLE_CONFOUNDERS = "<unreadable: the stored value was not valid JSON>"


def _limit(value: int) -> int:
    return max(1, min(value, MAX_ROWS))


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


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


async def events_for_session(
    conn: aiosqlite.Connection, session_id: int, *, limit: int = 500
) -> list[SessionEvent]:
    cursor = await conn.execute(
        "SELECT * FROM session_events WHERE session_id = ? ORDER BY seq LIMIT ?",
        (session_id, _limit(limit)),
    )
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


async def insert_decision(conn: aiosqlite.Connection, decision: Decision) -> Decision:
    cursor = await conn.execute(
        """
        INSERT INTO decisions
            (summary, rationale, source, source_ref, session_id, file_path,
             commit_sha, decided_at, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision.summary,
            decision.rationale,
            decision.source,
            decision.source_ref,
            decision.session_id,
            decision.file_path,
            decision.commit_sha,
            _iso(decision.decided_at),
            decision.confidence,
        ),
    )
    await conn.commit()
    return decision.model_copy(update={"id": int(cursor.lastrowid or 0)})


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
