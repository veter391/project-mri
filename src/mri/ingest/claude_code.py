"""Parse Claude Code session logs.

Written against real logs on disk rather than documentation — the record types,
key names, and counts this module relies on were measured from a 21,750-record
session before a line of it was written. See
`_workspace/research/session-log-formats.md` for the measurements.

The parser's job is to turn a log into claims this product is willing to make.
That means it discards more than it keeps:

* only `user` and `assistant` records become turns. `last-prompt`, `ai-title`,
  `attachment` and friends restate content that already appears elsewhere, and
  counting them would inflate a session's apparent influence;
* a file touch is recorded only when a tool reported operating on that file. A
  tool call whose result was an error did not change anything, and recording it
  would attribute a change that never happened;
* paths outside the repository being scanned are dropped rather than stored
  with a guess about where they belong.

Nothing here parses shell commands looking for filenames. A path inside a Bash
invocation may or may not have been written to, and this product does not
publish numbers it cannot defend.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from mri.timeparse import parse_iso8601

logger = logging.getLogger(__name__)

SOURCE = "claude_code"

#: Records that carry a turn. Everything else in the log is bookkeeping.
TURN_TYPES = {"user", "assistant"}

#: Tools whose input names a file directly, and what a successful call means.
#: `Read` is included because reading a file is evidence a session engaged with
#: it, but it is recorded as a read and never contributes to authorship.
FILE_TOOLS = {"Write": "write", "Edit": "write", "Read": "read"}

#: A tool reported doing the thing. That is strong evidence — much stronger
#: than correlating timestamps against a working tree — but it is still a
#: report, and the file may have been reverted a minute later. Never 1.0.
CONFIDENCE_REPORTED = 0.9

#: The call was issued and no result was recorded. It may have succeeded.
CONFIDENCE_OUTCOME_UNKNOWN = 0.5

#: Longest line the parser will try to decode. A turn is prose and tool
#: arguments; it is not eight megabytes. A single 500 MB line was measured
#: taking the process to a 1.5 GB peak — the raw string, the decoded object and
#: the retained content all alive at once. Past this the line is counted as
#: unreadable, which is what it is: something this parser cannot honestly say
#: it understood.
MAX_LINE_BYTES = 8 * 1024 * 1024


@dataclass(slots=True)
class ParsedTurn:
    seq: int
    role: str
    kind: str
    content: str | None
    content_hash: str
    occurred_at: datetime | None


@dataclass(slots=True)
class ParsedTouch:
    seq: int
    file_path: str
    touch_kind: str
    confidence: float
    occurred_at: datetime | None


@dataclass(slots=True)
class ParsedSession:
    external_id: str
    workspace_path: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    turns: list[ParsedTurn] = field(default_factory=list)
    touches: list[ParsedTouch] = field(default_factory=list)
    #: Lines that were not valid JSON. A live log's last line is routinely a
    #: partial write, so this is normal and small — but it is reported rather
    #: than swallowed, because a large count means the parser is wrong about
    #: the format and every number derived from it is suspect.
    unreadable_lines: int = 0
    #: Tool calls whose result was an error. They changed nothing, so they are
    #: not touches — but the count is reported, because "this session failed
    #: half its edits" is a fact about the session worth having.
    failed_calls: int = 0
    #: Records belonging to a different session that appeared in this file.
    #: Should be zero; a non-zero count means the file is not what we think.
    foreign_records: int = 0
    #: Tool calls reusing an id already awaiting a result. Also should be zero.
    duplicate_call_ids: int = 0


def _parse_time(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return parse_iso8601(raw)
    except ValueError:
        return None


def _content_parts(record: dict) -> list[dict]:
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, list):
        return [p for p in content if isinstance(p, dict)]
    return []


def _fingerprint(record: dict) -> str:
    """A hash identifying what a turn actually did.

    Hashing the prose alone is not enough: two turns can both carry no text
    while calling different tools on different files. A rewritten log would
    then look unchanged at that position, and the edit it now describes would
    be lost — measured, not hypothesised. So the fingerprint covers the whole
    message payload, tool inputs included.

    It stays a hash, so it identifies a turn without retaining what was said.
    """
    import hashlib

    message = record.get("message")
    payload = message.get("content") if isinstance(message, dict) else None
    if payload is None:
        return ""
    try:
        canonical = json.dumps(payload, sort_keys=True, default=str)
    except (TypeError, ValueError):  # pragma: no cover - json handles our shapes
        canonical = repr(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _text_of(record: dict) -> str:
    """Flatten a turn to text, for hashing and optional storage."""
    message = record.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            p.get("text", "") for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        )
    return ""


def _relative_within(raw_path: str, root: Path, cache: dict[str, str | None]) -> str | None:
    """Repo-relative path, or None if the file is not in this repository.

    A session ranges across a machine — other repositories, temp files, the
    user's home. Only what is inside the project being scanned can be attributed
    to it, and a path that is merely similar is not the same path.

    A log mentions the same handful of files hundreds of times, and `resolve()`
    touches the filesystem on every call — measured at 227 s for a million
    records. The answer for a given raw path never changes within one parse, so
    it is computed once.
    """
    if raw_path in cache:
        return cache[raw_path]
    try:
        candidate = Path(raw_path).resolve()
        relative: str | None = candidate.relative_to(root).as_posix()
    except (OSError, ValueError):
        relative = None
    cache[raw_path] = relative
    return relative


def iter_records(log: Path) -> Iterator[tuple[dict, bool]]:
    """Yield (record, ok) per line, streaming.

    Logs reach tens of megabytes; they are never read whole. A line that cannot
    be decoded yields ({}, False) so the caller can count it.

    A log that cannot be opened at all yields nothing. The directory this scans
    is not ours: it can hold a file another process has locked, a cloud-storage
    placeholder, a permission-denied file, or a directory that happens to end in
    `.jsonl`. One of those must not stop every other log from being read.
    """
    try:
        handle = log.open(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("skipping unreadable session log %s: %s", log.name, exc)
        return
    with handle:
        while True:
            try:
                line = handle.readline()
            except OSError as exc:  # the file went away mid-read
                logger.warning("stopped reading %s: %s", log.name, exc)
                return
            if not line:
                return
            if len(line) > MAX_LINE_BYTES:
                yield {}, False
                continue
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                yield {}, False
                continue
            yield (record, True) if isinstance(record, dict) else ({}, False)


def parse_log(log: Path, *, repo_root: Path, store_content: bool = False) -> ParsedSession | None:
    """Parse one session log, keeping only what applies to `repo_root`.

    `store_content` defaults to False: retaining prompt text is opt-in because
    prompts routinely contain pasted credentials. When it is False every turn is
    stored with `content=None` and its hash, which is enough to correlate and
    deduplicate turns without keeping what was said.
    """
    root = repo_root.resolve()
    session: ParsedSession | None = None
    seq = 0
    # tool_use_id -> (seq, file_path, touch_kind, occurred_at), awaiting its result.
    pending: dict[str, tuple[int, str, str, datetime | None]] = {}
    path_cache: dict[str, str | None] = {}

    # Counted before the session exists as well as after: an unreadable line can
    # come before the first valid record, and dropping it there would hide
    # exactly the case where the parser has misread the file from the start.
    unreadable = 0

    for record, ok in iter_records(log):
        if not ok:
            unreadable += 1
            continue

        external_id = record.get("sessionId")
        if session is not None and isinstance(external_id, str) and external_id                 and external_id != session.external_id:
            # One file, one session. A second id means the file was concatenated
            # or corrupted; merging them would attribute one session's work to
            # another, so the records are dropped and counted.
            session.foreign_records += 1
            continue
        if session is None:
            if not isinstance(external_id, str) or not external_id:
                continue
            session = ParsedSession(
                external_id=external_id,
                workspace_path=str(record.get("cwd") or ""),
            )
        elif not session.workspace_path:
            # `cwd` is absent from a fifth of the records, including — in real
            # logs — the first one carrying a sessionId. Take it from the first
            # record that actually has it rather than recording an empty path.
            session.workspace_path = str(record.get("cwd") or "")

        occurred_at = _parse_time(record.get("timestamp"))
        if occurred_at is not None:
            if session.started_at is None or occurred_at < session.started_at:
                session.started_at = occurred_at
            if session.ended_at is None or occurred_at > session.ended_at:
                session.ended_at = occurred_at

        # --- results first: they decide whether an earlier call counts ---
        for part in _content_parts(record):
            if part.get("type") != "tool_result":
                continue
            use_id = part.get("tool_use_id")
            if not isinstance(use_id, str):
                continue
            if part.get("is_error"):
                if pending.pop(use_id, None) is not None:
                    session.failed_calls += 1
                continue
            waiting = pending.pop(use_id, None)
            if waiting is not None:
                touch_seq, file_path, touch_kind, touch_time = waiting
                session.touches.append(ParsedTouch(
                    seq=touch_seq, file_path=file_path, touch_kind=touch_kind,
                    confidence=CONFIDENCE_REPORTED, occurred_at=touch_time,
                ))

        if record.get("type") not in TURN_TYPES:
            continue

        seq += 1
        text = _text_of(record)
        session.turns.append(ParsedTurn(
            seq=seq,
            role="assistant" if record.get("type") == "assistant" else "user",
            kind="message",
            content=text if (store_content and text) else None,
            content_hash=_fingerprint(record),
            occurred_at=occurred_at,
        ))

        for part in _content_parts(record):
            if part.get("type") != "tool_use":
                continue
            tool_kind = FILE_TOOLS.get(str(part.get("name")))
            if tool_kind is None:
                continue
            raw_path = (part.get("input") or {}).get("file_path")
            if not isinstance(raw_path, str):
                continue
            relative = _relative_within(raw_path, root, path_cache)
            if relative is None:
                continue  # another repository, a temp file, somewhere else
            use_id = part.get("id")
            if isinstance(use_id, str):
                if use_id in pending:
                    # Reusing an id would silently overwrite the earlier call.
                    # Keep both: the first is recorded now, at unknown outcome.
                    earlier_seq, earlier_path, earlier_kind, earlier_time = pending[use_id]
                    session.duplicate_call_ids += 1
                    session.touches.append(ParsedTouch(
                        seq=earlier_seq, file_path=earlier_path, touch_kind=earlier_kind,
                        confidence=CONFIDENCE_OUTCOME_UNKNOWN, occurred_at=earlier_time,
                    ))
                pending[use_id] = (seq, relative, tool_kind, occurred_at)
            else:
                session.touches.append(ParsedTouch(
                    seq=seq, file_path=relative, touch_kind=tool_kind,
                    confidence=CONFIDENCE_OUTCOME_UNKNOWN, occurred_at=occurred_at,
                ))

    if session is None:
        return None
    session.unreadable_lines = unreadable

    # Calls that never got a result. The tool was asked to do it; whether it did
    # is unknown, and the confidence says so rather than the record being dropped.
    for touch_seq, file_path, touch_kind, touch_time in pending.values():
        session.touches.append(ParsedTouch(
            seq=touch_seq, file_path=file_path, touch_kind=touch_kind,
            confidence=CONFIDENCE_OUTCOME_UNKNOWN, occurred_at=touch_time,
        ))

    if session.unreadable_lines:
        logger.info(
            "%s: %d unreadable line(s) in %s — normal for a live log's final line",
            SOURCE, session.unreadable_lines, log.name,
        )
    return session


def logs_for_workspace(workspace: Path, *, home: Path | None = None) -> list[Path]:
    """Session logs recorded for this workspace.

    Claude Code stores logs under a slugified copy of the working directory, but
    the slug is an implementation detail of another program. Rather than
    reproducing its rules, every candidate log is opened and its own recorded
    `cwd` is compared with the workspace — the log states where it ran, so ask
    it instead of guessing from a directory name.
    """
    base = (home or Path.home()) / ".claude" / "projects"
    if not base.is_dir():
        return []
    target = workspace.resolve()
    found: list[Path] = []
    for log in sorted(base.glob("*/*.jsonl")):
        for record, ok in iter_records(log):
            if not ok:
                continue
            cwd = record.get("cwd")
            if isinstance(cwd, str) and cwd:
                try:
                    if Path(cwd).resolve() == target:
                        found.append(log)
                except (OSError, ValueError):
                    pass
                break  # the first record with a cwd settles it
    return found
