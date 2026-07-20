"""Fusion results over HTTP — the per-file explanations, read-only.

The heavy fusion run (ingest, correlate, blame) happens elsewhere — the `mri
fusion` CLI, or a scheduled job — and writes its results to the database. This
endpoint only *reads* them, so it is a fast, cheap GET: `explain_file` reassembles
a file's explanation from stored rows with no git or blame in the request path.

Auth is applied globally by the app's middleware; a path under `/api` that is not
on the public allowlist requires a token, so this endpoint inherits that gate
without per-route wiring.
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from mri.api.deps import db_conn
from mri.db.repository import top_risk_files
from mri.fusion import explain_file, weight_hotspots

router = APIRouter(prefix="/api", tags=["fusion"])


@router.get("/projects/{project_id}/fusion")
async def project_fusion(
    project_id: int,
    top: int = Query(10, ge=1, le=100, description="How many risky files to explain"),
    conn: aiosqlite.Connection = Depends(db_conn),
) -> dict:
    """Per-file fusion explanations for a project's riskiest files.

    The files are the hotspots the project's latest scan flagged; each is
    explained from stored authorship, decision and consequence data. A project
    with no completed scan simply has no hotspots, and the file list is empty —
    an honest absence, not an error. An unknown project id is a 404.
    """
    cursor = await conn.execute("SELECT id, name FROM projects WHERE id = ?", (project_id,))
    project = await cursor.fetchone()
    if project is None:
        raise HTTPException(404, "project not found")

    hotspots = await top_risk_files(conn, project_id, limit=top)
    # Order by the risk that sits under agent-modified code, matching the CLI and
    # MCP surfaces (ADR-011): a user diffing this API against `mri fusion` for the
    # same project must see the same leading file. weight_hotspots is a pure DB
    # read of the same cost class as the per-file explain below — no heavy git in
    # the request path — and returns every hotspot, just reordered.
    files = []
    for wr in await weight_hotspots(conn, hotspots, project_id=project_id):
        exp = await explain_file(conn, wr.file_path, project_id=project_id, base_risk=wr.base_risk)
        files.append({
            "file": exp.file_path,
            "prose": exp.prose,
            "factors": [{"name": f.name, "statement": f.statement, "value": f.value}
                        for f in exp.factors],
        })
    return {"project_id": project_id, "project": project[1], "files": files}
