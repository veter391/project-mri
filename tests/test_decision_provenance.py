"""Decision provenance.

The point these tests defend: a decision mined from a bare commit has a clear
what and no why, and the why must stay absent rather than be invented from the
subject line. That is the one thing a provenance record exists to get right.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mri.db import fusion_repository as repo
from mri.db.migrator import migrate
from mri.db.repository import get_connection
from mri.fusion import ingest_adrs, parse_adr
from mri.fusion.decisions import (
    COMMIT_SUBJECT_ONLY_CONFIDENCE,
    COMMIT_WITH_RATIONALE_CONFIDENCE,
    _commit_decision,
)

#: Resolved once at import (sync), so the async regression test can gate on it
#: without a blocking filesystem call inside the event loop.
_REPO_ADR_DIR_EXISTS = Path("docs/adr").is_dir()


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

    class _FakeGit:
        def log(self, *args):  # noqa: ARG002 - no changed-file history in this fake
            return ""

    class _FakeRepo:
        def __init__(self, commits):
            self._commits = commits
            self.git = _FakeGit()

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


# ---------------------------------------------------------------------------
# What the block-7 audits found
# ---------------------------------------------------------------------------


def test_a_title_only_adr_has_no_invented_rationale():
    """The honesty rule applies to ADRs as much as commits: a title with no body
    is a what without a why, and the why stays None rather than an empty string
    dressed up at 0.95 confidence."""
    parsed = parse_adr("# ADR-000 Title only\n")
    assert parsed is not None
    assert parsed.rationale is None


def test_the_decision_date_comes_from_the_header_not_the_body():
    """An unscoped date search scavenged a date from a body subsection heading
    and presented it as the decision date. The date is read only from the
    metadata header before the first section."""
    text = (
        "# ADR-042 — Something\n\n"
        "- **Status:** Accepted\n\n"
        "## Context\nA rewrite happened on 2019-01-01 which we are undoing.\n"
    )
    parsed = parse_adr(text)
    assert parsed is not None
    assert parsed.decided_at is None, "no date in the header means no date, not one from the body"


def test_a_header_date_is_still_read():
    parsed = parse_adr("# ADR-1 — X\n\n- **Status:** Accepted · 2026-03-14\n\n## Decision\nDo it.\n")
    assert parsed is not None
    assert parsed.decided_at is not None
    assert parsed.decided_at.year == 2026


def test_status_is_parsed_across_its_real_forms_and_stored():
    """The status was parsed but had nowhere to go, so the "a supersession is
    picked up" claim was not true. It is now stored, and the parser handles the
    forms this repo's own ADRs actually use."""
    for text, expected in [
        ("# A\n\n- **Status:** Accepted\n", "Accepted"),
        ("# A\n\n> Status: **superseded**.\n", "superseded"),
        ("# A\n\n**Status:** Accepted · 2026-01-01\n", "Accepted"),
    ]:
        assert parse_adr(text).status == expected, text


async def test_status_is_persisted(db: Path, tmp_path: Path):
    from mri.fusion import ingest_adrs

    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    (adr_dir / "ADR-001.md").write_text(
        "# ADR-001 — X\n\n- **Status:** Superseded\n\n## Decision\nOld.\n", encoding="utf-8"
    )
    async with get_connection(db) as conn:
        await ingest_adrs(conn, adr_dir)
        cur = await conn.execute("SELECT status FROM decisions WHERE source='adr'")
        assert (await cur.fetchone())[0] == "Superseded"


async def test_an_adr_refresh_that_fails_partway_keeps_the_previous_set(db: Path, tmp_path: Path):
    """A crafted ADR that trips an error mid-refresh must not wipe the provenance
    already recorded. Delete and re-insert share one transaction."""
    from unittest.mock import patch

    from mri.fusion import ingest_adrs

    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    for i in range(3):
        (adr_dir / f"ADR-{i:03d}.md").write_text(
            f"# ADR-{i} — X\n\n## Decision\nDo {i}.\n", encoding="utf-8"
        )
    async with get_connection(db) as conn:
        assert await ingest_adrs(conn, adr_dir) == 3

        async def boom(*_a, **_k):
            raise RuntimeError("simulated crash mid-refresh")

        with patch.object(conn, "executemany", boom):
            with pytest.raises(RuntimeError, match="simulated crash"):
                await ingest_adrs(conn, adr_dir)

        cur = await conn.execute("SELECT count(*) FROM decisions WHERE source='adr'")
        assert (await cur.fetchone())[0] == 3, "the previous ADR set must survive a failed refresh"


async def test_a_duplicate_commit_cannot_be_double_inserted_by_a_race(db: Path):
    """The natural-key unique index makes the duplicate impossible at the
    database, so two ingests both believing a commit is new cannot both store
    it."""
    from datetime import datetime, timezone

    from mri.db import fusion_repository as frepo
    from mri.models.fusion import Decision

    d = Decision(
        summary="feat: x", source="commit", source_ref="deadbeef",
        commit_sha="deadbeef" * 5, decided_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        confidence=0.6,
    )
    async with get_connection(db) as conn:
        # Both runs prepared the same commit; only one row results.
        n1 = await frepo.insert_decisions_ignoring_duplicates(conn, [d])
        n2 = await frepo.insert_decisions_ignoring_duplicates(conn, [d])
        assert (n1, n2) == (1, 0)
        cur = await conn.execute("SELECT count(*) FROM decisions WHERE source_ref='deadbeef'")
        assert (await cur.fetchone())[0] == 1


def test_a_symlinked_adr_is_skipped(tmp_path: Path):
    """The ADR directory belongs to a possibly-untrusted repo. A symlink there
    could point at a secret elsewhere on the host, so symlinks are not followed."""
    from mri.fusion.decisions import _read_and_parse_adrs

    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    (adr_dir / "ADR-001.md").write_text("# ADR-001 — Real\n\n## Decision\nOK.\n", encoding="utf-8")
    secret = tmp_path / "secret.md"
    secret.write_text("# Leaked — secret\n\nAWS_KEY=AKIAFAKE\n", encoding="utf-8")
    try:
        (adr_dir / "ADR-evil.md").symlink_to(secret)
    except OSError:
        pytest.skip("cannot create symlinks on this host without privilege")

    parsed = _read_and_parse_adrs(adr_dir)
    summaries = [p.summary for _, p in parsed]
    assert "ADR-001 — Real" in summaries
    assert all("Leaked" not in s for s in summaries), "a symlinked ADR must not be followed"


def test_an_oversized_adr_is_skipped(tmp_path: Path):
    from mri.fusion.decisions import MAX_ADR_BYTES, _read_and_parse_adrs

    adr_dir = tmp_path / "adr"
    adr_dir.mkdir()
    (adr_dir / "ADR-big.md").write_text("# Big\n\n" + "x" * (MAX_ADR_BYTES + 10), encoding="utf-8")
    (adr_dir / "ADR-ok.md").write_text("# ADR-ok — Fine\n\n## Decision\nOK.\n", encoding="utf-8")
    parsed = _read_and_parse_adrs(adr_dir)
    assert [p.summary for _, p in parsed] == ["ADR-ok — Fine"]


async def test_ingest_the_real_repo_adrs(db: Path):
    """A regression test against this repo's own ADRs — the manual "verified on
    this repo" check that missed the header-date and title-only bugs is now
    automated."""
    from mri.fusion import ingest_adrs

    if not _REPO_ADR_DIR_EXISTS:
        pytest.skip("run from the repo root")
    adr_dir = Path("docs/adr")
    async with get_connection(db) as conn:
        count = await ingest_adrs(conn, adr_dir)
        assert count >= 8, "every real ADR should be recorded"
        # None of them should have scavenged a body date or an empty rationale.
        cur = await conn.execute("SELECT source_ref, rationale FROM decisions WHERE source='adr'")
        for ref, rationale in await cur.fetchall():
            assert rationale, f"{ref} lost its rationale"


# ---------------------------------------------------------------------------
# 7.1 decision -> file linkage
# ---------------------------------------------------------------------------


async def test_decisions_affecting_file_unions_column_and_link(db: Path):
    """A file's decisions come from an ADR that names it (the file_path column)
    and from a commit that changed it (the decision_files link) — the union is
    what the per-file view needs."""
    from mri.models.fusion import Decision

    async with get_connection(db) as conn:
        pid = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('p','/p')")).lastrowid)
        await conn.commit()
        await repo.insert_decision(conn, Decision(
            summary="use SQLite", source="adr", source_ref="ADR-1.md",
            project_id=pid, file_path="src/db.py",
        ))
        commit = await repo.insert_decision(conn, Decision(
            summary="refactor db layer", source="commit", source_ref="abc123",
            project_id=pid, commit_sha="abc123",
        ))
        await repo.link_decision_files(conn, commit.id, pid, ["src/db.py", "src/other.py"])

        found = {d.summary for d in await repo.decisions_affecting_file(conn, "src/db.py", project_id=pid)}
    assert found == {"use SQLite", "refactor db layer"}, "both the ADR (column) and the commit (link)"


async def test_link_is_idempotent_and_project_scoped(db: Path):
    from mri.models.fusion import Decision

    async with get_connection(db) as conn:
        a = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('a','/a')")).lastrowid)
        b = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('b','/b')")).lastrowid)
        await conn.commit()
        d = await repo.insert_decision(conn, Decision(
            summary="x", source="commit", source_ref="s", project_id=a, commit_sha="s"))
        await repo.link_decision_files(conn, d.id, a, ["src/x.py"])
        await repo.link_decision_files(conn, d.id, a, ["src/x.py"])  # idempotent
        cur = await conn.execute("SELECT count(*) FROM decision_files")
        assert (await cur.fetchone())[0] == 1, "re-linking the same file is a no-op"
        # project B does not see A's link
        assert await repo.decisions_affecting_file(conn, "src/x.py", project_id=b) == []


async def test_ingest_commits_links_each_commits_changed_files(db: Path):
    """After commit ingest, a file changed by a commit resolves to that commit's
    decision through the link table."""
    import subprocess
    import tempfile

    import git

    from mri.fusion import ingest_commits

    d = Path(tempfile.mkdtemp())

    def gitc(*a):
        subprocess.run(["git", *a], cwd=d, capture_output=True)

    gitc("init", "-q")
    gitc("config", "user.email", "t@t")
    gitc("config", "user.name", "t")
    (d / "a.py").write_text("x\n", encoding="utf-8")
    gitc("add", "-A")
    gitc("commit", "-qm", "add a.py")

    async with get_connection(db) as conn:
        pid = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('p', ?)", (str(d),))).lastrowid)
        await conn.commit()
        await ingest_commits(conn, git.Repo(d), project_id=pid)
        decisions = await repo.decisions_affecting_file(conn, "a.py", project_id=pid)
    assert [x.summary for x in decisions] == ["add a.py"], "the commit that changed a.py reaches it"


async def test_each_commit_links_only_its_own_files(db: Path):
    """Multi-commit: a sha->files inversion bug (last commit's files on every
    decision, or the wrong commit's files) would be caught here."""
    import subprocess
    import tempfile

    import git

    from mri.fusion import ingest_commits

    d = Path(tempfile.mkdtemp())

    def gitc(*a):
        subprocess.run(["git", *a], cwd=d, capture_output=True)

    gitc("init", "-q")
    gitc("config", "user.email", "t@t")
    gitc("config", "user.name", "t")
    (d / "a.py").write_text("a\n", encoding="utf-8")
    gitc("add", "-A")
    gitc("commit", "-qm", "add a")
    (d / "b.py").write_text("b\n", encoding="utf-8")
    gitc("add", "-A")
    gitc("commit", "-qm", "add b")

    async with get_connection(db) as conn:
        pid = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('p', ?)", (str(d),))).lastrowid)
        await conn.commit()
        await ingest_commits(conn, git.Repo(d), project_id=pid)
        by_a = {x.summary for x in await repo.decisions_affecting_file(conn, "a.py", project_id=pid)}
        by_b = {x.summary for x in await repo.decisions_affecting_file(conn, "b.py", project_id=pid)}
    assert by_a == {"add a"}, "a.py links only to the commit that added it"
    assert by_b == {"add b"}, "b.py links only to the commit that added it"


async def test_reingest_does_not_relink_everything(db: Path):
    """The linkage is scoped to this call's commits; a no-op re-ingest must not
    re-link every decision ever stored (the audit measured that redundant cost)."""
    import subprocess
    import tempfile
    from unittest.mock import patch

    import git

    import mri.db.fusion_repository as frepo
    from mri.fusion import ingest_commits

    d = Path(tempfile.mkdtemp())

    def gitc(*a):
        subprocess.run(["git", *a], cwd=d, capture_output=True)

    gitc("init", "-q")
    gitc("config", "user.email", "t@t")
    gitc("config", "user.name", "t")
    (d / "a.py").write_text("a\n", encoding="utf-8")
    gitc("add", "-A")
    gitc("commit", "-qm", "add a")

    async with get_connection(db) as conn:
        pid = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('p', ?)", (str(d),))).lastrowid)
        await conn.commit()
        await ingest_commits(conn, git.Repo(d), project_id=pid)  # first: links a.py

        calls = {"n": 0}
        real = frepo.link_decision_files

        async def counting(*args, **kwargs):
            calls["n"] += 1
            return await real(*args, **kwargs)

        with patch.object(frepo, "link_decision_files", counting):
            await ingest_commits(conn, git.Repo(d), project_id=pid)  # re-ingest, nothing new
    assert calls["n"] == 0, "a re-ingest that inserted no new commit links nothing"
