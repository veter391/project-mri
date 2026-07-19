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
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from mri.db import fusion_repository as repo
from mri.models.fusion import Decision

logger = logging.getLogger(__name__)

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

#: An ADR directory holds prose decision records, not a document dump. These
#: bounds keep a hostile or accidental repo — one with a hundred thousand tiny
#: files, or a single half-gigabyte one — from turning ingest into a multi-minute
#: blocking hang or an out-of-memory kill. Anything past them is skipped and
#: logged, not silently swallowed.
MAX_ADR_FILES = 2_000
MAX_ADR_BYTES = 2 * 1024 * 1024

_ADR_TITLE = re.compile(r"^#\s+(.*\S)\s*$", re.MULTILINE)
#: Tolerant of the label's real forms: `- **Status:** Accepted`,
#: `**Status:** Accepted · date`, `> Status: **accepted**.`
_ADR_STATUS = re.compile(r"status[:*\s]*\**\s*([A-Za-z][A-Za-z ]*[A-Za-z])", re.IGNORECASE)
_ADR_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
#: The metadata header ends at the first section heading. A date scavenged from
#: a body subsection is not the decision's date, so only the header is searched.
_ADR_HEADER_END = re.compile(r"^##\s", re.MULTILINE)


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
    #: None when the ADR is a title with no body — the why is not recoverable,
    #: exactly as for a bodyless commit, and an empty string would claim a
    #: rationale that is not there.
    rationale: str | None
    #: None when no status line is found, rather than a made-up "unknown".
    status: str | None
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

    # Status and date come only from the metadata header — the text before the
    # first section heading — so a date or the word "status" appearing in the
    # body cannot be mistaken for the decision's own.
    header_end = _ADR_HEADER_END.search(text)
    header = text[: header_end.start()] if header_end else text
    status_match = _ADR_STATUS.search(header)
    return ParsedAdr(
        summary=summary,
        rationale=body or None,
        status=status_match.group(1).strip() if status_match else None,
        decided_at=_parse_date(header),
    )


async def ingest_adrs(
    conn: aiosqlite.Connection, adr_dir: Path, *, project_id: int | None = None
) -> int:
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

    decisions = [
        Decision(
            summary=parsed.summary,
            rationale=parsed.rationale,
            source="adr",
            source_ref=name,
            project_id=project_id,
            decided_at=parsed.decided_at,
            status=parsed.status,
            confidence=ADR_CONFIDENCE,
        )
        for name, parsed in parsed_adrs
    ]
    # One transaction: the previous ADR rows survive untouched if any insert
    # fails, instead of a crafted ADR wiping the provenance it was meant to add.
    # Scoped to the project so one repo's refresh does not wipe another's.
    return await repo.replace_decisions_of_source(conn, "adr", decisions, project_id=project_id)


def _read_and_parse_adrs(adr_dir: Path) -> list[tuple[str, ParsedAdr]] | None:
    """Read and parse every ADR in a directory. None if the directory is absent.

    The ADR directory belongs to a repository that may be untrusted — this tool
    scans arbitrary clones. A symlink there could point at a secret elsewhere on
    the host, so symlinks are skipped and any path resolving outside the
    directory is rejected. File count and size are bounded so a hostile or
    accidental dump cannot turn ingest into a hang or an out-of-memory kill.
    """
    if not adr_dir.is_dir():
        return None
    root = adr_dir.resolve()
    out: list[tuple[str, ParsedAdr]] = []
    seen = 0
    for path in sorted(adr_dir.glob("*.md")):
        if path.name.upper() == "README.md".upper():
            continue  # the index is not a decision
        if path.is_symlink():
            logger.warning("skipping symlinked ADR %s: symlinks are not followed", path.name)
            continue
        try:
            resolved = path.resolve()
            resolved.relative_to(root)  # must stay inside the ADR directory
        except (OSError, ValueError):
            logger.warning("skipping ADR %s: resolves outside %s", path.name, root)
            continue
        if not resolved.is_file():
            continue
        if resolved.stat().st_size > MAX_ADR_BYTES:
            logger.warning("skipping ADR %s: larger than %d bytes", path.name, MAX_ADR_BYTES)
            continue
        seen += 1
        if seen > MAX_ADR_FILES:
            logger.warning("stopping at %d ADR files; the rest are not read", MAX_ADR_FILES)
            break
        parsed = parse_adr(path.read_text(encoding="utf-8", errors="replace"))
        if parsed is not None:
            out.append((path.name, parsed))
        else:
            logger.debug("skipping %s: no ADR title found", path.name)
    return out


def _commit_decision(commit: Any, project_id: int | None = None) -> Decision:
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
        project_id=project_id,
        commit_sha=str(commit.hexsha),
        decided_at=commit.authored_datetime,
        confidence=(
            COMMIT_WITH_RATIONALE_CONFIDENCE if body else COMMIT_SUBJECT_ONLY_CONFIDENCE
        ),
    )


async def ingest_commits(
    conn: aiosqlite.Connection,
    git_repo: Any,
    *,
    branch: str = "HEAD",
    max_count: int = 2000,
    project_id: int | None = None,
) -> int:
    """Record commits as decisions, skipping any already stored.

    A commit is immutable, so its decision never changes. Duplicates are refused
    by the natural-key unique index rather than a read-then-write check, so two
    ingests racing cannot both insert the same commit. Returns the number of
    commits actually newly recorded.

    `max_count` bounds a first ingest of a deep history. If the walk hits that
    bound there may be older commits this run did not reach; that is logged
    rather than passing silently, because a silent cap reads as "we captured
    everything" when we did not.
    """
    decisions = await asyncio.to_thread(_collect_commits, git_repo, branch, max_count, project_id)
    if len(decisions) == max_count:
        logger.info(
            "commit ingest hit the max_count of %d; commits older than that were not walked",
            max_count,
        )
    return await repo.insert_decisions_ignoring_duplicates(conn, decisions)


def _collect_commits(
    git_repo: Any, branch: str, max_count: int, project_id: int | None
) -> list[Decision]:
    """Walk history off the event loop — iterating commits is blocking git I/O."""
    return [
        _commit_decision(c, project_id) for c in git_repo.iter_commits(branch, max_count=max_count)
    ]
