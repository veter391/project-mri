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
    "link_related_decisions",
    "parse_adr",
]

#: An ADR reference in a commit message: "ADR-5", "ADR 005", "adr-42". The
#: number is normalised to an int so leading zeros do not matter.
_ADR_REF = re.compile(r"\bADR[-\s]?0*(\d{1,4})\b", re.IGNORECASE)
#: A commit sha cited in an ADR body: 7-40 hex chars. Only links if it actually
#: prefixes a stored commit sha, so a hex-looking word that is not a real commit
#: produces no link.
_SHA_REF = re.compile(r"\b([0-9a-f]{7,40})\b")
#: The ADR number embedded in an ADR's own source_ref/summary ("ADR-005-...").
_ADR_NUMBER = re.compile(r"ADR[-\s]?0*(\d{1,4})", re.IGNORECASE)

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

#: Commit subjects and ADR titles come from a repository that may be a hostile
#: clone. They are text, not markup or control codes, so control characters,
#: ANSI escapes and Unicode bidi overrides are stripped at ingest — that
#: protects every consumer (terminal, report, JSON) at once and loses no real
#: information. HTML-escaping is still the web surface's job at its render
#: boundary; this is the layer below that, keeping the stored text plain.
_CONTROL = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"   # ANSI CSI escape sequences
    r"|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"  # C0 controls except tab/newline, and DEL
    r"|[‪-‮⁦-⁩]"  # bidi embedding/override controls
)


def _clean(text: str) -> str:
    return _CONTROL.sub("", text)


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
        summary=_clean(summary),
        rationale=_clean(body) or None,
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
    summary = _clean(parts[0].strip())
    body = _clean(parts[1].strip()) if len(parts) > 1 else ""
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
    written = await repo.insert_decisions_ignoring_duplicates(conn, decisions)
    await _link_commit_files(conn, git_repo, branch, project_id, {d.commit_sha for d in decisions})
    return written


async def _link_commit_files(
    conn: aiosqlite.Connection, git_repo: Any, branch: str,
    project_id: int | None, shas: set[str],
) -> None:
    """Link each commit decision to the files that commit changed, so a per-file
    view can reach the decisions behind it. Idempotent — re-linking is ignored.

    Scoped to this call's commits: only the decisions whose sha was collected now
    are linked, so a re-ingest does not re-scan and re-link every decision ever
    stored for the project.

    Merge commits get no file link. `git log --name-only` reports no files for a
    merge, so a merge decision is recorded but not reachable per-file — which is
    the honest reading: a merge combines existing work, it does not author the
    lines, and the commits it merges carry their own links.
    """
    from mri.fusion.correlation import file_commit_history

    wanted = {s for s in shas if s}
    if not wanted:
        return

    history = await asyncio.to_thread(file_commit_history, git_repo, branch=branch)
    files_by_sha: dict[str, list[str]] = {}
    for path, commits in history.items():
        for _, sha in commits:
            if sha in wanted:
                files_by_sha.setdefault(sha, []).append(path)

    for sha, decision_id in (await _decision_ids_for_shas(conn, project_id, wanted)).items():
        await repo.link_decision_files(conn, decision_id, project_id, files_by_sha.get(sha, []))


async def _decision_ids_for_shas(
    conn: aiosqlite.Connection, project_id: int | None, shas: set[str]
) -> dict[str, int]:
    """Map commit sha -> decision id for the commits of this run that are not yet
    linked. Excluding already-linked decisions makes a no-op re-ingest do no
    linking work at all, rather than re-issuing an idempotent write per commit."""
    out: dict[str, int] = {}
    sha_list = list(shas)
    for start in range(0, len(sha_list), 500):
        batch = sha_list[start:start + 500]
        placeholders = ",".join("?" * len(batch))
        cursor = await conn.execute(
            "SELECT commit_sha, id FROM decisions"  # noqa: S608 - placeholders only, values bound
            " WHERE source = 'commit' AND project_id IS ?"
            f" AND commit_sha IN ({placeholders})"
            " AND id NOT IN (SELECT decision_id FROM decision_files)",
            (project_id, *batch),
        )
        out.update({str(sha): int(did) for sha, did in await cursor.fetchall()})
    return out


def _collect_commits(
    git_repo: Any, branch: str, max_count: int, project_id: int | None
) -> list[Decision]:
    """Walk history off the event loop — iterating commits is blocking git I/O."""
    return [
        _commit_decision(c, project_id) for c in git_repo.iter_commits(branch, max_count=max_count)
    ]


async def link_related_decisions(conn: aiosqlite.Connection, *, project_id: int) -> int:
    """Link an ADR and a commit that describe the same decision.

    Only *explicit* cross-references make a link — a commit message naming an ADR
    ("see ADR-005"), or an ADR body naming a commit sha. Fuzzy text similarity is
    deliberately not used: guessing that two decisions are "the same" and merging
    them would fabricate a relationship, and a wrong merge of two real decisions
    is the exact failure this product refuses. The two rows are kept distinct and
    linked, not merged, so each keeps its own rationale and confidence.

    Idempotent — re-running only adds links that are newly derivable.
    """
    cursor = await conn.execute(
        "SELECT id, source, source_ref, summary, rationale, commit_sha FROM decisions"
        " WHERE project_id IS ?",
        (project_id,),
    )
    rows = await cursor.fetchall()

    adr_by_number: dict[int, int] = {}
    commit_by_sha: list[tuple[str, int]] = []
    for did, source, source_ref, _summary, _rationale, commit_sha in rows:
        if source == "adr":
            m = _ADR_NUMBER.search(source_ref or "") or _ADR_NUMBER.search(_summary or "")
            if m:
                adr_by_number[int(m.group(1))] = int(did)
        elif source == "commit" and commit_sha:
            commit_by_sha.append((str(commit_sha), int(did)))

    links = 0
    for did, source, _source_ref, summary, rationale, _commit_sha in rows:
        text = f"{summary or ''}\n{rationale or ''}"
        if source == "commit":
            for m in _ADR_REF.finditer(text):
                adr_id = adr_by_number.get(int(m.group(1)))
                if adr_id is not None and adr_id != did:
                    if await repo.insert_decision_link(conn, int(did), adr_id, project_id, "commit_names_adr"):
                        links += 1
        elif source == "adr":
            cited = {c.lower() for c in _SHA_REF.findall(text.lower())}
            for sha, commit_id in commit_by_sha:
                if commit_id == did:
                    continue
                if any(sha.startswith(ref) or ref.startswith(sha) for ref in cited):
                    if await repo.insert_decision_link(conn, int(did), commit_id, project_id, "adr_names_commit"):
                        links += 1
    return links
