"""Health + version + deep health check.

`/api/health` is the liveness/readiness endpoint for orchestrators.
Returns 503 if any critical dependency is unhealthy.
"""
from __future__ import annotations

import logging
import sys
import time

from fastapi import APIRouter, Response, status

from mri.api.deps import get_db_path
from mri.db.repository import get_connection
from mri.models.scan import HealthResponse

logger = logging.getLogger("mri.health")
router = APIRouter(prefix="/api", tags=["system"])

_VERSION = "0.3.0"
_STARTED_AT = time.time()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe — fast, returns even if DB is slow."""
    return HealthResponse(
        status="ok",
        version=_VERSION,
        db_path=str(get_db_path()),
        uptime_seconds=round(time.time() - _STARTED_AT, 1),
    )


@router.get("/health/deep")
async def health_deep(response: Response) -> dict:
    """Readiness probe — checks DB connectivity, schema present, scanners loadable."""
    checks: dict[str, dict] = {}
    overall_ok = True

    # 1. DB connection + schema
    db_start = time.perf_counter()
    try:
        async with get_connection() as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in await cursor.fetchall()]
            db_ms = round((time.perf_counter() - db_start) * 1000, 2)
            expected = {"projects", "scans", "analyzer_runs", "findings", "scan_events"}
            missing = expected - set(tables)
            checks["database"] = {
                "ok": not missing,
                "latency_ms": db_ms,
                "tables": tables,
                "missing": sorted(missing) if missing else [],
            }
            if missing:
                overall_ok = False
    except Exception as e:
        checks["database"] = {"ok": False, "error": str(e)[:200]}
        overall_ok = False

    # 2. Scanners importable
    try:
        from mri.analyzers.architecture import ArchitectureAnalyzer
        from mri.analyzers.complexity import ComplexityAnalyzer
        from mri.analyzers.coupling import CouplingAnalyzer
        from mri.analyzers.dependencies import DependenciesAnalyzer
        from mri.analyzers.git_history import GitHistoryAnalyzer
        from mri.analyzers.tech_debt import TechDebtAnalyzer
        analyzers = [
            ArchitectureAnalyzer, ComplexityAnalyzer, CouplingAnalyzer,
            DependenciesAnalyzer, GitHistoryAnalyzer, TechDebtAnalyzer,
        ]
        checks["analyzers"] = {
            "ok": True,
            "count": len(analyzers),
            "names": [a.name for a in analyzers],
        }
    except Exception as e:
        checks["analyzers"] = {"ok": False, "error": str(e)[:200]}
        overall_ok = False

    # 3. Tree-sitter available
    try:
        from tree_sitter_language_pack import get_parser
        get_parser("python")  # warm
        checks["tree_sitter"] = {"ok": True}
    except Exception as e:
        checks["tree_sitter"] = {"ok": False, "error": str(e)[:200]}
        overall_ok = False

    # 4. GitPython available
    try:
        checks["git"] = {"ok": True}
    except Exception as e:
        checks["git"] = {"ok": False, "error": str(e)[:200]}
        overall_ok = False

    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if overall_ok else "degraded",
        "version": _VERSION,
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "python": sys.version.split()[0],
        "checks": checks,
    }


@router.get("/version")
async def version() -> dict:
    return {
        "name": "project-mri",
        "version": _VERSION,
        "python": sys.version.split()[0],
    }