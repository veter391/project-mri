"""Session-to-commit correlation (block 5.2).

The rule under test: a write touch on a file is linked to the earliest commit
that changed that file at or after the touch's time — the commit that first
materialised the edit. A touch with no later commit changing its file stays
unlinked, because that edit is not committed yet. This is the fact block 6.2's
line-shares are built on, so what it refuses to claim matters as much as what it
links.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from mri.db import fusion_repository as repo
from mri.db.migrator import migrate
from mri.db.repository import get_connection
from mri.fusion import correlate_touches_to_commits
from mri.fusion.correlation import file_commit_history
from mri.models.fusion import Session, SessionFileTouch

_SEP = "\x1f"
_MARK = "\x01"


class _FakeGit:
    """Emits the exact `git log -z --pretty=format:\\x01%H\\x1f%aI --name-only`
    shape the correlator parses: raw (unquoted) paths, NUL-separated fields.
    Input is chronological (oldest first); git log is newest-first, so it is
    reversed here to match."""

    def __init__(self, commits: list[tuple[str, str, list[str]]]):
        self._commits = list(reversed(commits))

    def log(self, *args: str) -> str:  # noqa: ARG002 - signature mirrors GitPython
        if args and args[-1].startswith("-"):
            raise ValueError(f"invalid revision {args[-1]!r}")  # mirror _validate_branch
        fields: list[str] = []
        for sha, iso, files in self._commits:
            first = files[0] if files else ""
            fields.append(f"{_MARK}{sha}{_SEP}{iso}\n{first}")
            fields.extend(files[1:])
        return "\x00".join(fields) + "\x00"


class _FakeRepo:
    def __init__(self, commits):
        self.git = _FakeGit(commits)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "corr.db"
    migrate(path)
    return path


def _dt(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 5, day, hour, tzinfo=timezone.utc)


async def _project(conn, path: str = "/repo") -> int:
    pid = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('p', ?)", (path,))).lastrowid)
    await conn.commit()
    return pid


async def _session(conn, pid: int, external_id: str = "s1") -> int:
    s = await repo.upsert_session(
        conn, Session(source="claude_code", external_id=external_id, project_id=pid)
    )
    assert s.id is not None
    return s.id


async def _touch(conn, sid, pid, path, when, kind="write"):
    await repo.insert_session_file_touch(
        conn,
        SessionFileTouch(
            session_id=sid, project_id=pid, file_path=path, touch_kind=kind,
            confidence=0.9, occurred_at=when,
        ),
    )


# ---------------------------------------------------------------------------
# The parser
# ---------------------------------------------------------------------------


def test_history_is_grouped_by_file_ascending_by_time():
    repo_obj = _FakeRepo([
        ("aaa", "2026-05-01T12:00:00+00:00", ["src/a.py"]),
        ("bbb", "2026-05-05T12:00:00+00:00", ["src/a.py", "src/b.py"]),
    ])
    hist = file_commit_history(repo_obj)
    assert [s for _, s in hist["src/a.py"]] == ["aaa", "bbb"], "ascending by author time"
    assert [s for _, s in hist["src/b.py"]] == ["bbb"]


# ---------------------------------------------------------------------------
# The matching rule
# ---------------------------------------------------------------------------


async def test_touch_links_to_the_first_commit_after_it(db: Path):
    """Two commits changed the file; the touch is linked to the earliest one at
    or after the touch time, not the latest."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        sid = await _session(conn, pid)
        await _touch(conn, sid, pid, "src/a.py", _dt(3))  # between the two commits
        git = _FakeRepo([
            ("early", "2026-05-01T12:00:00+00:00", ["src/a.py"]),  # before the touch
            ("materialises", "2026-05-04T12:00:00+00:00", ["src/a.py"]),  # first after
            ("later", "2026-05-09T12:00:00+00:00", ["src/a.py"]),
        ])
        res = await correlate_touches_to_commits(conn, git, project_id=pid)
        assert res.linked == 1
        touches = await repo.touches_for_file(conn, "src/a.py", project_id=pid)
    assert touches[0].commit_sha == "materialises", "the commit that first carried the edit"


async def test_a_touch_at_the_exact_commit_time_links_to_that_commit(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        sid = await _session(conn, pid)
        await _touch(conn, sid, pid, "src/a.py", _dt(4))
        git = _FakeRepo([("c", "2026-05-04T12:00:00+00:00", ["src/a.py"])])
        await correlate_touches_to_commits(conn, git, project_id=pid)
        touches = await repo.touches_for_file(conn, "src/a.py", project_id=pid)
    assert touches[0].commit_sha == "c", "at-or-after includes the exact instant"


async def test_an_edit_not_yet_committed_stays_unlinked(db: Path):
    """A touch after the last commit changing its file is uncommitted work — a
    real state, left unlinked rather than forced onto an earlier commit."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        sid = await _session(conn, pid)
        await _touch(conn, sid, pid, "src/a.py", _dt(10))  # after the only commit
        git = _FakeRepo([("old", "2026-05-01T12:00:00+00:00", ["src/a.py"])])
        res = await correlate_touches_to_commits(conn, git, project_id=pid)
        assert (res.linked, res.uncommitted) == (0, 1)
        touches = await repo.touches_for_file(conn, "src/a.py", project_id=pid)
    assert touches[0].commit_sha is None


async def test_a_touch_on_a_file_git_never_recorded_stays_unlinked(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        sid = await _session(conn, pid)
        await _touch(conn, sid, pid, "scratch/tmp.py", _dt(3))
        git = _FakeRepo([("c", "2026-05-04T12:00:00+00:00", ["src/a.py"])])
        res = await correlate_touches_to_commits(conn, git, project_id=pid)
    assert (res.linked, res.uncommitted) == (0, 1)


async def test_reads_are_not_correlated(db: Path):
    """A read is not authorship; only write/create/delete touches correlate."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        sid = await _session(conn, pid)
        await _touch(conn, sid, pid, "src/a.py", _dt(3), kind="read")
        git = _FakeRepo([("c", "2026-05-04T12:00:00+00:00", ["src/a.py"])])
        res = await correlate_touches_to_commits(conn, git, project_id=pid)
        touches = await repo.touches_for_file(conn, "src/a.py", project_id=pid)
    assert res.linked == 0
    assert touches[0].commit_sha is None, "a read is never linked to a commit as authorship"


async def test_correlation_is_idempotent(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        sid = await _session(conn, pid)
        await _touch(conn, sid, pid, "src/a.py", _dt(3))
        git = _FakeRepo([("c", "2026-05-04T12:00:00+00:00", ["src/a.py"])])
        first = await correlate_touches_to_commits(conn, git, project_id=pid)
        again = await correlate_touches_to_commits(conn, git, project_id=pid)
    assert (first.linked, again.linked) == (1, 0), "an already-linked touch is not re-linked"


async def test_correlation_is_scoped_to_the_project(db: Path):
    """Two projects, same file path, same commit history object: each project's
    touches link only against its own, and one project's run leaves the other's
    touches untouched."""
    async with get_connection(db) as conn:
        a = await _project(conn, "/a")
        b = await _project(conn, "/b")
        sa = await _session(conn, a, "sa")
        sb = await _session(conn, b, "sb")
        await _touch(conn, sa, a, "src/a.py", _dt(3))
        await _touch(conn, sb, b, "src/a.py", _dt(3))
        git = _FakeRepo([("c", "2026-05-04T12:00:00+00:00", ["src/a.py"])])

        res_a = await correlate_touches_to_commits(conn, git, project_id=a)
        assert res_a.linked == 1
        # project B's touch is still unlinked until B's own run.
        b_touch = (await repo.touches_for_file(conn, "src/a.py", project_id=b))[0]
        assert b_touch.commit_sha is None, "correlating A must not touch B's rows"

        res_b = await correlate_touches_to_commits(conn, git, project_id=b)
    assert res_b.linked == 1


async def test_a_commit_gains_all_earlier_touches_of_its_files(db: Path):
    """Several touches on a file before the same commit all link to it — the
    commit carried all of them."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        sid = await _session(conn, pid)
        await _touch(conn, sid, pid, "src/a.py", _dt(2))
        await _touch(conn, sid, pid, "src/a.py", _dt(3))
        git = _FakeRepo([("c", "2026-05-05T12:00:00+00:00", ["src/a.py"])])
        res = await correlate_touches_to_commits(conn, git, project_id=pid)
        touches = await repo.touches_for_file(conn, "src/a.py", project_id=pid)
    assert res.linked == 2
    assert {t.commit_sha for t in touches} == {"c"}


# ---------------------------------------------------------------------------
# What the 5.2 audits found
# ---------------------------------------------------------------------------


async def test_a_non_ascii_filename_correlates(db: Path):
    """git's default core.quotepath escaped non-ASCII names, so a touch on
    'café.py' never matched the escaped log key and fell uncommitted forever.
    The -z parser reads the raw path, so it links."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        sid = await _session(conn, pid)
        await _touch(conn, sid, pid, "src/café.py", _dt(3))
        git = _FakeRepo([("c", "2026-05-04T12:00:00+00:00", ["src/café.py"])])
        res = await correlate_touches_to_commits(conn, git, project_id=pid)
        touches = await repo.touches_for_file(conn, "src/café.py", project_id=pid)
    assert res.linked == 1
    assert touches[0].commit_sha == "c"


async def test_a_file_with_multiple_files_per_commit_parses(db: Path):
    """The -z parser must split several files in one commit correctly."""
    repo_obj = _FakeRepo([("c", "2026-05-01T12:00:00+00:00", ["a.py", "b.py", "dir/c.py"])])
    hist = file_commit_history(repo_obj)
    assert set(hist) == {"a.py", "b.py", "dir/c.py"}


async def test_equal_timestamp_commits_pick_the_earliest_committed(db: Path):
    """Two commits change the file at the identical author second. The link must
    be the earlier-committed one — the commit that first materialised the edit,
    not a later commit that happens to share the timestamp."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        sid = await _session(conn, pid)
        await _touch(conn, sid, pid, "src/a.py", _dt(4))
        # chronological order: 'earliest' committed before 'later', same author time.
        git = _FakeRepo([
            ("earliest", "2026-05-04T12:00:00+00:00", ["src/a.py"]),
            ("later", "2026-05-04T12:00:00+00:00", ["src/a.py"]),
        ])
        await correlate_touches_to_commits(conn, git, project_id=pid)
        touches = await repo.touches_for_file(conn, "src/a.py", project_id=pid)
    assert touches[0].commit_sha == "earliest", "the earliest-committed of a tie, not a later one"


def test_a_branch_that_looks_like_a_flag_is_refused():
    """`git log` has no `--` guard for its revision position; a branch value that
    starts with `-` would be read as an option. Refused before it can be."""
    from mri.fusion.correlation import file_commit_history

    with pytest.raises(ValueError, match="invalid branch"):
        file_commit_history(_FakeRepo([]), branch="--output=/tmp/pwn")


def test_file_commit_history_respects_max_count():
    """A bound on the walk keeps a huge or hostile history from an unbounded read.
    The -z fake honours -n so the parser sees only the capped commits."""
    from mri.fusion.correlation import file_commit_history

    class _CappingGit:
        def __init__(self, commits):
            self._commits = list(reversed(commits))

        def log(self, *args):
            n = None
            for a in args:
                if a.startswith("-n"):
                    n = int(a[2:])
            commits = self._commits[:n] if n is not None else self._commits
            fields = []
            for sha, iso, files in commits:
                fields.append(f"{_MARK}{sha}{_SEP}{iso}\n{files[0]}")
                fields.extend(files[1:])
            return "\x00".join(fields) + "\x00"

    class _Repo:
        def __init__(self, commits):
            self.git = _CappingGit(commits)

    commits = [(f"c{i}", f"2026-05-{i + 1:02d}T00:00:00+00:00", ["a.py"]) for i in range(5)]
    full = file_commit_history(_Repo(commits))
    capped = file_commit_history(_Repo(commits), max_count=2)
    assert len(full["a.py"]) == 5
    assert len(capped["a.py"]) == 2, "the walk is bounded by max_count"
