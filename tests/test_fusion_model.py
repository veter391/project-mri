"""The data model the fusion layers are built on.

These tests exist to protect two properties that the product's credibility rests
on, and they are enforced twice — once by the schema, once by the models:

  * an attribution accounts for the whole file, and "we do not know" is a share
    with a name rather than something quietly folded into "human";
  * a consequence says what kind of claim it is making, and nothing produces
    "causation" by default or by accident.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from mri.db import fusion_repository as repo
from mri.db.migrator import migrate
from mri.db.repository import get_connection
from mri.models.fusion import (
    AuthorshipShare,
    Consequence,
    Decision,
    Session,
    SessionEvent,
    SessionFileTouch,
)

FUSION_TABLES = {
    "sessions",
    "session_events",
    "session_file_touches",
    "authorship_shares",
    "decisions",
    "consequences",
}


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "fusion.db"
    migrate(path)
    return path


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_migration_creates_every_fusion_table(db: Path):
    conn = sqlite3.connect(db)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert FUSION_TABLES <= tables


def test_join_paths_are_indexed(db: Path):
    """The layers join on file path, commit sha, session and time. Without
    indices those joins degrade quietly as history accumulates."""
    conn = sqlite3.connect(db)
    try:
        indexed = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            )
        }
    finally:
        conn.close()
    for expected in (
        "idx_touches_file", "idx_touches_commit", "idx_touches_session",
        "idx_authorship_file", "idx_authorship_commit",
        "idx_decisions_file", "idx_decisions_commit", "idx_decisions_session",
        "idx_consequences_decision", "idx_consequences_window",
    ):
        assert expected in indexed, f"missing index {expected}"


def test_upgrading_a_pre_fusion_database_keeps_its_data(tmp_path: Path):
    """The plan requires both paths to work. A user on the previous schema, with
    real scans in it, must gain the fusion tables without losing anything."""
    from importlib.resources import files as pkg_files

    db = tmp_path / "existing.db"
    baseline = (
        pkg_files("mri").joinpath("db", "migrations", "0001_initial_schema.sql")
        .read_text(encoding="utf-8")
    )
    conn = sqlite3.connect(db)
    try:
        conn.executescript(baseline)
        conn.execute("INSERT INTO projects (name, path) VALUES ('legacy', '/tmp/legacy')")
        conn.commit()
    finally:
        conn.close()

    applied = migrate(db)
    assert "0001_initial_schema.sql" not in applied, "the baseline should be stamped, not re-run"
    assert "0002_fusion_model.sql" in applied

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT name FROM projects").fetchone()[0] == "legacy"
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert FUSION_TABLES <= tables


@pytest.mark.parametrize(
    ("sql", "args", "why"),
    [
        (
            "INSERT INTO authorship_shares (file_path, share_ai, share_human, share_unattributed)"
            " VALUES (?,?,?,?)",
            ("a.py", 40, 35, 10),
            "shares that do not account for the whole file",
        ),
        (
            "INSERT INTO authorship_shares (file_path, share_ai, share_human, share_unattributed,"
            " confidence) VALUES (?,?,?,?,?)",
            ("a.py", 50, 50, 0, 1.7),
            "a confidence outside 0..1",
        ),
        (
            "INSERT INTO consequences (metric, window_start, window_end) VALUES (?,?,?)",
            ("risk", "2026-01-01", "2026-02-01"),
            "a consequence about nothing",
        ),
        (
            "INSERT INTO consequences (session_id, metric, window_start, window_end, causal_claim)"
            " VALUES (?,?,?,?,?)",
            (1, "risk", "2026-01-01", "2026-02-01", "proven"),
            "a causal claim outside the vocabulary",
        ),
    ],
)
def test_schema_refuses_dishonest_rows(db: Path, sql: str, args: tuple, why: str):
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("INSERT INTO sessions (source, external_id) VALUES ('claude_code','s1')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, args)
    finally:
        conn.close()


def test_a_consequence_defaults_to_the_weaker_claim(db: Path):
    conn = sqlite3.connect(db)
    try:
        conn.execute("INSERT INTO sessions (source, external_id) VALUES ('claude_code','s1')")
        conn.execute(
            "INSERT INTO consequences (session_id, metric, window_start, window_end)"
            " VALUES (1, 'risk', '2026-01-01', '2026-02-01')"
        )
        claim, confounders = conn.execute(
            "SELECT causal_claim, confounders FROM consequences"
        ).fetchone()
    finally:
        conn.close()
    assert claim == "correlation"
    assert confounders == "[]"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def test_models_repeat_the_schema_guarantees():
    """The database is the last line of defence, not the only one — building a
    dishonest record in memory should fail at construction."""
    with pytest.raises(ValidationError, match="must sum to 100"):
        AuthorshipShare(file_path="a.py", share_ai=40, share_human=35, share_unattributed=10)
    with pytest.raises(ValidationError):
        Consequence(metric="risk", window_start="2026-01-01", window_end="2026-02-01")
    with pytest.raises(ValidationError):
        Consequence(
            session_id=1, metric="r", window_start="2026-01-01",
            window_end="2026-02-01", causal_claim="proven",
        )


def test_defaults_claim_nothing():
    """A record created without evidence must assert nothing — not human
    authorship, not causation, not confidence."""
    share = AuthorshipShare(file_path="x.py")
    assert (share.share_ai, share.share_human, share.share_unattributed) == (0.0, 0.0, 100.0)
    assert share.confidence == 0.0

    consequence = Consequence(
        session_id=1, metric="risk", window_start="2026-01-01", window_end="2026-02-01"
    )
    assert consequence.causal_claim == "correlation"
    assert consequence.confounders == []

    decision = Decision(summary="switched to X", source="commit")
    assert decision.rationale is None, "an unrecoverable why must stay absent, not be invented"


# ---------------------------------------------------------------------------
# Repository round trips
# ---------------------------------------------------------------------------


async def test_session_ingest_is_idempotent(db: Path):
    """Re-ingesting the same log must not double-count a session's influence."""
    async with get_connection(db) as conn:
        first = await repo.upsert_session(
            conn, Session(source="claude_code", external_id="abc", workspace_path="/repo")
        )
        again = await repo.upsert_session(
            conn, Session(source="claude_code", external_id="abc", workspace_path="/repo")
        )
        assert first.id == again.id

        cursor = await conn.execute("SELECT count(*) FROM sessions")
        assert (await cursor.fetchone())[0] == 1


async def test_round_trip_preserves_every_guarantee(db: Path):
    async with get_connection(db) as conn:
        session = await repo.upsert_session(
            conn, Session(source="cursor", external_id="s-1", content_stored=False)
        )
        assert session.id is not None

        event = await repo.insert_session_event(
            conn,
            SessionEvent(session_id=session.id, seq=1, role="user", content=None, content_hash="h1"),
        )
        assert event.id is not None
        events = await repo.events_for_session(conn, session.id)
        assert len(events) == 1
        assert events[0].content is None, "metadata-only ingest must survive the round trip"

        await repo.insert_session_file_touch(
            conn,
            SessionFileTouch(
                session_id=session.id, file_path="src/a.py", touch_kind="write", confidence=0.4
            ),
        )
        touches = await repo.touches_for_file(conn, "src/a.py")
        assert touches[0].confidence == 0.4
        assert touches[0].commit_sha is None, "an uncommitted touch is a real state"

        await repo.insert_authorship_share(
            conn,
            AuthorshipShare(
                file_path="src/a.py", share_ai=40, share_human=35, share_unattributed=25,
                method="session_overlap", confidence=0.6,
            ),
        )
        shares = await repo.authorship_for_file(conn, "src/a.py")
        assert shares[0].share_unattributed == 25
        assert shares[0].method == "session_overlap"

        decision = await repo.insert_decision(
            conn,
            Decision(
                summary="extracted the scoring module", rationale=None,
                source="commit", source_ref="deadbeef", file_path="src/a.py",
            ),
        )
        assert decision.id is not None
        assert (await repo.decisions_for_file(conn, "src/a.py"))[0].rationale is None

        await repo.insert_consequence(
            conn,
            Consequence(
                decision_id=decision.id, metric="complexity", file_path="src/a.py",
                window_start="2026-01-01", window_end="2026-02-01",
                baseline_value=30.0, observed_value=22.0, delta=-8.0,
                confounders=["a refactor landed in the same window"], confidence=0.35,
            ),
        )
        found = await repo.consequences_for_decision(conn, decision.id)
        assert found[0].causal_claim == "correlation"
        assert found[0].confounders == ["a refactor landed in the same window"], (
            "confounders must survive storage — they are the caveat on the claim"
        )


# ---------------------------------------------------------------------------
# Content retention (migration 0003)
# ---------------------------------------------------------------------------


async def test_retention_off_refuses_content(db: Path):
    """`content_stored` was decorative when 0002 shipped: a session could claim
    it kept no content while holding a pasted API key. The schema now refuses."""
    async with get_connection(db) as conn:
        session = await repo.upsert_session(
            conn, Session(source="claude_code", external_id="off", content_stored=False)
        )
        assert session.id is not None
        with pytest.raises(sqlite3.IntegrityError, match="content_stored"):
            await repo.insert_session_event(
                conn,
                SessionEvent(session_id=session.id, seq=1, role="user", content="sk-SECRET"),
            )

        # Metadata-only ingest is the supported path and still works.
        await repo.insert_session_event(
            conn,
            SessionEvent(session_id=session.id, seq=2, role="user", content=None, content_hash="h"),
        )
        assert len(await repo.events_for_session(conn, session.id)) == 1


async def test_retention_on_still_allows_contentless_turns(db: Path):
    """The inverse is deliberately not enforced — tool and system turns carry no
    content, and forcing an empty string there would be its own small lie."""
    async with get_connection(db) as conn:
        session = await repo.upsert_session(
            conn, Session(source="claude_code", external_id="on", content_stored=True)
        )
        assert session.id is not None
        await repo.insert_session_event(
            conn, SessionEvent(session_id=session.id, seq=1, role="user", content="hello")
        )
        await repo.insert_session_event(
            conn,
            SessionEvent(session_id=session.id, seq=2, role="tool", content=None, content_hash="h"),
        )
        assert len(await repo.events_for_session(conn, session.id)) == 2


def test_turning_retention_off_redacts_what_was_kept(db: Path):
    """Switching the flag off is a request to stop retaining, not to relabel.
    The content goes; the hashes stay, so turns remain correlatable."""
    conn = sqlite3.connect(db)
    try:
        conn.execute("INSERT INTO sessions (source, external_id, content_stored) VALUES ('cc','s',1)")
        conn.execute(
            "INSERT INTO session_events (session_id, seq, role, content, content_hash)"
            " VALUES (1, 1, 'user', 'sk-SECRET', 'h1')"
        )
        conn.commit()
        conn.execute("UPDATE sessions SET content_stored = 0 WHERE id = 1")
        conn.commit()
        content, content_hash = conn.execute(
            "SELECT content, content_hash FROM session_events"
        ).fetchone()
    finally:
        conn.close()
    assert content is None, "flipping retention off must drop the retained content"
    assert content_hash == "h1", "the hash must survive so turns stay correlatable"


def test_the_rule_holds_for_a_connection_that_bypasses_this_package(db: Path):
    """Enforced by the schema rather than by the repository, so a backfill or a
    fixup script cannot route around it."""
    conn = sqlite3.connect(db)
    try:
        conn.execute("INSERT INTO sessions (source, external_id, content_stored) VALUES ('cc','s',0)")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO session_events (session_id, seq, role, content)"
                " VALUES (1, 1, 'user', 'sk-SECRET')"
            )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Reads survive damaged rows and hostile limits
# ---------------------------------------------------------------------------


async def test_one_damaged_row_does_not_take_down_the_read(db: Path):
    """A row written outside the models must not make every sibling
    unreadable — and the damage must be visible rather than smoothed over."""
    conn = sqlite3.connect(db)
    try:
        conn.execute("INSERT INTO decisions (summary, source) VALUES ('d', 'commit')")
        for metric, confounders in (("good", '["a real caveat"]'), ("bad", "not-json")):
            conn.execute(
                "INSERT INTO consequences (decision_id, metric, window_start, window_end,"
                " confounders) VALUES (1, ?, '2026-01-01', '2026-02-01', ?)",
                (metric, confounders),
            )
        conn.commit()
    finally:
        conn.close()

    async with get_connection(db) as conn:
        found = {c.metric: c.confounders for c in await repo.consequences_for_decision(conn, 1)}
    assert found["good"] == ["a real caveat"]
    assert found["bad"] == [repo.UNREADABLE_CONFOUNDERS], (
        "a damaged caveat must report itself as damaged, not as an empty list — "
        "an empty list is the claim that nothing was considered"
    )


async def test_limits_are_clamped_by_the_repository(db: Path):
    """The ceiling lives here, not at the call site, because there will be more
    than one call site and one of them will pass a request parameter straight
    through."""
    async with get_connection(db) as conn:
        session = await repo.upsert_session(
            conn, Session(source="cc", external_id="lim", content_stored=False)
        )
        assert session.id is not None
        for seq in range(5):
            await repo.insert_session_event(
                conn, SessionEvent(session_id=session.id, seq=seq, role="user", content_hash="h")
            )
        assert len(await repo.events_for_session(conn, session.id, limit=10**9)) == 5

    assert repo._limit(10**9) == repo.MAX_ROWS
    assert repo._limit(0) == 1
    assert repo._limit(50) == 50


# ---------------------------------------------------------------------------
# Index and write-path tuning (migration 0004)
# ---------------------------------------------------------------------------


def test_list_queries_do_not_sort_after_filtering(db: Path):
    """The audit found every list query building a TEMP B-TREE because the
    index covered the filter column but not the sort column — invisible at
    average cardinality, 18x on a hot file. The composite indices removed it,
    and this is what stops them being 'simplified' back."""
    conn = sqlite3.connect(db)
    try:
        queries = [
            ("SELECT * FROM session_file_touches WHERE file_path = ?"
             " ORDER BY occurred_at DESC LIMIT 200", ("a.py",)),
            ("SELECT * FROM authorship_shares WHERE file_path = ?"
             " ORDER BY computed_at DESC LIMIT 50", ("a.py",)),
            ("SELECT * FROM decisions WHERE file_path = ?"
             " ORDER BY decided_at DESC LIMIT 50", ("a.py",)),
            ("SELECT * FROM consequences WHERE decision_id = ?"
             " ORDER BY window_end DESC LIMIT 100", (1,)),
        ]
        for sql, args in queries:
            plan = " ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, args))
            assert "TEMP B-TREE" not in plan, f"sort not covered by the index: {sql}\n{plan}"
    finally:
        conn.close()


def test_the_redundant_session_index_is_gone(db: Path):
    """UNIQUE (source, external_id) already serves a source-only lookup through
    its leftmost prefix, so a separate index on source could never be chosen."""
    conn = sqlite3.connect(db)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert "idx_sessions_source" not in names
        plan = " ".join(
            r[3] for r in conn.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM sessions WHERE source = ?", ("cc",)
            )
        )
        assert "sqlite_autoindex_sessions_1" in plan, plan
    finally:
        conn.close()


async def test_bulk_writers_round_trip(db: Path):
    """Ingest reads a whole log at once; these commit once rather than per row."""
    async with get_connection(db) as conn:
        session = await repo.upsert_session(
            conn, Session(source="cc", external_id="bulk", content_stored=False)
        )
        assert session.id is not None
        written = await repo.insert_session_events(
            conn,
            [
                SessionEvent(session_id=session.id, seq=i, role="user", content_hash=f"h{i}")
                for i in range(200)
            ],
        )
        assert written == 200
        assert len(await repo.events_for_session(conn, session.id, limit=500)) == 200

        touched = await repo.insert_session_file_touches(
            conn,
            [
                SessionFileTouch(
                    session_id=session.id, file_path=f"src/f{i}.py",
                    touch_kind="write", confidence=0.5,
                )
                for i in range(50)
            ],
        )
        assert touched == 50
        assert await repo.insert_session_events(conn, []) == 0, "an empty batch is not an error"


async def test_omitting_content_returns_absence_not_invention(db: Path):
    """A caller that did not ask for content gets None — the same value that
    means 'metadata-only ingest'. Both are honest; an empty string would not be."""
    async with get_connection(db) as conn:
        session = await repo.upsert_session(
            conn, Session(source="cc", external_id="proj", content_stored=True)
        )
        assert session.id is not None
        await repo.insert_session_event(
            conn, SessionEvent(session_id=session.id, seq=1, role="user", content="hello")
        )
        with_content = await repo.events_for_session(conn, session.id)
        without = await repo.events_for_session(conn, session.id, include_content=False)
    assert with_content[0].content == "hello"
    assert without[0].content is None
    assert without[0].content_hash == with_content[0].content_hash
