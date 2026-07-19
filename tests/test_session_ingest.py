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


def _turn(seq: int, role: str, cwd: str, parts: list[dict], session_id: str = "sess-1") -> dict:
    return {
        "type": role,
        "sessionId": session_id,
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
        pid = int((await conn.execute(
            "INSERT INTO projects (name, path) VALUES ('p', '/p')"
        )).lastrowid)
        await conn.commit()
        first = await ingest_log(conn, log, repo_root=repo_root, project_id=pid)
        assert (first.sessions, first.events, first.touches) == (1, 2, 1)

        again = await ingest_log(conn, log, repo_root=repo_root, project_id=pid)
        assert (again.events, again.touches, again.unchanged) == (0, 0, 1)

        # The log grows, as a live one does.
        records.append(_turn(3, "assistant", cwd, [_use("Edit", str(repo_root / "src" / "b.py"), "u2")]))
        records.append(_turn(4, "user", cwd, [_result("u2")]))
        _log(log, records)

        third = await ingest_log(conn, log, repo_root=repo_root, project_id=pid)
        assert (third.events, third.touches) == (2, 1)

        cursor = await conn.execute("SELECT count(*) FROM session_events")
        assert (await cursor.fetchone())[0] == 4
        assert len(await repo.touches_for_file(conn, "src/a.py", project_id=pid)) == 1


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


# ---------------------------------------------------------------------------
# What the audits found
# ---------------------------------------------------------------------------


async def test_a_rewritten_log_is_re_read_not_silently_skipped(
    db: Path, tmp_path: Path, repo_root: Path
):
    """The watermark assumed logs only ever grow. A log rewritten in place —
    crash recovery, a checkpoint re-emit, an editor — put different content
    where the previous run considered the work done, and the edits it now
    described were lost while the run reported nothing had changed. Reproduced
    against a real database before this check existed."""
    cwd = str(repo_root)
    first = [
        _turn(1, "assistant", cwd, [_use("Write", str(repo_root / "src" / "a.py"), "u1")]),
        _turn(2, "user", cwd, [_result("u1")]),
        _turn(3, "assistant", cwd, [{"type": "text", "text": "nothing to do"}]),
    ]
    log = _log(tmp_path / "s.jsonl", first)

    async with get_connection(db) as conn:
        pid = int((await conn.execute(
            "INSERT INTO projects (name, path) VALUES ('p', '/p')"
        )).lastrowid)
        await conn.commit()
        await ingest_log(conn, log, repo_root=repo_root, project_id=pid)

        # Turn 3 is rewritten: it is now a real edit of a different file.
        rewritten = list(first)
        rewritten[2] = _turn(
            3, "assistant", cwd, [_use("Write", str(repo_root / "src" / "b.py"), "u9")]
        )
        rewritten.append(_turn(4, "user", cwd, [_result("u9")]))
        _log(log, rewritten)

        result = await ingest_log(conn, log, repo_root=repo_root, project_id=pid)
        assert result.rewritten == 1, "the rewrite must be noticed and reported"
        touches = await repo.touches_for_file(conn, "src/b.py", project_id=pid)
        cursor = await conn.execute("SELECT count(*) FROM session_events")
        stored = (await cursor.fetchone())[0]

    assert len(touches) == 1, "the edit the rewritten log describes must be recovered"
    assert stored == 4, "re-reading must replace the stale copy, not stack on top of it"


def test_a_turn_is_fingerprinted_by_what_it_did_not_only_what_it_said(
    tmp_path: Path, repo_root: Path
):
    """Two turns can both carry no prose while writing different files. Hashing
    the text alone would make them identical, and a rewrite between them
    invisible."""
    a = _log(tmp_path / "a.jsonl", [
        _turn(1, "assistant", str(repo_root), [_use("Write", str(repo_root / "src" / "a.py"), "u1")]),
    ])
    b = _log(tmp_path / "b.jsonl", [
        _turn(1, "assistant", str(repo_root), [_use("Write", str(repo_root / "src" / "b.py"), "u1")]),
    ])
    left = claude_code.parse_log(a, repo_root=repo_root)
    right = claude_code.parse_log(b, repo_root=repo_root)
    assert left.turns[0].content_hash != right.turns[0].content_hash


def test_records_from_another_session_are_dropped_not_merged(tmp_path: Path, repo_root: Path):
    """One file, one session. A second id means the file was concatenated or
    corrupted, and merging would credit one session with another's work."""
    cwd = str(repo_root)
    foreign = _turn(2, "assistant", cwd, [_use("Write", str(repo_root / "src" / "b.py"), "u2")])
    foreign["sessionId"] = "someone-else"
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "assistant", cwd, [_use("Write", str(repo_root / "src" / "a.py"), "u1")]),
        foreign,
        _turn(3, "user", cwd, [_result("u1"), _result("u2")]),
    ])
    parsed = claude_code.parse_log(log, repo_root=repo_root)
    assert parsed.external_id == "sess-1"
    assert parsed.foreign_records == 1
    assert [t.file_path for t in parsed.touches] == ["src/a.py"]


def test_a_reused_tool_call_id_keeps_both_touches(tmp_path: Path, repo_root: Path):
    """Overwriting the pending entry would drop the earlier call silently. The
    earlier one is kept at unknown outcome, because its result is now
    unknowable — which is not the same as evidence that nothing happened."""
    cwd = str(repo_root)
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "assistant", cwd, [_use("Write", str(repo_root / "src" / "a.py"), "dup")]),
        _turn(2, "assistant", cwd, [_use("Write", str(repo_root / "src" / "b.py"), "dup")]),
        _turn(3, "user", cwd, [_result("dup")]),
    ])
    parsed = claude_code.parse_log(log, repo_root=repo_root)
    assert parsed.duplicate_call_ids == 1
    assert sorted(t.file_path for t in parsed.touches) == ["src/a.py", "src/b.py"]


def test_failed_calls_are_counted_even_though_they_are_not_touches(
    tmp_path: Path, repo_root: Path
):
    """"Half this session failed its edits" is a fact about the session worth
    having, even though none of those calls changed a file."""
    cwd = str(repo_root)
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "assistant", cwd, [
            _use("Edit", str(repo_root / "src" / "a.py"), "u1"),
            _use("Edit", str(repo_root / "src" / "b.py"), "u2"),
        ]),
        _turn(2, "user", cwd, [_result("u1", error=True), _result("u2", error=True)]),
    ])
    parsed = claude_code.parse_log(log, repo_root=repo_root)
    assert parsed.touches == []
    assert parsed.failed_calls == 2


def test_an_absurdly_long_line_is_counted_not_decoded(tmp_path: Path, repo_root: Path):
    """A turn is prose and tool arguments, not eight megabytes. A single 500 MB
    line was measured taking the process to a 1.5 GB peak."""
    path = tmp_path / "s.jsonl"
    huge = json.dumps({
        "type": "user", "sessionId": "sess-1", "cwd": str(repo_root),
        "message": {"content": [{"type": "text", "text": "x" * (claude_code.MAX_LINE_BYTES + 10)}]},
    })
    sane = json.dumps(_turn(1, "user", str(repo_root), [{"type": "text", "text": "hi"}]))
    path.write_text(huge + "\n" + sane + "\n", encoding="utf-8")

    parsed = claude_code.parse_log(path, repo_root=repo_root)
    assert parsed.unreadable_lines == 1
    assert len(parsed.turns) == 1, "the sane record after it must still be read"


def test_one_unreadable_candidate_does_not_stop_discovery(tmp_path: Path, repo_root: Path):
    """That directory is not ours. It can hold a locked file, a cloud-storage
    placeholder, or a directory that happens to end in .jsonl — and one of those
    must not stop every other log from being read."""
    home = tmp_path / "home"
    projects = home / ".claude" / "projects" / "p"
    projects.mkdir(parents=True)
    (projects / "aaa-a-directory.jsonl").mkdir()  # sorts first, so it is hit first
    _log(projects / "zzz-real.jsonl", [
        _turn(1, "assistant", str(repo_root), [_use("Write", str(repo_root / "src" / "a.py"), "u1")]),
        _turn(2, "user", str(repo_root), [_result("u1")]),
    ])
    found = claude_code.logs_for_workspace(repo_root, home=home)
    assert [p.name for p in found] == ["zzz-real.jsonl"]


async def test_a_racing_ingest_fails_loudly_rather_than_duplicating(
    db: Path, tmp_path: Path, repo_root: Path
):
    """UNIQUE (session_id, seq) is what stops the duplication. This turns the
    resulting bare sqlite error into one that names the cause and the rule."""
    from mri.ingest.service import ConcurrentIngestError

    cwd = str(repo_root)
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "assistant", cwd, [_use("Write", str(repo_root / "src" / "a.py"), "u1")]),
        _turn(2, "user", cwd, [_result("u1")]),
    ])
    async with get_connection(db) as conn:
        await ingest_log(conn, log, repo_root=repo_root)
        # The state a concurrent run leaves mid-flight: rows present, but the
        # fingerprint no longer matches, so this run believes it must re-read.
        await conn.execute("UPDATE session_events SET content_hash = 'stale' WHERE seq = 2")
        await conn.commit()

        async def racing_forget(*_args, **_kwargs):
            return None  # the other writer has not finished clearing yet

        import mri.ingest.service as service

        original = service._forget_session
        service._forget_session = racing_forget
        try:
            with pytest.raises(ConcurrentIngestError, match="serialised per session"):
                await ingest_log(conn, log, repo_root=repo_root)
        finally:
            service._forget_session = original


# ---------------------------------------------------------------------------
# Seam: ingest -> authorship, project scoping, and the event_id link
# ---------------------------------------------------------------------------


async def test_ingest_then_authorship_end_to_end_and_project_scoped(
    db: Path, tmp_path: Path, repo_root: Path
):
    """The boundary the whole-subsystem audit flagged as untested: a real log
    ingested through ingest_log, then fed to weight_hotspots — and isolated from
    another project touching the same file path."""
    from mri.fusion import weight_hotspots

    cwd = str(repo_root)
    # Distinct session ids: two real repos never share a session id, and reusing
    # one made an earlier version of this test a false positive — it passed
    # because the second ingest *deleted* the first's data, not because scoping
    # isolated it.
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "assistant", cwd, [_use("Write", str(repo_root / "src" / "a.py"), "u1")], "sess-mine"),
        _turn(2, "user", cwd, [_result("u1")], "sess-mine"),
    ])
    async with get_connection(db) as conn:
        mine = int((await conn.execute(
            "INSERT INTO projects (name, path) VALUES ('mine', ?)", (cwd,)
        )).lastrowid)
        other = int((await conn.execute(
            "INSERT INTO projects (name, path) VALUES ('other', '/other')"
        )).lastrowid)
        await conn.commit()

        # Another project's session wrote a same-named file.
        other_log = _log(tmp_path / "o.jsonl", [
            _turn(1, "assistant", cwd, [_use("Write", str(repo_root / "src" / "a.py"), "x1")], "sess-other"),
            _turn(2, "user", cwd, [_result("x1")], "sess-other"),
        ])
        await ingest_log(conn, other_log, repo_root=repo_root, project_id=other)

        await ingest_log(conn, log, repo_root=repo_root, project_id=mine)

        # Both sessions survive; each project sees only its own touch.
        weighted = await weight_hotspots(conn, {"src/a.py": 50.0}, project_id=mine)
        assert weighted[0].evidence.ai_write_touches == 1, "only my project's touch counts"
        assert weighted[0].weighted_risk == 45.0
        other_w = await weight_hotspots(conn, {"src/a.py": 50.0}, project_id=other)
        assert other_w[0].evidence.ai_write_touches == 1, "the other project still has its own"


async def test_a_session_id_cannot_be_hijacked_across_projects(
    db: Path, tmp_path: Path, repo_root: Path
):
    """A real agent-session id is globally unique and belongs to one workspace.
    Re-ingesting it under a different project is forgery/corruption, and silently
    obeying it hijacked — and could delete — the first project's data. Refused."""
    from mri.db.fusion_repository import CrossProjectSessionError

    cwd = str(repo_root)
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "assistant", cwd, [_use("Write", str(repo_root / "src" / "a.py"), "u1")], "dup"),
        _turn(2, "user", cwd, [_result("u1")], "dup"),
    ])
    async with get_connection(db) as conn:
        a = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('a', '/a')")).lastrowid)
        b = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('b', '/b')")).lastrowid)
        await conn.commit()
        await ingest_log(conn, log, repo_root=repo_root, project_id=a)
        with pytest.raises(CrossProjectSessionError):
            await ingest_log(conn, log, repo_root=repo_root, project_id=b)
        # A's data is intact.
        assert len(await repo.touches_for_file(conn, "src/a.py", project_id=a)) == 1


async def test_an_unclaimed_session_is_adopted_and_its_touches_backfilled(
    db: Path, tmp_path: Path, repo_root: Path
):
    """Scan-then-register: a session first ingested with no project, then with a
    real one, must not strand its touches at project_id NULL."""
    cwd = str(repo_root)
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "assistant", cwd, [_use("Write", str(repo_root / "src" / "a.py"), "u1")], "later"),
        _turn(2, "user", cwd, [_result("u1")], "later"),
    ])
    async with get_connection(db) as conn:
        pid = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('p', '/p')")).lastrowid)
        await conn.commit()
        await ingest_log(conn, log, repo_root=repo_root, project_id=None)   # unclaimed
        assert len(await repo.touches_for_file(conn, "src/a.py", project_id=pid)) == 0
        await ingest_log(conn, log, repo_root=repo_root, project_id=pid)    # claimed
        assert len(await repo.touches_for_file(conn, "src/a.py", project_id=pid)) == 1, (
            "adoption must backfill the touches written while unclaimed"
        )


async def test_a_touch_is_linked_to_the_turn_that_produced_it(
    db: Path, tmp_path: Path, repo_root: Path
):
    """event_id was defined and indexed since 0002 but never populated — the
    schema asserted a link that did not exist. It does now."""
    cwd = str(repo_root)
    log = _log(tmp_path / "s.jsonl", [
        _turn(1, "assistant", cwd, [_use("Write", str(repo_root / "src" / "a.py"), "u1")]),
        _turn(2, "user", cwd, [_result("u1")]),
    ])
    async with get_connection(db) as conn:
        pid = int((await conn.execute(
            "INSERT INTO projects (name, path) VALUES ('p', ?)", (cwd,)
        )).lastrowid)
        await conn.commit()
        await ingest_log(conn, log, repo_root=repo_root, project_id=pid)
        row = await (await conn.execute(
            "SELECT t.event_id, e.seq FROM session_file_touches t"
            " JOIN session_events e ON e.id = t.event_id"
        )).fetchone()
    assert row is not None, "the touch must resolve to a real event row"
    assert row[1] == 1, "the touch points at the assistant turn that made the Write"
