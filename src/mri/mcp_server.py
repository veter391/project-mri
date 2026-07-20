"""The agent-native surface — MRI as an MCP provider.

The vision's L5: MRI is not only a tool a human runs, it is a provider a coding
agent queries. This exposes the fusion loop as MCP tools so an agent can ask, in
the middle of its own work, "who authored this file, and what decided it" and get
the same honest, fact-backed answer the CLI prints.

The tools are thin over the audited fusion layers — they resolve a project by
path, then run or read the same functions the CLI and HTTP surface use. The heavy
run is one tool (`fuse_project`); the rest read what it stored, so an agent fuses
once and then queries cheaply. The read tools never write: they look a project up
by path and, finding none, answer with an honest "no evidence" rather than
minting an empty project row or bumping its `last_scanned`.

The `mcp` SDK is an optional dependency (`pip install project-mri[mcp]`); this
module imports it lazily inside `build_server` so the core package does not
require it.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

__all__ = ["build_server"]

# The riskiest-files window the read path considers. Kept in lockstep with the
# HTTP route's `Query(..., le=100)` (src/mri/api/routes/fusion.py) — a file
# ranked outside this window carries no stored `risk` factor.
_RISK_WINDOW = 100


def build_server(db_path: Path | None = None) -> Any:
    """Construct the FastMCP server with the fusion tools registered.

    `db_path` overrides the database (used by tests); production uses the
    default path, the same one the CLI and API use.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via the CLI's message
        raise ModuleNotFoundError(
            "the MCP server needs the optional 'mcp' dependency; "
            "install it with `pip install project-mri[mcp]`"
        ) from exc

    from mri.db.repository import default_db_path, get_connection, top_risk_files, upsert_project
    from mri.fusion import explain_file as _explain_file
    from mri.fusion import run_fusion
    from mri.utils import clean_text

    resolved_db = db_path or default_db_path()
    server = FastMCP("project-mri")

    async def _resolve(project_path: str) -> Path:
        # resolve() stats the filesystem; keep it off the event loop.
        return await asyncio.to_thread(lambda: Path(project_path).resolve())

    async def _existing_project_id(conn: Any, project_path: str) -> int | None:
        """The id of the project stored under this path, or None if none is.

        Read-only by design: a read tool must not create a project or bump its
        `last_scanned` (which reorders the project list) merely to answer a
        question. Only `fuse_project` writes.
        """
        root = await _resolve(project_path)
        cursor = await conn.execute("SELECT id FROM projects WHERE path = ?", (str(root),))
        row = await cursor.fetchone()
        return int(row[0]) if row else None

    @server.tool()
    async def fuse_project(project_path: str, top: int = 10) -> dict:
        """Run the full fusion loop over a repository and explain its riskiest
        files: session-log ingest, session->commit correlation, per-file
        AI/human/unattributed authorship, decision mining, and the consequence
        loop. Returns a count from each stage plus per-file explanations. This is
        the heavy call that writes what the other, read-only tools return."""
        import git

        root = await _resolve(project_path)
        if not await asyncio.to_thread(root.is_dir):
            raise ValueError(f"{root} is not a directory")
        try:
            repo = git.Repo(root)
        except Exception as exc:  # noqa: BLE001 - any GitPython error means "not a usable repo"
            raise ValueError(f"{root} is not a git repository") from exc

        async with get_connection(resolved_db) as conn:
            pid = await upsert_project(
                conn, path=str(root), name=root.name, default_branch="HEAD"
            )
            hotspots = await top_risk_files(conn, pid, limit=max(1, min(top, 100)))
            adr_dir = root / "docs" / "adr"
            report = await run_fusion(
                conn, repo, root, project_id=pid,
                hotspots=hotspots or None,
                adr_dir=adr_dir if await asyncio.to_thread(adr_dir.is_dir) else None,
            )
        return {
            "sessions": report.ingest.sessions,
            "touches": report.ingest.touches,
            "correlated": report.correlation.linked,
            "decisions": {
                "adr": report.adrs, "commit": report.commits, "links": report.decision_links,
            },
            "authored_files": report.authored_files,
            "files": [{"file": e.file_path, "prose": e.prose} for e in report.explanations],
        }

    @server.tool()
    async def explain_file(project_path: str, file_path: str) -> dict:
        """Explain one file — its risk, AI/human/unattributed authorship, the
        agent sessions behind it, and the decisions that touch it — from data a
        previous `fuse_project` stored. Every clause is a stored fact; a file (or
        a repo) with no fusion evidence says so plainly."""
        shown = clean_text(file_path)
        async with get_connection(resolved_db) as conn:
            pid = await _existing_project_id(conn, project_path)
            if pid is None:
                return {
                    "file": shown,
                    "prose": f"{shown}: no fusion evidence — run fuse_project on this repository first.",
                    "factors": [],
                }
            hotspots = await top_risk_files(conn, pid, limit=_RISK_WINDOW)
            exp = await _explain_file(
                conn, file_path, project_id=pid, base_risk=hotspots.get(file_path)
            )
        return {
            "file": exp.file_path,  # already sanitized inside the fusion explain layer
            "prose": exp.prose,
            "factors": [
                {"name": f.name, "statement": f.statement, "value": f.value} for f in exp.factors
            ],
        }

    @server.tool()
    async def get_authorship(project_path: str, file_path: str) -> dict:
        """The stored AI/human/unattributed line-share for a file, with the method
        and confidence it was computed at. Absent when no share has been computed —
        an honest 'unknown', not a fabricated zero."""
        from mri.db import fusion_repository as repo

        shown = clean_text(file_path)
        async with get_connection(resolved_db) as conn:
            pid = await _existing_project_id(conn, project_path)
            shares = (
                await repo.authorship_for_file(conn, file_path, project_id=pid)
                if pid is not None else []
            )
        if not shares:
            return {"file": shown, "computed": False}
        s = shares[0]
        return {
            "file": shown, "computed": True,
            "share_ai": s.share_ai, "share_human": s.share_human,
            "share_unattributed": s.share_unattributed,
            "method": s.method, "confidence": s.confidence,
        }

    @server.tool()
    async def get_decisions(project_path: str, file_path: str) -> dict:
        """The decisions that touch a file — mined from ADRs and commits — with
        their recoverable rationale (or an explicit null when a commit had none)."""
        from mri.db import fusion_repository as repo

        shown = clean_text(file_path)
        async with get_connection(resolved_db) as conn:
            pid = await _existing_project_id(conn, project_path)
            decisions = (
                await repo.decisions_affecting_file(conn, file_path, project_id=pid)
                if pid is not None else []
            )
        return {
            "file": shown,
            "decisions": [
                {"summary": d.summary, "rationale": d.rationale, "source": d.source,
                 "confidence": d.confidence}
                for d in decisions
            ],
        }

    return server
