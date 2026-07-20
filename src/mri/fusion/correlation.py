"""Session-to-commit correlation — the linchpin the later layers rest on.

A session's write touch says an agent edited a file at an instant. A commit says
that file's content changed and was recorded. Correlating the two tells us which
commits an agent's work landed in — the fact that turns "the agent touched this
file" into "the agent's edit is in commit abc123", which is what lets authorship
be computed against the file's actual committed lines (block 6.2) rather than
guessed at.

The rule is deliberately the tightest defensible one, and it was measured before
it was written: a write touch on file F at time T is linked to **the earliest
commit that changed F at or after T**. That is the commit that first materialised
the edit — any intervening commit changing F would be picked instead, and a touch
with no later commit changing F is left unlinked, because that edit is not
committed yet. No fixed time window, no fuzzy overlap: the commit history itself
decides.

This is correlation, not proof. The agent edited F and F next changed in this
commit; the human may have altered the edit before committing. The touch keeps
its own sub-1.0 confidence, and nothing here raises it — the link adds *which*
commit, not *more certainty* that the agent authored the line.
"""
from __future__ import annotations

import asyncio
import logging
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import aiosqlite

from mri.db import fusion_repository as repo

logger = logging.getLogger(__name__)

__all__ = ["CorrelationResult", "correlate_touches_to_commits", "file_commit_history"]

#: Field separator inside the git-log format. Unit Separator (0x1f) cannot occur
#: in a sha or an ISO timestamp, so parsing never has to guess.
_SEP = "\x1f"
_MARK = "\x01"  # start-of-record marker, likewise absent from git's own output


@dataclass(slots=True, frozen=True)
class CorrelationResult:
    """What one correlation run did — reported, not summarised away."""

    linked: int = 0
    #: Touches with a time but no later commit changing their file: the edit is
    #: not committed yet. A real state, counted rather than hidden.
    uncommitted: int = 0
    #: Distinct commits an agent's work was linked into.
    commits: set[str] = field(default_factory=set)


def _validate_branch(branch: str) -> str:
    """A branch is a revision, not an option or a pathspec. Reject a value that
    could be read as a git flag before it is ever taken from anything but a
    hardcoded literal — `git log` has no `--` guard for the revision position."""
    if branch.startswith("-"):
        raise ValueError(f"invalid branch/revision {branch!r}")
    return branch


def file_commit_history(git_repo: Any, *, branch: str = "HEAD") -> dict[str, list[tuple[datetime, str]]]:
    """Per file, the commits that changed it, ascending by author time.

    One `git log --name-only` rather than a diff per commit: the latter calls
    into git once for every commit and is the slow path this deliberately avoids.
    Author time (not commit time) is used, because it is when the change was
    written — the moment a touch should line up against.

    `-z` (NUL-terminated) rather than the default line output: git's default
    `core.quotepath` wraps any non-ASCII, backslash or quote in a filename in
    C-style escapes ("caf\\303\\251.py"), which would never match the real
    `file_path` a touch carries — every accented/CJK/emoji filename would fall
    silently uncommitted. `-z` emits the raw path and sidesteps quoting entirely.

    Ties: two commits changing the same file at the identical author second are
    ordered earliest-committed first, so the first-at-or-after link picks the
    commit that actually materialised the edit rather than a later one. git log
    is newest-first, so the earlier-committed of a tie has the higher stream
    index — the sort key uses `-index` to bring it first.
    """
    raw = git_repo.git.log(
        f"--pretty=format:{_MARK}%H{_SEP}%aI", "--name-only", "--no-renames", "-z",
        _validate_branch(branch),
    )
    history: dict[str, list[tuple[datetime, int, str]]] = {}
    sha = ""
    when: datetime | None = None
    index = 0
    # -z separates every field — the commit header (which ends at the newline
    # before its first file) and each file path — with NUL. A field that carries
    # the record marker begins a commit and also holds that commit's first file
    # after the newline; every other non-empty field is a further file.
    for field_ in raw.split("\x00"):
        if not field_:
            continue
        if field_.startswith(_MARK):
            header, _, first_file = field_.partition("\n")
            body = header[len(_MARK):]
            sha, _, iso = body.partition(_SEP)
            index += 1
            try:
                when = datetime.fromisoformat(iso)
            except ValueError:  # pragma: no cover - git always emits a valid %aI
                when = None
            path = first_file
        else:
            path = field_
        if not path or when is None:
            continue
        history.setdefault(path, []).append((when, index, sha))

    # Ascending by author time; for a tie, higher stream index (earlier commit)
    # first. Drop the index from the returned pairs.
    out: dict[str, list[tuple[datetime, str]]] = {}
    for path, commits in history.items():
        commits.sort(key=lambda c: (c[0], -c[1]))
        out[path] = [(when_, sha_) for when_, _, sha_ in commits]
    return out


def _first_commit_at_or_after(
    times: list[datetime], commits: list[tuple[datetime, str]], moment: datetime
) -> str | None:
    """The earliest commit whose author time is >= moment, or None."""
    idx = bisect_left(times, moment)
    return commits[idx][1] if idx < len(times) else None


async def correlate_touches_to_commits(
    conn: aiosqlite.Connection, git_repo: Any, *, project_id: int, branch: str = "HEAD"
) -> CorrelationResult:
    """Link a project's uncommitted write touches to the commits that materialised
    them. Idempotent: only touches without a commit_sha are considered, so
    re-running after new commits links what has since become committable and
    leaves the rest.
    """
    history = await asyncio.to_thread(file_commit_history, git_repo, branch=branch)
    touches = await repo.uncommitted_write_touches(conn, project_id)

    # Each file's ascending time list is built once, not once per touch on it —
    # a hotspot file can carry thousands of touches and commits, and reconverting
    # per touch measured O(touches x commits). Author times from git are already
    # offset-aware, and a touch's stored time parses to aware UTC, so they compare
    # directly with no re-normalisation.
    times_by_file: dict[str, list[datetime]] = {
        path: [t for t, _ in commits] for path, commits in history.items()
    }

    linked_ids: list[tuple[int, str]] = []
    uncommitted = 0
    commits_hit: set[str] = set()
    for touch in touches:
        commits = history.get(touch.file_path)
        if not commits or touch.occurred_at is None:
            uncommitted += 1
            continue
        sha = _first_commit_at_or_after(times_by_file[touch.file_path], commits, touch.occurred_at)
        if sha is None:
            uncommitted += 1
            continue
        assert touch.id is not None
        linked_ids.append((touch.id, sha))
        commits_hit.add(sha)
    for touch_id, sha in linked_ids:
        await repo.set_touch_commit(conn, touch_id, sha)
    if linked_ids:
        await conn.commit()

    logger.info(
        "correlated %d touch(es) to %d commit(s) for project %d; %d not yet committed",
        len(linked_ids), len(commits_hit), project_id, uncommitted,
    )
    return CorrelationResult(len(linked_ids), uncommitted, commits_hit)
