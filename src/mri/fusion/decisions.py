"""Decision provenance — the recoverable "why" behind the code.

Two sources produce decisions, and the difference between them is the whole
point of the honesty rule this layer enforces:

* An **ADR** is a decision written down on purpose. It has a clear what and a
  clear why, and it is the strongest kind of provenance this project has.
* A **commit** has a clear what — its subject line — and a why only if the
  author wrote a body. When there is no body, the why is not recoverable, and
  this layer records `rationale = None` rather than inventing one or copying the
  subject into the rationale to look complete. Fabricating a rationale is the
  exact failure a provenance record exists to prevent.

Nothing here promotes a guess to a fact. A commit's stated reason is the
author's claim, recorded as such at a confidence below one; an ADR is a
deliberate record, recorded higher but still never at certainty, because a
record can be out of date.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from mri.db import fusion_repository as repo
from mri.models.fusion import Decision

__all__ = [
    "ingest_adrs",
    "ingest_commits",
    "parse_adr",
]

#: An ADR is a deliberate decision record — the strongest provenance we have —
#: but a record can be stale, so never certainty.
ADR_CONFIDENCE = 0.95
#: A commit whose author wrote a body stated a reason. It is their claim, not a
#: verified fact.
COMMIT_WITH_RATIONALE_CONFIDENCE = 0.6
#: A commit with only a subject has a clear what and an unrecoverable why.
COMMIT_SUBJECT_ONLY_CONFIDENCE = 0.3

_ADR_TITLE = re.compile(r"^#\s+(.*\S)\s*$", re.MULTILINE)
_ADR_STATUS = re.compile(r"\*\*Status:\*\*\s*([^\n·|]+)", re.IGNORECASE)
_ADR_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _parse_date(raw: str) -> datetime | None:
    match = _ADR_DATE.search(raw)
    if not match:
        return None
    try:
        return datetime.fromisoformat(match.group(1))
    except ValueError:
        return None


@dataclass(slots=True, frozen=True)
class ParsedAdr:
    summary: str
    rationale: str
    status: str
    decided_at: datetime | None


def parse_adr(text: str) -> ParsedAdr | None:
    """Pull a decision out of an ADR's markdown.

    The summary is the title; the rationale is the body under it, which is where
    an ADR does its actual work. Returns None for a file with no title — that is
    not an ADR, and guessing a summary from a filename would be inventing one.
    """
    title_match = _ADR_TITLE.search(text)
    if title_match is None:
        return None
    summary = title_match.group(1)
    # The rationale is everything after the title line. An ADR's Context and
    # Decision sections are its reasoning; keeping the whole body rather than a
    # slice avoids deciding, per file, which heading holds "the" reason.
    body = text[title_match.end():].strip()
    status_match = _ADR_STATUS.search(text)
    status = status_match.group(1).strip() if status_match else "unknown"
    return ParsedAdr(
        summary=summary,
        rationale=body,
        status=status,
        decided_at=_parse_date(text),
    )


async def ingest_adrs(conn: aiosqlite.Connection, adr_dir: Path) -> int:
    """Record every ADR in a directory as a decision.

    ADRs are re-read in full on each run: they are few, they are edited (a
    decision gets superseded, a status changes), and a stale copy in the table
    would be its own small lie. The previous ADR-sourced rows are cleared first
    so an ADR that was renamed or deleted does not linger.
    """
    # Reading the directory is blocking filesystem work; the API serves on this
    # loop, so it happens off it. The parse is pure, so it goes in the thread too.
    parsed_adrs = await asyncio.to_thread(_read_and_parse_adrs, adr_dir)
    if parsed_adrs is None:
        return 0

    await conn.execute("DELETE FROM decisions WHERE source = 'adr'")
    await conn.commit()

    for name, parsed in parsed_adrs:
        await repo.insert_decision(
            conn,
            Decision(
                summary=parsed.summary,
                rationale=parsed.rationale,
                source="adr",
                source_ref=name,
                decided_at=parsed.decided_at,
                confidence=ADR_CONFIDENCE,
            ),
        )
    return len(parsed_adrs)


def _read_and_parse_adrs(adr_dir: Path) -> list[tuple[str, ParsedAdr]] | None:
    """Read and parse every ADR in a directory. None if the directory is absent."""
    if not adr_dir.is_dir():
        return None
    out: list[tuple[str, ParsedAdr]] = []
    for path in sorted(adr_dir.glob("*.md")):
        if path.name.upper() == "README.md".upper():
            continue  # the index is not a decision
        parsed = parse_adr(path.read_text(encoding="utf-8"))
        if parsed is not None:
            out.append((path.name, parsed))
    return out


def _commit_decision(commit: Any) -> Decision:
    message = str(commit.message)
    parts = message.split("\n", 1)
    summary = parts[0].strip()
    body = parts[1].strip() if len(parts) > 1 else ""
    return Decision(
        summary=summary or "(no subject)",
        # No body means no recoverable why. It stays absent — the subject is the
        # what, and copying it here would dress a missing rationale as a present
        # one.
        rationale=body or None,
        source="commit",
        source_ref=str(commit.hexsha)[:12],
        commit_sha=str(commit.hexsha),
        decided_at=commit.authored_datetime,
        confidence=(
            COMMIT_WITH_RATIONALE_CONFIDENCE if body else COMMIT_SUBJECT_ONLY_CONFIDENCE
        ),
    )


async def ingest_commits(
    conn: aiosqlite.Connection, git_repo: Any, *, branch: str = "HEAD", max_count: int = 2000
) -> int:
    """Record commits as decisions, skipping any already stored.

    A commit is immutable, so its decision never changes: re-ingest inserts only
    commits whose sha is not already present. `max_count` bounds a first ingest
    of a deep history; subsequent runs are cheap because almost everything is
    already there.
    """
    stored = await _stored_commit_shas(conn)
    count = 0
    for commit in git_repo.iter_commits(branch, max_count=max_count):
        if str(commit.hexsha) in stored:
            continue
        await repo.insert_decision(conn, _commit_decision(commit))
        count += 1
    return count


async def _stored_commit_shas(conn: aiosqlite.Connection) -> set[str]:
    cursor = await conn.execute(
        "SELECT commit_sha FROM decisions WHERE source = 'commit' AND commit_sha IS NOT NULL"
    )
    return {str(row[0]) for row in await cursor.fetchall()}
