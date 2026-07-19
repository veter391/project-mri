"""Reading agent session logs into the fusion tables.

The parser was written against a real 21,750-record log and validated against a
second one whose edits could be checked by hand. These tests pin the decisions
that make the resulting numbers defensible: what counts as a turn, what counts
as a touch, what gets dropped, and what happens on the second run.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mri.db import fusion_repository as repo
from mri.db.migrator import migrate
from mri.db.repository import get_connection
from mri.ingest import claude_code, ingest_log, ingest_workspace


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "ingest.db"
    migrate(path)
    return path


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("y = 2\n", encoding="utf-8")
    return root


def _log(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def _turn(seq: int, role: str, cwd: str, parts: list[dict]) -> dict:
    return {
        "type": role,
        "sessionId": "sess-1",
        "cwd": cwd,
        "timestamp": f"2026-07-{seq + 1:02d}T10:00:00.000Z",
        "message": {"content": parts},
    }


def _use(tool: str, file_path: str, use_id: str) -> dict:
    return {"type": "tool_use", "id": use_id, "name": tool, "input": {"file_path": file_path}}


def _result(use_id: str, *, error: bool = False) -> dict:
    part: dict = {"type": "tool_result", "tool_use_id": use_id, "content": "ok"}
    if error:
        part["is_error"] = True
    return part


# ---------------------------------------------------------------------------
# What becomes a turn
# ---------------------------------------------------------------------------


def test_only_real_turns_are_counted(tmp_path: Path, repo_root: Path):
    """A log restates content in `last-prompt`, `ai-title` and `attachment`
    records. Counting those would inflate a session's apparent influence over
    the code, which is the number this whole layer exists to get right."""
    cwd = str(repo_root)
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "user", cwd, [{"type": "text", "text": "do the thing"}]),
        {"type": "last-prompt", "sessionId": "sess-1", "cwd": cwd, "message": {"content": "do the thing"}},
        {"type": "ai-title", "sessionId": "sess-1", "cwd": cwd, "message": {"content": "The Thing"}},
        {"type": "attachment", "sessionId": "sess-1", "cwd": cwd},
        _turn(2, "assistant", cwd, [{"type": "text", "text": "done"}]),
    ])
    parsed = claude_code.parse_log(log, repo_root=repo_root)
    assert [t.role for t in parsed.turns] == ["user", "assistant"]
    assert [t.seq for t in parsed.turns] == [1, 2]


def test_content_is_not_retained_unless_asked(tmp_path: Path, repo_root: Path):
    """Prompts routinely contain pasted credentials, so retention is opt-in.
    The hash is kept either way, which is what deduplication actually needs."""
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "user", str(repo_root), [{"type": "text", "text": "my key is sk-SECRET"}]),
    ])
    default = claude_code.parse_log(log, repo_root=repo_root)
    assert default.turns[0].content is None
    assert default.turns[0].content_hash, "the hash must survive so turns stay correlatable"

    opted_in = claude_code.parse_log(log, repo_root=repo_root, store_content=True)
    assert opted_in.turns[0].content == "my key is sk-SECRET"
    assert opted_in.turns[0].content_hash == default.turns[0].content_hash


# ---------------------------------------------------------------------------
# What becomes a file touch
# ---------------------------------------------------------------------------


def test_a_failed_tool_call_is_not_a_change(tmp_path: Path, repo_root: Path):
    """An Edit whose result was an error did not change the file. Recording it
    would attribute a change that never happened — the one failure this product
    cannot afford."""
    cwd = str(repo_root)
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "assistant", cwd, [
            _use("Edit", str(repo_root / "src" / "a.py"), "u1"),
            _use("Edit", str(repo_root / "src" / "b.py"), "u2"),
        ]),
        _turn(2, "user", cwd, [_result("u1"), _result("u2", error=True)]),
    ])
    parsed = claude_code.parse_log(log, repo_root=repo_root)
    assert [t.file_path for t in parsed.touches] == ["src/a.py"]
    assert parsed.touches[0].confidence == claude_code.CONFIDENCE_REPORTED


def test_an_unanswered_call_is_recorded_as_uncertain(tmp_path: Path, repo_root: Path):
    """The tool was asked to do it and the log ends before saying whether it
    did. That is a real state, and the confidence says so rather than the touch
    being invented or discarded."""
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "assistant", str(repo_root), [_use("Write", str(repo_root / "src" / "a.py"), "u1")]),
    ])
    parsed = claude_code.parse_log(log, repo_root=repo_root)
    assert len(parsed.touches) == 1
    assert parsed.touches[0].confidence == claude_code.CONFIDENCE_OUTCOME_UNKNOWN


def test_confidence_is_never_certain(tmp_path: Path, repo_root: Path):
    """The log says what a tool reported. A report is not a filesystem
    observation — the file could have been reverted a minute later."""
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "assistant", str(repo_root), [_use("Write", str(repo_root / "src" / "a.py"), "u1")]),
        _turn(2, "user", str(repo_root), [_result("u1")]),
    ])
    parsed = claude_code.parse_log(log, repo_root=repo_root)
    assert all(0.0 < t.confidence < 1.0 for t in parsed.touches)


def test_files_outside_the_repository_are_dropped(tmp_path: Path, repo_root: Path):
    """A session ranges across a machine. Only what is inside the project being
    scanned can be attributed to it."""
    outside = tmp_path / "elsewhere" / "other.py"
    outside.parent.mkdir()
    outside.write_text("z = 3\n", encoding="utf-8")
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "assistant", str(repo_root), [
            _use("Write", str(repo_root / "src" / "a.py"), "u1"),
            _use("Write", str(outside), "u2"),
        ]),
        _turn(2, "user", str(repo_root), [_result("u1"), _result("u2")]),
    ])
    parsed = claude_code.parse_log(log, repo_root=repo_root)
    assert [t.file_path for t in parsed.touches] == ["src/a.py"]


def test_reads_are_recorded_but_are_not_authorship(tmp_path: Path, repo_root: Path):
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "assistant", str(repo_root), [_use("Read", str(repo_root / "src" / "a.py"), "u1")]),
        _turn(2, "user", str(repo_root), [_result("u1")]),
    ])
    parsed = claude_code.parse_log(log, repo_root=repo_root)
    assert parsed.touches[0].touch_kind == "read"


def test_a_truncated_final_line_is_counted_not_swallowed(tmp_path: Path, repo_root: Path):
    """A live log's last line is routinely a partial write. That is normal and
    survivable — but a large count means the parser is wrong about the format
    and every number derived from it is suspect, so it is reported."""
    path = tmp_path / "s.jsonl"
    path.write_text(
        json.dumps(_turn(1, "user", str(repo_root), [{"type": "text", "text": "hi"}]))
        + '\n{"type": "assistant", "sessi',
        encoding="utf-8",
    )
    parsed = claude_code.parse_log(path, repo_root=repo_root)
    assert len(parsed.turns) == 1
    assert parsed.unreadable_lines == 1


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def test_ingest_is_idempotent_and_resumable(db: Path, tmp_path: Path, repo_root: Path):
    """Ingest runs repeatedly against logs that are still being written. The
    second run over an unchanged log must change nothing — a double-counted
    session silently inflates every authorship number downstream."""
    cwd = str(repo_root)
    records = [
        _turn(1, "assistant", cwd, [_use("Write", str(repo_root / "src" / "a.py"), "u1")]),
        _turn(2, "user", cwd, [_result("u1")]),
    ]
    log = _log(tmp_path / "s.jsonl", records)

    async with get_connection(db) as conn:
        first = await ingest_log(conn, log, repo_root=repo_root)
        assert (first.sessions, first.events, first.touches) == (1, 2, 1)

        again = await ingest_log(conn, log, repo_root=repo_root)
        assert (again.events, again.touches, again.unchanged) == (0, 0, 1)

        # The log grows, as a live one does.
        records.append(_turn(3, "assistant", cwd, [_use("Edit", str(repo_root / "src" / "b.py"), "u2")]))
        records.append(_turn(4, "user", cwd, [_result("u2")]))
        _log(log, records)

        third = await ingest_log(conn, log, repo_root=repo_root)
        assert (third.events, third.touches) == (2, 1)

        cursor = await conn.execute("SELECT count(*) FROM session_events")
        assert (await cursor.fetchone())[0] == 4
        assert len(await repo.touches_for_file(conn, "src/a.py")) == 1


async def test_ingest_respects_retention_and_redacts_on_the_way_back(
    db: Path, tmp_path: Path, repo_root: Path
):
    """Ingesting with content, then ingesting the same log without it, must
    leave nothing behind — the second run is the user turning retention off."""
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "user", str(repo_root), [{"type": "text", "text": "sk-SECRET"}]),
    ])
    async with get_connection(db) as conn:
        await ingest_log(conn, log, repo_root=repo_root, store_content=True)
        cursor = await conn.execute("SELECT content FROM session_events")
        assert (await cursor.fetchone())[0] == "sk-SECRET"

        await ingest_log(conn, log, repo_root=repo_root, store_content=False)
        cursor = await conn.execute("SELECT content, content_hash FROM session_events")
        content, content_hash = await cursor.fetchone()
    assert content is None, "turning retention off must drop what was already stored"
    assert content_hash, "the hash stays, so turns remain correlatable"


async def test_a_workspace_nobody_used_an_agent_on_is_not_an_error(db: Path, tmp_path: Path):
    """Most repositories were never touched by an agent. Zero is a real answer."""
    home = tmp_path / "home"
    home.mkdir()
    async with get_connection(db) as conn:
        result = await ingest_workspace(conn, tmp_path / "project", home=home)
    assert (result.sessions, result.events, result.touches) == (0, 0, 0)


async def test_logs_are_matched_by_recorded_cwd_not_by_directory_name(
    db: Path, tmp_path: Path, repo_root: Path
):
    """The on-disk directory name is another program's slugification rule. The
    log states where it ran; ask it rather than reproducing that rule."""
    home = tmp_path / "home"
    projects = home / ".claude" / "projects" / "an-unrelated-slug"
    projects.mkdir(parents=True)
    _log(projects / "sess-1.jsonl", [
        _turn(1, "assistant", str(repo_root), [_use("Write", str(repo_root / "src" / "a.py"), "u1")]),
        _turn(2, "user", str(repo_root), [_result("u1")]),
    ])
    other = home / ".claude" / "projects" / "someone-elses-project"
    other.mkdir(parents=True)
    _log(other / "sess-2.jsonl", [
        {"type": "user", "sessionId": "sess-2", "cwd": str(tmp_path / "not-ours"),
         "message": {"content": [{"type": "text", "text": "hi"}]}},
    ])

    async with get_connection(db) as conn:
        result = await ingest_workspace(conn, repo_root, home=home)
        assert result.sessions == 1, "only the log whose cwd is this workspace"
        stored = await repo.get_session(conn, claude_code.SOURCE, "sess-1")
        assert stored is not None
        assert stored.workspace_path == str(repo_root)


def test_the_parser_survives_a_log_with_no_sessions(tmp_path: Path, repo_root: Path):
    log = _log(tmp_path / "s.jsonl", [{"type": "system", "subtype": "init"}])
    assert claude_code.parse_log(log, repo_root=repo_root) is None
