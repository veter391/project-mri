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
from mri.utils import utc_iso

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


def file_commit_history(git_repo: Any, *, branch: str = "HEAD") -> dict[str, list[tuple[datetime, str]]]:
    """Per file, the commits that changed it, ascending by author time.

    One `git log --name-only` rather than a diff per commit: the latter calls
    into git once for every commit and is the slow path this deliberately avoids.
    Author time (not commit time) is used, because it is when the change was
    written — the moment a touch should line up against.
    """
    raw = git_repo.git.log(
        f"--pretty=format:{_MARK}%H{_SEP}%aI", "--name-only", "--no-renames", branch
    )
    history: dict[str, list[tuple[datetime, str]]] = {}
    sha = ""
    when: datetime | None = None
    for line in raw.splitlines():
        if line.startswith(_MARK):
            body = line[len(_MARK):]
            sha, _, iso = body.partition(_SEP)
            try:
                when = datetime.fromisoformat(iso)
            except ValueError:  # pragma: no cover - git always emits a valid %aI
                when = None
            continue
        path = line.strip()
        if not path or when is None:
            continue
        history.setdefault(path, []).append((when, sha))
    # Each file's commits arrive newest-first (git log order); sort ascending so
    # a touch can bisect to the first commit at or after its time.
    for commits in history.values():
        commits.sort(key=lambda c: c[0])
    return history


def _first_commit_at_or_after(
    commits: list[tuple[datetime, str]], moment: datetime
) -> str | None:
    """The earliest commit whose author time is >= moment, or None."""
    times = [c[0] for c in commits]
    idx = bisect_left(times, moment)
    return commits[idx][1] if idx < len(commits) else None


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

    result = CorrelationResult()
    linked_ids: list[tuple[int, str]] = []
    for touch in touches:
        commits = history.get(touch.file_path)
        if not commits or touch.occurred_at is None:
            result = CorrelationResult(result.linked, result.uncommitted + 1, result.commits)
            continue
        # occurred_at is stored UTC-canonical; compare on the same footing.
        moment = datetime.fromisoformat(utc_iso(touch.occurred_at))
        sha = _first_commit_at_or_after(
            [(datetime.fromisoformat(utc_iso(t)), s) for t, s in commits], moment
        )
        if sha is None:
            result = CorrelationResult(result.linked, result.uncommitted + 1, result.commits)
            continue
        assert touch.id is not None
        linked_ids.append((touch.id, sha))
        result.commits.add(sha)

    for touch_id, sha in linked_ids:
        await repo.set_touch_commit(conn, touch_id, sha)
    if linked_ids:
        await conn.commit()

    logger.info(
        "correlated %d touch(es) to %d commit(s) for project %d; %d not yet committed",
        len(linked_ids), len(result.commits), project_id, result.uncommitted,
    )
    return CorrelationResult(len(linked_ids), result.uncommitted, result.commits)
