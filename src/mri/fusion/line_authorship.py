"""Per-file AI/human/unattributed line-shares (block 6.2).

ADR-008 deferred this: with only session touches, a file's *line* authorship
could not be computed honestly, because a session's window spans weeks and says
nothing about which lines survive. Block 5.2 removed that blocker by linking
touches to the specific commits that materialised them, so the share can now be
measured against a file's actual committed lines rather than guessed.

The method, and what each share means:

* `git blame` gives every current line its last-modifying commit — a fact, not
  an estimate. A line whose last-modifying commit is one an agent's write touch
  was linked to (5.2) is **AI-authored**: the line as it stands was last written
  in an agent-attributed commit.
* Everything else is **unattributed**, never **human**. A line we cannot tie to
  an agent commit might be human-written, might predate any session, might come
  from an agent session we never ingested. Absence of AI evidence is not
  evidence of a human, so `share_human` stays 0 — the distinction ADR-008 and
  the schema were built to keep.
* A line an agent wrote but a human later rewrote blames to the human's commit
  and is correctly *not* counted as AI. The share measures authorship of the
  current content, which is the honest question.

Confidence is the correlation's, not blame's: blame is exact, but "this commit
is agent-attributed" rests on the touch->commit link, whose confidence is below
one. So the share's confidence is the strongest write-touch confidence among the
file's agent-attributed commits — 0 when there are none.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import aiosqlite

from mri.models.fusion import AuthorshipShare

logger = logging.getLogger(__name__)

__all__ = ["compute_file_authorship", "persist_file_authorship"]

#: The method name stored on each share, so a reader knows exactly how it was
#: derived and can judge it.
METHOD = "blame_session_commit"


@dataclass(slots=True, frozen=True)
class _AiCommits:
    """The commits an agent's writes were linked to, and how strong that link is."""

    shas: set[str]
    #: sha -> strongest write-touch confidence linked to it.
    confidence: dict[str, float]


async def _ai_attributed_commits(conn: aiosqlite.Connection, project_id: int) -> _AiCommits:
    cursor = await conn.execute(
        "SELECT commit_sha, max(confidence) FROM session_file_touches"
        " WHERE project_id = ? AND commit_sha IS NOT NULL"
        "   AND touch_kind IN ('write', 'create')"
        " GROUP BY commit_sha",
        (project_id,),
    )
    confidence = {str(sha): float(conf) for sha, conf in await cursor.fetchall()}
    return _AiCommits(set(confidence), confidence)


def _blame_share(git_repo: Any, file_path: str, ai: _AiCommits) -> AuthorshipShare | None:
    """Blame one file and split its current lines into AI vs unattributed.

    None when the file cannot be blamed — it does not exist at HEAD, or is binary.
    That is an honest absence. It is logged, so an operator can tell a legitimate
    omission from a real failure rather than reading every gap as "no AI here":
    a bad ref or a broken git process is a different thing from a deleted file,
    and only git-command failures are swallowed — anything else propagates.
    """
    import git as _git

    try:
        blame = git_repo.blame("HEAD", file_path)
    except _git.GitCommandError as exc:
        logger.debug("cannot blame %s (absent at HEAD or binary): %s", file_path, exc)
        return None
    if not blame:
        logger.debug("blame of %s returned nothing; omitting", file_path)
        return None

    total = 0
    ai_lines = 0
    strongest = 0.0
    for commit, lines in blame:
        n = len(lines)
        total += n
        if commit.hexsha in ai.shas:
            ai_lines += n
            strongest = max(strongest, ai.confidence.get(commit.hexsha, 0.0))
    if total == 0:
        return None

    share_ai = round(ai_lines / total * 100.0, 2)
    return AuthorshipShare(
        file_path=file_path,
        share_ai=share_ai,
        share_human=0.0,  # never claimed from this evidence
        share_unattributed=round(100.0 - share_ai, 2),
        method=METHOD,
        confidence=strongest,
    )


async def compute_file_authorship(
    conn: aiosqlite.Connection, git_repo: Any, file_paths: list[str], *, project_id: int
) -> list[AuthorshipShare]:
    """Compute an AI/human/unattributed line-share for each blameable file.

    Files that cannot be blamed are omitted (absence, not a made-up row). Blame
    is blocking per-file git work, so it runs off the event loop; the file list
    is the caller's (typically the scan's hotspots), which bounds the cost.
    """
    ai = await _ai_attributed_commits(conn, project_id)
    shares = await asyncio.to_thread(_compute_blocking, git_repo, file_paths, ai, project_id)
    logger.info(
        "computed authorship for %d/%d file(s) in project %d",
        len(shares), len(file_paths), project_id,
    )
    return shares


def _compute_blocking(
    git_repo: Any, file_paths: list[str], ai: _AiCommits, project_id: int
) -> list[AuthorshipShare]:
    out: list[AuthorshipShare] = []
    for path in file_paths:
        share = _blame_share(git_repo, path, ai)
        if share is not None:
            out.append(share.model_copy(update={"project_id": project_id}))
    return out


async def persist_file_authorship(
    conn: aiosqlite.Connection, shares: list[AuthorshipShare], *, project_id: int
) -> int:
    """Store computed shares in one transaction, replacing any previous
    blame-derived share for the same file so a recompute does not stack stale
    rows. Only this method's rows are replaced; a share from another method is
    left alone. One transaction, so a mid-batch failure leaves the previous set
    whole rather than half-replaced.
    """
    from mri.db.fusion_repository import _iso

    if not shares:
        return 0
    try:
        await conn.execute("BEGIN")
        for share in shares:
            await conn.execute(
                "DELETE FROM authorship_shares"
                " WHERE project_id = ? AND file_path = ? AND method = ?",
                (project_id, share.file_path, METHOD),
            )
        await conn.executemany(
            "INSERT INTO authorship_shares"
            " (project_id, file_path, commit_sha, share_ai, share_human, share_unattributed,"
            "  method, confidence, computed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (project_id, s.file_path, s.commit_sha, s.share_ai, s.share_human,
                 s.share_unattributed, s.method, s.confidence, _iso(s.computed_at))
                for s in shares
            ],
        )
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    return len(shares)
