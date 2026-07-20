"""Per-file AI/human/unattributed line-shares (block 6.2).

The honesty ADR-008 was written to protect, now that 5.2 makes the share
computable: shares sum to 100, `human` is never claimed, an unblameable file is
absent rather than fabricated, and a line a human rewrote is not counted as AI.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mri.db import fusion_repository as repo
from mri.db.migrator import migrate
from mri.db.repository import get_connection
from mri.fusion import compute_file_authorship, persist_file_authorship
from mri.models.fusion import Session, SessionFileTouch


class _Commit:
    def __init__(self, sha: str):
        self.hexsha = sha


class _BlameRepo:
    """Returns a controlled blame: {file: [(sha, n_lines), ...]}."""

    def __init__(self, blames: dict[str, list[tuple[str, int]]]):
        self._blames = blames

    def blame(self, rev: str, path: str):  # noqa: ARG002 - mirrors GitPython
        if path not in self._blames:
            import git
            # The real GitPython raises this for a path absent at HEAD.
            raise git.GitCommandError(["blame", rev, "--", path], 128)
        return [(_Commit(sha), ["x"] * n) for sha, n in self._blames[path]]


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "la.db"
    migrate(path)
    return path


async def _project(conn, path: str = "/repo") -> int:
    pid = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('p', ?)", (path,))).lastrowid)
    await conn.commit()
    return pid


async def _ai_touch(conn, pid, sha, file_path="src/a.py", confidence=0.9, kind="write"):
    """A touch already linked to a commit — the post-5.2 state 6.2 reads."""
    s = await repo.upsert_session(conn, Session(source="claude_code", external_id=f"s-{sha}", project_id=pid))
    assert s.id is not None
    touch = SessionFileTouch(
        session_id=s.id, project_id=pid, file_path=file_path, touch_kind=kind, confidence=confidence
    )
    stored = await repo.insert_session_file_touch(conn, touch)
    await repo.set_touch_commit(conn, stored.id, sha)  # type: ignore[arg-type]
    await conn.commit()  # set_touch_commit defers the commit to its bulk caller


async def test_a_fully_ai_written_file_is_100_percent_ai(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _ai_touch(conn, pid, "c1")
        git = _BlameRepo({"src/a.py": [("c1", 40)]})
        shares = await compute_file_authorship(conn, git, ["src/a.py"], project_id=pid)
    s = shares[0]
    assert s.share_ai == 100.0
    assert s.share_unattributed == 0.0
    assert s.share_human == 0.0


async def test_shares_always_sum_to_100_and_human_is_never_claimed(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _ai_touch(conn, pid, "c1")
        # 30 AI lines (c1), 70 lines from a commit no session touched.
        git = _BlameRepo({"src/a.py": [("c1", 30), ("human_or_old", 70)]})
        shares = await compute_file_authorship(conn, git, ["src/a.py"], project_id=pid)
    s = shares[0]
    assert s.share_ai == 30.0
    assert s.share_unattributed == 70.0
    assert s.share_human == 0.0, "absence of AI evidence is unattributed, never human"
    assert s.share_ai + s.share_human + s.share_unattributed == 100.0


async def test_a_file_with_no_ai_commits_is_fully_unattributed(db: Path):
    """We blamed it and found no agent-attributed line — a real 100 unattributed,
    which the schema accepts, not a guess."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        git = _BlameRepo({"src/a.py": [("someone_else", 50)]})
        shares = await compute_file_authorship(conn, git, ["src/a.py"], project_id=pid)
    s = shares[0]
    assert s.share_ai == 0.0
    assert s.share_unattributed == 100.0
    assert s.confidence == 0.0, "no AI lines means no attribution confidence"


async def test_an_unblameable_file_is_omitted_not_fabricated(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _ai_touch(conn, pid, "c1")
        git = _BlameRepo({"src/a.py": [("c1", 10)]})  # b.py absent from the tree
        shares = await compute_file_authorship(conn, git, ["src/a.py", "src/b.py"], project_id=pid)
    assert [s.file_path for s in shares] == ["src/a.py"], "the missing file yields no row"


async def test_confidence_is_the_strongest_touch_of_the_ai_commits(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _ai_touch(conn, pid, "c1", confidence=0.5)
        await _ai_touch(conn, pid, "c2", confidence=0.9)
        git = _BlameRepo({"src/a.py": [("c1", 10), ("c2", 10)]})
        shares = await compute_file_authorship(conn, git, ["src/a.py"], project_id=pid)
    assert shares[0].confidence == 0.9, "the strongest link among the file's AI commits"


async def test_a_read_linked_commit_does_not_count_as_authorship(db: Path):
    """Only write/create touches attribute a commit. A commit an agent only read
    files in is not agent-authored."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _ai_touch(conn, pid, "c1", kind="read")
        git = _BlameRepo({"src/a.py": [("c1", 20)]})
        shares = await compute_file_authorship(conn, git, ["src/a.py"], project_id=pid)
    assert shares[0].share_ai == 0.0


async def test_shares_are_project_scoped(db: Path):
    """Another project's touch on the same commit sha must not attribute lines
    here."""
    async with get_connection(db) as conn:
        a = await _project(conn, "/a")
        b = await _project(conn, "/b")
        await _ai_touch(conn, b, "c1")  # only project B linked this commit
        git = _BlameRepo({"src/a.py": [("c1", 10)]})
        shares_a = await compute_file_authorship(conn, git, ["src/a.py"], project_id=a)
        shares_b = await compute_file_authorship(conn, git, ["src/a.py"], project_id=b)
    assert shares_a[0].share_ai == 0.0, "project A has no evidence for this commit"
    assert shares_b[0].share_ai == 100.0


async def test_persist_replaces_and_does_not_stack(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _ai_touch(conn, pid, "c1")
        git = _BlameRepo({"src/a.py": [("c1", 10)]})
        shares = await compute_file_authorship(conn, git, ["src/a.py"], project_id=pid)
        assert await persist_file_authorship(conn, shares, project_id=pid) == 1
        assert await persist_file_authorship(conn, shares, project_id=pid) == 1
        stored = await repo.authorship_for_file(conn, "src/a.py", project_id=pid)
    assert len(stored) == 1, "a recompute replaces, it does not stack"
    assert stored[0].share_ai == 100.0
    assert stored[0].project_id == pid
