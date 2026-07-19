"""Decision provenance.

The point these tests defend: a decision mined from a bare commit has a clear
what and no why, and the why must stay absent rather than be invented from the
subject line. That is the one thing a provenance record exists to get right.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mri.db.migrator import migrate
from mri.db.repository import get_connection
from mri.fusion import ingest_adrs, parse_adr
from mri.fusion.decisions import (
    COMMIT_SUBJECT_ONLY_CONFIDENCE,
    COMMIT_WITH_RATIONALE_CONFIDENCE,
    _commit_decision,
)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "dp.db"
    migrate(path)
    return path


class _FakeCommit:
    """A commit shaped like GitPython's, without needing a real repo."""

    def __init__(self, sha: str, message: str, when):
        self.hexsha = sha
        self.message = message
        self.authored_datetime = when


# ---------------------------------------------------------------------------
# Commits: the honesty rule
# ---------------------------------------------------------------------------


def test_a_bare_commit_has_no_invented_rationale():
    """A subject with no body is a what without a why. The why stays None."""
    from datetime import datetime

    decision = _commit_decision(_FakeCommit("abc123", "fix: off-by-one", datetime(2026, 1, 1)))
    assert decision.summary == "fix: off-by-one"
    assert decision.rationale is None, "no body means no recoverable why"
    assert decision.confidence == COMMIT_SUBJECT_ONLY_CONFIDENCE


def test_a_commit_body_becomes_the_rationale_as_a_claim_not_a_fact():
    from datetime import datetime

    decision = _commit_decision(
        _FakeCommit("abc123", "fix: off-by-one\n\nThe loop skipped the last row.", datetime(2026, 1, 1))
    )
    assert decision.summary == "fix: off-by-one"
    assert decision.rationale == "The loop skipped the last row."
    assert decision.confidence == COMMIT_WITH_RATIONALE_CONFIDENCE
    assert decision.confidence < 1.0, "a stated reason is the author's claim, not certainty"


def test_the_subject_is_never_copied_into_the_rationale():
    """The failure mode this whole layer guards against: dressing a missing why
    as a present one by repeating the what."""
    from datetime import datetime

    decision = _commit_decision(_FakeCommit("abc", "refactor: extract module", datetime(2026, 1, 1)))
    assert decision.rationale != decision.summary
    assert decision.rationale is None


# ---------------------------------------------------------------------------
# ADRs
# ---------------------------------------------------------------------------


def test_parse_adr_pulls_title_and_body():
    text = (
        "# ADR-042 — Use SQLite\n\n"
        "- **Status:** Accepted\n- **Date:** 2026-03-14\n\n"
        "## Context\nWe need a local store.\n\n## Decision\nSQLite it is.\n"
    )
    parsed = parse_adr(text)
    assert parsed is not None
    assert parsed.summary == "ADR-042 — Use SQLite"
    assert "We need a local store." in parsed.rationale
    assert "SQLite it is." in parsed.rationale
    assert parsed.status == "Accepted"
    assert parsed.decided_at is not None
    assert parsed.decided_at.year == 2026


def test_a_file_with_no_title_is_not_an_adr():
    """Guessing a summary from a filename would be inventing one."""
    assert parse_adr("just some prose with no heading\n") is None


async def test_ingest_adrs_records_each_and_is_refreshable(db: Path, tmp_path: Path):
    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    (adr_dir / "ADR-001-x.md").write_text(
        "# ADR-001 — First\n\n- **Status:** Accepted\n\n## Decision\nDo X.\n", encoding="utf-8"
    )
    (adr_dir / "ADR-002-y.md").write_text(
        "# ADR-002 — Second\n\n- **Status:** Accepted\n\n## Decision\nDo Y.\n", encoding="utf-8"
    )
    (adr_dir / "README.md").write_text("# Index\nnot a decision\n", encoding="utf-8")

    async with get_connection(db) as conn:
        count = await ingest_adrs(conn, adr_dir)
        assert count == 2, "the README index is not a decision"

        # Re-running must not double-count, and must pick up an edit.
        (adr_dir / "ADR-002-y.md").write_text(
            "# ADR-002 — Second, revised\n\n- **Status:** Superseded\n\n## Decision\nDo Z.\n",
            encoding="utf-8",
        )
        again = await ingest_adrs(conn, adr_dir)
        assert again == 2

        cursor = await conn.execute("SELECT count(*) FROM decisions WHERE source = 'adr'")
        assert (await cursor.fetchone())[0] == 2, "refresh must replace, not stack"
        cursor = await conn.execute(
            "SELECT summary FROM decisions WHERE source_ref = 'ADR-002-y.md'"
        )
        assert (await cursor.fetchone())[0] == "ADR-002 — Second, revised"


async def test_missing_adr_directory_is_zero_not_an_error(db: Path, tmp_path: Path):
    async with get_connection(db) as conn:
        assert await ingest_adrs(conn, tmp_path / "nope") == 0


# ---------------------------------------------------------------------------
# Commit ingest against the real repo
# ---------------------------------------------------------------------------


async def test_ingest_commits_is_idempotent(db: Path):
    from datetime import datetime, timezone

    from mri.fusion.decisions import ingest_commits

    class _FakeRepo:
        def __init__(self, commits):
            self._commits = commits

        def iter_commits(self, branch, max_count):  # noqa: ARG002
            return iter(self._commits[:max_count])

    commits = [
        _FakeCommit("sha1", "feat: a\n\nbecause reasons", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        _FakeCommit("sha2", "fix: b", datetime(2026, 1, 2, tzinfo=timezone.utc)),
    ]
    repo_obj = _FakeRepo(commits)

    async with get_connection(db) as conn:
        first = await ingest_commits(conn, repo_obj)
        assert first == 2
        again = await ingest_commits(conn, repo_obj)
        assert again == 0, "a commit already stored is not re-inserted"

        cursor = await conn.execute(
            "SELECT rationale FROM decisions WHERE source = 'commit' AND source_ref = 'sha2'"
        )
        assert (await cursor.fetchone())[0] is None, "the bodyless commit kept a null rationale"
