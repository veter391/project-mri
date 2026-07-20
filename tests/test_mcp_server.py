"""The MCP server, exercised through a real in-memory client↔server session.

Self-review rule 13: an MCP surface is verified by a client actually calling its
tools over the protocol, not by reading the diff. This wires the SDK's in-memory
transport to the built server, lists the tools, and calls them, asserting the
signature answer comes back through the protocol.
"""
from __future__ import annotations

import json
from pathlib import Path

import git
import pytest

mcp = pytest.importorskip("mcp", reason="MCP surface needs the optional 'mcp' extra")

from mcp.client.session import ClientSession  # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

from mri.db.migrator import migrate  # noqa: E402
from mri.db.repository import connect_sync  # noqa: E402
from mri.mcp_server import build_server  # noqa: E402


def _seed(db: Path, project_dir: Path) -> str:
    """A project with a hotspot finding and a stored AI share, keyed by a path.

    Stored under the resolved path, because the tools resolve `project_path`
    before looking the project up — the two must match."""
    migrate(db)
    conn = connect_sync(db)
    project_path = str(project_dir.resolve())
    try:
        pid = conn.execute(
            "INSERT INTO projects (path, name, default_branch) VALUES (?, 'proj', 'HEAD')",
            (project_path,),
        ).lastrowid
        sid = conn.execute(
            "INSERT INTO scans (project_id, scan_uuid, status) VALUES (?, 'u1', 'completed')",
            (pid,),
        ).lastrowid
        rid = conn.execute(
            "INSERT INTO analyzer_runs (scan_id, analyzer_name, status, score_value, score_label)"
            " VALUES (?, 'git_history', 'completed', 50, 'g')",
            (sid,),
        ).lastrowid
        conn.execute(
            "INSERT INTO findings (run_id, analyzer_name, severity, category, title, target_path, score)"
            " VALUES (?, 'git_history', 'high', 'hotspot', 'x', 'app.py', 82)",
            (rid,),
        )
        conn.execute(
            "INSERT INTO authorship_shares (project_id, file_path, share_ai, share_human,"
            " share_unattributed, method, confidence)"
            " VALUES (?, 'app.py', 88, 0, 12, 'blame_session_commit', 0.9)",
            (pid,),
        )
        did = conn.execute(
            "INSERT INTO decisions (summary, source, project_id, file_path, confidence)"
            " VALUES ('switch to async', 'adr', ?, 'app.py', 0.95)",
            (pid,),
        ).lastrowid
        conn.execute(
            "INSERT INTO consequences (decision_id, metric, file_path,"
            " window_start, window_end, delta, causal_claim, confidence)"
            " VALUES (?, 'complexity', 'app.py', '2026-01-01', '2026-02-01', 12.0,"
            " 'correlation', 0.4)",
            (did,),
        )
        conn.commit()
    finally:
        conn.close()
    return project_path


def _make_git_repo(path: Path) -> None:
    """A minimal real git repo with one commit, for the heavy fuse_project path."""
    path.mkdir(parents=True, exist_ok=True)
    repo = git.Repo.init(path)
    (path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    repo.index.add(["app.py"])
    actor = git.Actor("t", "t@t")
    repo.index.commit("init", author=actor, committer=actor)


def _project_count(db: Path) -> int:
    conn = connect_sync(db)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0])
    finally:
        conn.close()


def _text(result) -> str:
    """The text payload of a tool result, across SDK shapes."""
    parts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
    return "\n".join(parts)


async def test_tools_are_listed_and_callable_over_the_protocol(tmp_path: Path):
    db = tmp_path / "mcp.db"
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    project_path = _seed(db, project_dir)
    server = build_server(db_path=db)

    async with create_connected_server_and_client_session(server._mcp_server) as client:
        client: ClientSession
        await client.initialize()

        tools = {t.name for t in (await client.list_tools()).tools}
        assert {
            "fuse_project", "explain_file", "get_authorship",
            "get_decisions", "get_consequences",
        } <= tools

        # explain_file returns the signature sentence through the protocol.
        r = await client.call_tool("explain_file", {"project_path": project_path, "file_path": "app.py"})
        assert not r.isError, _text(r)
        assert "88% of its current lines are AI-authored" in _text(r)
        assert "risk 82/100" in _text(r)

        # get_authorship returns the structured share.
        r = await client.call_tool("get_authorship", {"project_path": project_path, "file_path": "app.py"})
        payload = json.loads(_text(r))
        assert payload["computed"] is True
        assert payload["share_ai"] == 88
        assert payload["share_human"] == 0

        # get_decisions returns the decisions touching the file.
        r = await client.call_tool("get_decisions", {"project_path": project_path, "file_path": "app.py"})
        payload = json.loads(_text(r))
        assert payload["decisions"][0]["summary"] == "switch to async"

        # get_consequences returns what followed those decisions, labelled honestly.
        r = await client.call_tool("get_consequences", {"project_path": project_path, "file_path": "app.py"})
        payload = json.loads(_text(r))
        assert payload["consequences"][0]["metric"] == "complexity"
        assert payload["consequences"][0]["claim"] == "correlation"
        assert payload["consequences"][0]["decision"] == "switch to async"


async def test_authorship_of_an_uncomputed_file_is_an_honest_unknown(tmp_path: Path):
    db = tmp_path / "mcp.db"
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    project_path = _seed(db, project_dir)
    server = build_server(db_path=db)
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        await client.initialize()
        r = await client.call_tool(
            "get_authorship", {"project_path": project_path, "file_path": "never_touched.py"}
        )
        payload = json.loads(_text(r))
    assert payload["computed"] is False, "no share computed is an explicit unknown, not a zero"


async def test_fuse_project_runs_over_a_real_repo_through_the_protocol(tmp_path: Path):
    """The heavy tool, exercised end-to-end against a real git repo. A fresh
    repo has no sessions, so every stage count is zero — but the documented
    shape must come back intact, proving the git path and the write succeed."""
    db = tmp_path / "mcp.db"
    migrate(db)
    repo_dir = tmp_path / "repo"
    _make_git_repo(repo_dir)
    server = build_server(db_path=db)
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        await client.initialize()
        r = await client.call_tool("fuse_project", {"project_path": str(repo_dir), "top": 5})
        assert not r.isError, _text(r)
        payload = json.loads(_text(r))
    assert {"sessions", "touches", "correlated", "decisions", "authored_files", "files"} <= set(payload)
    assert set(payload["decisions"]) == {"adr", "commit", "links"}


async def test_fuse_project_on_a_non_repo_is_a_clean_error(tmp_path: Path):
    """A directory that is not a git repo yields the CLI's message through the
    protocol, not a raw GitPython stack trace."""
    db = tmp_path / "mcp.db"
    migrate(db)
    plain = tmp_path / "plain"
    plain.mkdir()
    server = build_server(db_path=db)
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        await client.initialize()
        r = await client.call_tool("fuse_project", {"project_path": str(plain)})
    assert r.isError
    assert "not a git repository" in _text(r)


async def test_read_tools_never_create_a_project_row(tmp_path: Path):
    """A read over an unknown path is an honest 'no evidence' and, critically,
    writes nothing — reads must not mint a project row or bump last_scanned."""
    db = tmp_path / "mcp.db"
    migrate(db)
    server = build_server(db_path=db)
    unknown = str((tmp_path / "never_scanned").resolve())
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        await client.initialize()
        r = await client.call_tool("get_authorship", {"project_path": unknown, "file_path": "x.py"})
        assert json.loads(_text(r))["computed"] is False
        r = await client.call_tool("explain_file", {"project_path": unknown, "file_path": "x.py"})
        assert "no fusion evidence" in _text(r)
        r = await client.call_tool("get_decisions", {"project_path": unknown, "file_path": "x.py"})
        assert json.loads(_text(r))["decisions"] == []
    assert _project_count(db) == 0, "a read tool wrote a project row — reads must not write"


async def test_file_path_is_sanitized_in_read_tool_output(tmp_path: Path):
    """A filename carrying a terminal escape must not round-trip verbatim into a
    tool result an MCP host renders to a terminal."""
    db = tmp_path / "mcp.db"
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    project_path = _seed(db, project_dir)
    server = build_server(db_path=db)
    dirty = "app\x1b[31m.py\x1b[0m"
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        await client.initialize()
        # Inspect the PARSED field, not the JSON text: json.dumps escapes the ESC
        # byte to a unicode escape sequence, so a substring check on the raw text
        # passes even when the control char round-trips. Decode first, then assert.
        r = await client.call_tool("get_authorship", {"project_path": project_path, "file_path": dirty})
        assert "\x1b" not in json.loads(_text(r))["file"], "escape survived into get_authorship"
        r = await client.call_tool("get_decisions", {"project_path": project_path, "file_path": dirty})
        assert "\x1b" not in json.loads(_text(r))["file"], "escape survived into get_decisions"
