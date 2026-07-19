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


def _parse_time(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
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


def _relative_within(raw_path: str, root: Path) -> str | None:
    """Repo-relative path, or None if the file is not in this repository.

    A session ranges across a machine — other repositories, temp files, the
    user's home. Only what is inside the project being scanned can be attributed
    to it, and a path that is merely similar is not the same path.
    """
    try:
        candidate = Path(raw_path).resolve()
    except (OSError, ValueError):
        return None
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return None


def iter_records(log: Path) -> Iterator[tuple[dict, bool]]:
    """Yield (record, ok) per line, streaming.

    Logs reach tens of megabytes; they are never read whole. A line that does
    not parse yields ({}, False) so the caller can count it.
    """
    with log.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
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
    import hashlib

    root = repo_root.resolve()
    session: ParsedSession | None = None
    seq = 0
    # tool_use_id -> (seq, file_path, touch_kind, occurred_at), awaiting its result.
    pending: dict[str, tuple[int, str, str, datetime | None]] = {}
    errored: set[str] = set()

    for record, ok in iter_records(log):
        if not ok:
            if session is not None:
                session.unreadable_lines += 1
            continue

        external_id = record.get("sessionId")
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
                errored.add(use_id)
                pending.pop(use_id, None)
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
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "",
            occurred_at=occurred_at,
        ))

        for part in _content_parts(record):
            if part.get("type") != "tool_use":
                continue
            touch_kind = FILE_TOOLS.get(str(part.get("name")))
            if touch_kind is None:
                continue
            raw_path = (part.get("input") or {}).get("file_path")
            if not isinstance(raw_path, str):
                continue
            relative = _relative_within(raw_path, root)
            if relative is None:
                continue  # another repository, a temp file, somewhere else
            use_id = part.get("id")
            if isinstance(use_id, str):
                pending[use_id] = (seq, relative, touch_kind, occurred_at)
            else:
                session.touches.append(ParsedTouch(
                    seq=seq, file_path=relative, touch_kind=touch_kind,
                    confidence=CONFIDENCE_OUTCOME_UNKNOWN, occurred_at=occurred_at,
                ))

    if session is None:
        return None

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
