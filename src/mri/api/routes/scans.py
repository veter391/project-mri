"""Scan routes — POST /api/scans, GET /api/scans/{uuid}, WebSocket progress.

Production-hardened:
- Input validation via mri.security (path allowlist, branch name)
- Structured logging via mri.logging_setup
- Graceful shutdown via mri.api.routes.scans.shutdown
- Persistent errors via scan_events (DB write of any exception)
- Batched progress events (no DB write per progress tick)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, Response

from mri import __version__
from mri.api.deps import db_conn
from mri.db.repository import (
    create_scan,
    insert_findings,
    record_event,
    save_analyzer_run,
    update_scan_status,
    upsert_project,
)
from mri.models.scan import (
    ProjectListResponse,
    ProjectSummary,
    Report,
    ScanAccepted,
    ScanListResponse,
    ScanRequest,
    ScanStatus,
    ScanSummary,
)
from mri.security import (
    PathValidationError,
    sanitize_for_log,
    validate_branch,
    validate_project_path,
)
from mri.services.report_generator import render_html, render_json
from mri.services.scanner import Scanner, ScanOptions

logger = logging.getLogger("mri.scans")
router = APIRouter(prefix="/api", tags=["scans"])


# Compile UUID regex once (32 hex chars, no dashes).
# uuid.uuid4().hex is 32 lowercase hex characters.
_UUID_RE = re.compile(r"^[a-f0-9]{32}$")


# ---------------------------------------------------------------------------
# In-memory progress hub
# ---------------------------------------------------------------------------


class ProgressBus:
    """Pub/sub for WebSocket subscribers."""

    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, scan_uuid: str) -> asyncio.Queue:
        async with self._lock:
            q: asyncio.Queue = asyncio.Queue(maxsize=200)
            self._subs.setdefault(scan_uuid, []).append(q)
            return q

    async def unsubscribe(self, scan_uuid: str, q: asyncio.Queue) -> None:
        async with self._lock:
            if scan_uuid in self._subs and q in self._subs[scan_uuid]:
                self._subs[scan_uuid].remove(q)
                if not self._subs[scan_uuid]:
                    del self._subs[scan_uuid]

    def publish(self, scan_uuid: str, message: dict) -> None:
        for q in self._subs.get(scan_uuid, []):
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass  # Drop if subscriber is slow


bus = ProgressBus()


# ---------------------------------------------------------------------------
# Graceful shutdown — cancel pending scans + close DB
# ---------------------------------------------------------------------------


_active_scan_tasks: set[asyncio.Task] = set()


async def shutdown() -> None:
    """Called from app lifespan on shutdown. Cancel active scans gracefully."""
    if not _active_scan_tasks:
        return
    logger.info(
        "scans.shutdown",
        extra={
            "event": "scans.shutdown",
            "active_scans": len(_active_scan_tasks),
        },
    )
    for task in list(_active_scan_tasks):
        task.cancel()
    # Wait for cancellation with timeout
    try:
        await asyncio.wait_for(
            asyncio.gather(*_active_scan_tasks, return_exceptions=True),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        logger.warning("scans.shutdown_timeout", extra={"event": "scans.shutdown_timeout"})


# ---------------------------------------------------------------------------
# POST /api/scans
# ---------------------------------------------------------------------------


@router.post("/scans", response_model=ScanAccepted)
async def start_scan(
    req: ScanRequest,
    conn: aiosqlite.Connection = Depends(db_conn),
) -> ScanAccepted:
    """Start a scan.

    `project_path` may be either a local filesystem path (e.g. `/home/user/repo`)
    or a git URL (e.g. `https://github.com/owner/name`). URLs are cloned
    automatically using configured credentials.
    """
    # Detect URL vs local path
    is_url = req.project_path.startswith(("https://", "http://", "git@"))
    if is_url:
        # Validate URL (basic shape check)
        from mri.services.repo_cloner import parse_repo_url
        try:
            parse_repo_url(req.project_path)
        except ValueError as e:
            logger.info(
                "scan.rejected",
                extra={"event": "scan.rejected", "reason": "url", "error": str(e)},
            )
            raise HTTPException(400, f"invalid repository URL: {e}") from e
        # Use the URL as the path key (will be cloned by scanner)
        p_path_display = req.project_path
        p_name = req.project_path.rstrip("/").split("/")[-1].replace(".git", "") or "remote-repo"
    else:
        # Validate local path
        try:
            p = validate_project_path(req.project_path)
        except PathValidationError as e:
            logger.info(
                "scan.rejected",
                extra={"event": "scan.rejected", "reason": "path", "error": str(e)},
            )
            raise HTTPException(400, str(e)) from e
        p_path_display = str(p)
        p_name = p.name

    # Validate branch name (for any scan type)
    try:
        branch = validate_branch(req.branch)
    except ValueError as e:
        logger.info(
            "scan.rejected",
            extra={"event": "scan.rejected", "reason": "branch", "error": str(e)},
        )
        raise HTTPException(400, str(e)) from e

    # Use p_path_display (URL or local path) as the project's identity
    scan_uuid = uuid.uuid4().hex
    project_id = await upsert_project(conn, p_path_display, p_name, branch or "main")
    scan_id = await create_scan(conn, project_id, scan_uuid)
    await record_event(conn, scan_id, "log", f"scan {scan_uuid} queued for {p_path_display}")

    logger.info(
        "scan.start",
        extra={
            "event": "scan.start",
            "scan_uuid": scan_uuid,
            "project": sanitize_for_log(p_name),
            "path": sanitize_for_log(p_path_display),
            "branch": branch or "(default)",
            "source": "url" if is_url else "local",
        },
    )

    # Metrics
    from mri import metrics as _metrics
    _metrics.SCANS_STARTED.labels(source="url" if is_url else "local").inc(1)
    # ACTIVE_SCANS is incremented/decremented inside Scanner.scan (symmetric,
    # correct on both API and CLI paths) — do not touch the gauge here.

    # Kick off background scan
    task = asyncio.create_task(
        _run_scan(
            scan_uuid=scan_uuid,
            scan_id=scan_id,
            project_id=project_id,
            project_path=p_path_display,
            branch=branch,
            include_globs=req.include_globs,
            exclude_globs=req.exclude_globs,
        ),
        name=f"scan-{scan_uuid[:8]}",
    )
    _active_scan_tasks.add(task)
    task.add_done_callback(_active_scan_tasks.discard)

    return ScanAccepted(
        scan_uuid=scan_uuid,
        project_name=p_name,
        project_path=p_path_display,
        status=ScanStatus.PENDING,
        started_at=datetime.now(timezone.utc),
        stream_url=f"/api/ws/scans/{scan_uuid}",
    )


async def _run_scan(
    *,
    scan_uuid: str,
    scan_id: int,
    project_id: int,
    project_path: str,
    branch: str | None,
    include_globs: list[str] | None,
    exclude_globs: list[str] | None,
) -> None:
    """Background task: run the scanner, persist results, publish progress.

    Progress events are published to WebSocket subscribers immediately,
    but the DB write is throttled (max 1/sec) to avoid N+1 connections.
    """
    logger.info("scan.run.start", extra={"event": "scan.run.start", "scan_uuid": scan_uuid})
    async with _db() as conn:
        await update_scan_status(conn, scan_id, ScanStatus.RUNNING.value)

    # Throttle: at most one DB write per second for progress events.
    # We still publish every event to WebSocket clients.
    last_db_write = [0.0]
    db_write_lock = asyncio.Lock()

    async def on_progress(progress) -> None:
        msg = {
            "type": "progress",
            "phase": progress.phase,
            "detail": progress.detail,
            "percent": round(progress.percent, 1),
            "ts": progress.ts.isoformat(),
        }
        bus.publish(scan_uuid, msg)
        # Throttle DB writes — we don't need every progress event in the DB
        # (the WebSocket already has them, and the report is the final state).
        now = asyncio.get_event_loop().time()
        if now - last_db_write[0] < 1.0:
            return
        async with db_write_lock:
            # Re-check after acquiring lock
            now = asyncio.get_event_loop().time()
            if now - last_db_write[0] < 1.0:
                return
            last_db_write[0] = now
            try:
                async with _db() as conn:
                    await record_event(
                        conn,
                        scan_id,
                        "progress",
                        f"[{progress.phase}] {progress.detail} ({progress.percent:.0f}%)",
                    )
            except Exception:  # nosec  # DB write failure; scan continues
                # Don't let DB errors abort the scan
                pass

    try:
        scanner = Scanner(on_progress=on_progress)
        report = await scanner.scan(
            project_path,
            opts=ScanOptions(
                branch=branch,
                include_globs=include_globs,
                exclude_globs=exclude_globs,
            ),
        )
        report.scan_uuid = scan_uuid

        # Persist
        async with _db() as conn:
            for run in report.runs:
                run_id = await save_analyzer_run(
                    conn,
                    scan_id,
                    run.name,
                    status=run.status.value,
                    findings=[f.model_dump(mode="json") for f in run.findings],
                    signals=run.signals,
                    score_value=run.score.value if run.score else None,
                    score_label=run.score.label if run.score else "",
                    started_at=run.started_at.isoformat() if run.started_at else "",
                    finished_at=run.finished_at.isoformat() if run.finished_at else "",
                    error_message=run.error_message,
                )
                await insert_findings(
                    conn,
                    run_id,
                    run.name,
                    [f.model_dump(mode="json") for f in run.findings],
                )
            summary = {
                "overall_health": report.overall_health,
                "overall_band": report.overall_band,
                "file_count": report.stats.get("file_count", 0),
                "loc_total": report.stats.get("loc_total", 0),
                "commit_count": report.stats.get("commit_count", 0),
                "finding_counts": report.stats.get("finding_counts", {}),
                "duration_ms": report.duration_ms,
            }
            await update_scan_status(
                conn,
                scan_id,
                ScanStatus.COMPLETED.value,
                report=json.loads(render_json(report)),
                summary=summary,
                finished=True,
            )
            await record_event(conn, scan_id, "log", "scan completed")

        bus.publish(
            scan_uuid,
            {
                "type": "done",
                "scan_uuid": scan_uuid,
                "overall_health": report.overall_health,
            },
        )
        logger.info(
            "scan.run.done",
            extra={
                "event": "scan.run.done",
                "scan_uuid": scan_uuid,
                "overall_health": report.overall_health,
                "duration_ms": report.duration_ms,
                "findings": len(report.findings),
            },
        )
        # Fire webhook (best-effort, never blocks)
        try:
            from mri.services.webhook import send_webhook
            await send_webhook(
                "scan_complete",
                {
                    "scan_uuid": scan_uuid,
                    "project_name": report.project.name,
                    "project_path": report.project.path,
                    "overall_health": report.overall_health,
                    "overall_band": report.overall_band,
                    "duration_ms": report.duration_ms,
                    "findings_count": len(report.findings),
                },
            )
        except Exception:  # nosec B110  # intentional
            pass  # webhook is best-effort  # nosec B110
    except asyncio.CancelledError:
        async with _db() as conn:
            await update_scan_status(
                conn,
                scan_id,
                ScanStatus.FAILED.value,
                error_message="scan cancelled by shutdown",
                finished=True,
            )
            await record_event(conn, scan_id, "error", "cancelled by shutdown")
        bus.publish(scan_uuid, {"type": "error", "message": "cancelled by shutdown"})
        logger.warning(
            "scan.run.cancelled",
            extra={"event": "scan.run.cancelled", "scan_uuid": scan_uuid},
        )
        try:
            from mri.services.webhook import send_webhook
            await send_webhook(
                "scan_failed",
                {"scan_uuid": scan_uuid, "error": "cancelled by shutdown"},
            )
        except Exception:  # nosec B110  # intentional
            pass  # nosec B110
        raise
    except Exception as exc:
        async with _db() as conn:
            await update_scan_status(
                conn,
                scan_id,
                ScanStatus.FAILED.value,
                error_message=str(exc),
                finished=True,
            )
            await record_event(conn, scan_id, "error", f"{type(exc).__name__}: {exc}")
        bus.publish(scan_uuid, {"type": "error", "message": str(exc)})
        logger.exception(
            "scan.run.failed",
            extra={"event": "scan.run.failed", "scan_uuid": scan_uuid},
        )
        try:
            from mri.services.webhook import send_webhook
            await send_webhook(
                "scan_failed",
                {"scan_uuid": scan_uuid, "error": str(exc)},
            )
        except Exception:  # nosec B110  # intentional
            pass


# ---------------------------------------------------------------------------  # nosec B110
# DB context for background tasks (cannot use Depends)
# ---------------------------------------------------------------------------


class _DBCtx:
    async def __aenter__(self):
        from mri.db.repository import get_connection
        self._cm = get_connection()
        self.conn = await self._cm.__aenter__()
        return self.conn

    async def __aexit__(self, *exc):
        await self._cm.__aexit__(*exc)


_db = _DBCtx


# ---------------------------------------------------------------------------
# GET /api/scans/{uuid}
# ---------------------------------------------------------------------------


@router.get("/scans/{scan_uuid}", response_model=dict)
async def get_scan(scan_uuid: str, conn: aiosqlite.Connection = Depends(db_conn)) -> dict:
    from mri.db.repository import get_scan_by_uuid, get_scan_runs

    # Validate uuid format
    if not _is_valid_uuid(scan_uuid):
        raise HTTPException(400, "invalid scan_uuid")

    row = await get_scan_by_uuid(conn, scan_uuid)
    if not row:
        raise HTTPException(404, "scan not found")
    runs = await get_scan_runs(conn, row["id"])
    out = {
        "scan_uuid": scan_uuid,
        "project_name": row["project_name"],
        "project_path": row["project_path"],
        "status": row["status"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "error_message": row["error_message"],
    }
    if row["report_json"] and row["status"] == "completed":
        out["report"] = json.loads(row["report_json"])
    elif row["summary_json"]:
        out["summary"] = json.loads(row["summary_json"])
    out["runs"] = [
        {
            "name": r["analyzer_name"],
            "status": r["status"],
            "started_at": r["started_at"],
            "finished_at": r["finished_at"],
            "score_value": r["score_value"],
            "score_label": r["score_label"],
            "error_message": r["error_message"],
            "findings_count": len(json.loads(r["findings_json"])),
        }
        for r in runs
    ]
    return out


# ---------------------------------------------------------------------------
# GET /api/scans
# ---------------------------------------------------------------------------


@router.get("/scans", response_model=ScanListResponse)
async def list_scans(
    limit: int = 50,
    conn: aiosqlite.Connection = Depends(db_conn),
) -> ScanListResponse:
    from mri.db.repository import list_scans

    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be between 1 and 500")
    rows = await list_scans(conn, limit=limit)
    return ScanListResponse(
        scans=[_to_scan_summary(r) for r in rows],
        count=len(rows),
    )


def _to_scan_summary(row: dict) -> ScanSummary:
    """Map a database row onto the public model.

    Deliberately explicit: the summary blob is written by this service, so a
    malformed one is a bug here rather than user input — but a listing must not
    500 because one old row failed to parse.
    """
    try:
        summary = json.loads(row.get("summary_json") or "{}")
    except (ValueError, TypeError):
        logger.warning(
            "scan.summary.unparsable",
            extra={"event": "scan.summary.unparsable", "scan_uuid": row.get("scan_uuid")},
        )
        summary = {}
    return ScanSummary(
        scan_uuid=row["scan_uuid"],
        project_name=row["project_name"],
        project_path=row["project_path"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row.get("finished_at"),
        duration_ms=summary.get("duration_ms"),
        overall_health=summary.get("overall_health"),
        overall_band=summary.get("overall_band", "fair"),
        file_count=summary.get("file_count", 0),
        loc_total=summary.get("loc_total", 0),
        commit_count=summary.get("commit_count", 0),
        finding_counts=summary.get("finding_counts", {}),
    )


# ---------------------------------------------------------------------------
# GET /api/projects
# ---------------------------------------------------------------------------


@router.get("/projects", response_model=ProjectListResponse)
async def list_projects(
    limit: int = 50,
    conn: aiosqlite.Connection = Depends(db_conn),
) -> ProjectListResponse:
    from mri.db.repository import list_projects

    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be between 1 and 500")
    rows = await list_projects(conn, limit=limit)
    return ProjectListResponse(
        projects=[ProjectSummary(**{k: r[k] for k in ProjectSummary.model_fields if k in r})
                  for r in rows],
        count=len(rows),
    )


# ---------------------------------------------------------------------------
# GET /api/scans/{uuid}/report.{html|json}
# ---------------------------------------------------------------------------


@router.get("/scans/{scan_uuid}/report.html")
async def get_report_html(scan_uuid: str, conn: aiosqlite.Connection = Depends(db_conn)) -> HTMLResponse:
    from mri.db.repository import get_scan_by_uuid

    if not _is_valid_uuid(scan_uuid):
        raise HTTPException(400, "invalid scan_uuid")
    row = await get_scan_by_uuid(conn, scan_uuid)
    if not row:
        raise HTTPException(404, "scan not found")
    if not row["report_json"]:
        raise HTTPException(409, "scan not completed yet")
    raw = json.loads(row["report_json"])
    report = Report.model_validate(raw)
    return HTMLResponse(render_html(report))


@router.get("/scans/{scan_uuid}/report.json")
async def get_report_json(scan_uuid: str, conn: aiosqlite.Connection = Depends(db_conn)) -> dict:
    from mri.db.repository import get_scan_by_uuid

    if not _is_valid_uuid(scan_uuid):
        raise HTTPException(400, "invalid scan_uuid")
    row = await get_scan_by_uuid(conn, scan_uuid)
    if not row:
        raise HTTPException(404, "scan not found")
    if not row["report_json"]:
        raise HTTPException(409, "scan not completed yet")
    return json.loads(row["report_json"])


# ---------------------------------------------------------------------------
# DELETE /api/scans/{uuid} — delete a scan (and its findings)
# ---------------------------------------------------------------------------


@router.delete("/scans/{scan_uuid}")
async def delete_scan(
    scan_uuid: str,
    conn: aiosqlite.Connection = Depends(db_conn),
) -> dict:
    """Delete a scan and all its findings. Idempotent."""
    if not _is_valid_uuid(scan_uuid):
        raise HTTPException(400, "invalid scan_uuid")
    cur = await conn.execute("SELECT id FROM scans WHERE scan_uuid = ?", (scan_uuid,))
    row = await cur.fetchone()
    if row is None:
        return {"ok": True, "deleted": False}
    scan_id = row[0]
    await conn.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
    await conn.commit()
    return {"ok": True, "deleted": True, "scan_uuid": scan_uuid}


# ---------------------------------------------------------------------------
# GET /api/scans/{a}/diff/{b} — compare two scans
# ---------------------------------------------------------------------------


@router.get("/scans/{a}/diff/{b}")
async def diff_scans(
    a: str,
    b: str,
    conn: aiosqlite.Connection = Depends(db_conn),
) -> dict:
    """Compare two scans: what changed in scores, findings, stats.

    Returns a structured diff suitable for rendering in the dashboard.
    """
    if not (_is_valid_uuid(a) and _is_valid_uuid(b)):
        raise HTTPException(400, "invalid scan_uuid")
    from mri.db.repository import get_scan_by_uuid

    row_a = await get_scan_by_uuid(conn, a)
    row_b = await get_scan_by_uuid(conn, b)
    if not row_a or not row_b:
        raise HTTPException(404, "scan not found")
    if not row_a["report_json"] or not row_b["report_json"]:
        raise HTTPException(409, "one or both scans not completed")
    # Scans must be from the same project
    if row_a["project_id"] != row_b["project_id"]:
        raise HTTPException(400, "scans are from different projects")

    rep_a = json.loads(row_a["report_json"])
    rep_b = json.loads(row_b["report_json"])

    # Score diff
    scores_a = {s["label"]: s for s in rep_a.get("scores", [])}
    scores_b = {s["label"]: s for s in rep_b.get("scores", [])}
    score_diff = []
    for label in sorted(set(scores_a) | set(scores_b)):
        va = scores_a.get(label, {}).get("value", 0)
        vb = scores_b.get(label, {}).get("value", 0)
        score_diff.append({
            "label": label,
            "before": va,
            "after": vb,
            "delta": round(vb - va, 1),
        })

    # Finding diff (by title within same analyzer)
    def _fingerprint(f: dict) -> str:
        return f"{f.get('analyzer_name', '')}:{f.get('category', '')}:{f.get('title', '')}"

    findings_a = {_fingerprint(f): f for f in rep_a.get("findings", [])}
    findings_b = {_fingerprint(f): f for f in rep_b.get("findings", [])}
    added = list(findings_b.keys() - findings_a.keys())
    removed = list(findings_a.keys() - findings_b.keys())
    # Present in both — check if severity changed
    changed = []
    for fp in findings_a.keys() & findings_b.keys():
        fa, fb = findings_a[fp], findings_b[fp]
        if fa.get("severity") != fb.get("severity"):
            changed.append({
                "title": fb.get("title", ""),
                "category": fb.get("category", ""),
                "analyzer": fb.get("analyzer_name", ""),
                "before_severity": fa.get("severity"),
                "after_severity": fb.get("severity"),
            })

    # Stats diff
    stats_a = rep_a.get("stats", {})
    stats_b = rep_b.get("stats", {})

    return {
        "before": {
            "scan_uuid": a,
            "started_at": rep_a.get("started_at"),
            "finished_at": rep_a.get("finished_at"),
            "overall_health": rep_a.get("overall_health"),
            "overall_band": rep_a.get("overall_band"),
        },
        "after": {
            "scan_uuid": b,
            "started_at": rep_b.get("started_at"),
            "finished_at": rep_b.get("finished_at"),
            "overall_health": rep_b.get("overall_health"),
            "overall_band": rep_b.get("overall_band"),
        },
        "score_diff": score_diff,
        "findings": {
            "added": [findings_b[k] for k in added[:100]],
            "removed": [findings_a[k] for k in removed[:100]],
            "severity_changed": changed,
        },
        "stats_diff": {
            "file_count": stats_b.get("file_count", 0) - stats_a.get("file_count", 0),
            "loc_total": stats_b.get("loc_total", 0) - stats_a.get("loc_total", 0),
            "commit_count": stats_b.get("commit_count", 0) - stats_a.get("commit_count", 0),
        },
    }


# ---------------------------------------------------------------------------
# GET /api/scans/{uuid}/report.sarif — SARIF for CI integration
# ---------------------------------------------------------------------------


@router.get("/scans/{scan_uuid}/report.sarif")
async def get_report_sarif(
    scan_uuid: str,
    conn: aiosqlite.Connection = Depends(db_conn),
) -> Response:
    """Export a scan as SARIF 2.1.0 for integration with GitHub Code Scanning,
    GitLab Code Quality, VS Code, etc."""
    if not _is_valid_uuid(scan_uuid):
        raise HTTPException(400, "invalid scan_uuid")
    from mri.db.repository import get_scan_by_uuid

    row = await get_scan_by_uuid(conn, scan_uuid)
    if not row:
        raise HTTPException(404, "scan not found")
    if not row["report_json"]:
        raise HTTPException(409, "scan not completed yet")
    raw = json.loads(row["report_json"])
    report = Report.model_validate(raw)
    sarif = _to_sarif(report)
    return Response(
        content=json.dumps(sarif, indent=2),
        media_type="application/sarif+json",
    )


def _to_sarif(report: Report) -> dict:
    """Convert a Report to SARIF 2.1.0 format.

    SARIF is the OASIS standard for static analysis output. Supported by
    GitHub Code Scanning, GitLab Code Quality, Azure DevOps, IDEs, etc.
    """
    severity_to_sarif_level = {
        "info": "note",
        "low": "note",
        "medium": "warning",
        "high": "error",
        "critical": "error",
    }
    runs = []
    for run in report.runs:
        results = []
        for f in run.findings:
            results.append({
                "ruleId": f.category,
                "level": severity_to_sarif_level.get(f.severity.value, "warning"),
                "message": {"text": f.description or f.title},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": f.target_path or "."},
                        "region": {"startLine": 1},
                    },
                }] if f.target_path else [],
                "properties": {
                    "analyzer": run.name,
                    "severity": f.severity.value,
                    "score": f.score,
                    "title": f.title,
                    "category": f.category,
                },
            })
        runs.append({
            "tool": {
                "driver": {
                    "name": "project-mri",
                    "version": __version__,
                    "informationUri": "https://github.com/project-mri/project-mri",
                    "rules": [
                        {
                            "id": f.category,
                            "name": f.category,
                            "shortDescription": {"text": f.title},
                            "helpUri": "https://github.com/project-mri/project-mri",
                        }
                        for f in run.findings
                    ],
                },
            },
            "results": results,
        })

    # If there are no runs but there are top-level findings, emit a single run
    if not runs and report.findings:
        results = []
        for f in report.findings:
            results.append({
                "ruleId": f.category,
                "level": severity_to_sarif_level.get(f.severity.value, "warning"),
                "message": {"text": f.description or f.title},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": f.target_path or "."},
                        "region": {"startLine": 1},
                    },
                }] if f.target_path else [],
                "properties": {
                    "analyzer": "project-mri",
                    "severity": f.severity.value,
                    "score": f.score,
                    "title": f.title,
                    "category": f.category,
                },
            })
        runs.append({
            "tool": {
                "driver": {
                    "name": "project-mri",
                    "version": __version__,
                    "informationUri": "https://github.com/project-mri/project-mri",
                    "rules": [
                        {
                            "id": f.category,
                            "name": f.category,
                            "shortDescription": {"text": f.title},
                            "helpUri": "https://github.com/project-mri/project-mri",
                        }
                        for f in report.findings
                    ],
                },
            },
            "results": results,
        })

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": runs,
    }


# ---------------------------------------------------------------------------
# WebSocket /api/ws/scans/{uuid}
# ---------------------------------------------------------------------------


@router.websocket("/ws/scans/{scan_uuid}")
async def scan_progress_ws(ws: WebSocket, scan_uuid: str) -> None:
    if not _is_valid_uuid(scan_uuid):
        await ws.close(code=1008, reason="invalid uuid")
        return
    await ws.accept()
    q = await bus.subscribe(scan_uuid)
    try:
        await ws.send_json({"type": "hello", "scan_uuid": scan_uuid})
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=15)
                await ws.send_json(msg)
                if msg.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass  # nosec B110
    except Exception:
        logger.exception(
            "ws.error",
            extra={"event": "ws.error", "scan_uuid": scan_uuid},
        )
    finally:
        await bus.unsubscribe(scan_uuid, q)
        try:
            await ws.close()
        except Exception:  # nosec  # close on already-closed socket is fine
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_valid_uuid(value: str) -> bool:
    """We use 32-char hex UUIDs (no dashes)."""
    return isinstance(value, str) and bool(_UUID_RE.match(value))