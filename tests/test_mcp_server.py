"""The MCP server, exercised through a real in-memory client↔server session.

Self-review rule 13: an MCP surface is verified by a client actually calling its
tools over the protocol, not by reading the diff. This wires the SDK's in-memory
transport to the built server, lists the tools, and calls them, asserting the
signature answer comes back through the protocol.
"""
from __future__ import annotations

import json
from pathlib import Path

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
        conn.execute(
            "INSERT INTO decisions (summary, source, project_id, file_path, confidence)"
            " VALUES ('switch to async', 'adr', ?, 'app.py', 0.95)",
            (pid,),
        )
        conn.commit()
    finally:
        conn.close()
    return project_path


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
        assert {"fuse_project", "explain_file", "get_authorship", "get_decisions"} <= tools

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
