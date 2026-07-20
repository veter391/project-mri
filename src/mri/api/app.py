"""FastAPI app factory.

Wires:
- Structured logging
- Security middleware (headers, request context, auth, rate limit, body size)
- CORS (locked down via env)
- Routes
- Lifespan events (startup/shutdown for graceful scan cancellation)
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from mri import __version__
from mri.api.metrics_routes import router as metrics_router
from mri.api.middleware import (
    AuthMiddleware,
    MaxBodySizeMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from mri.api.routes import demo as demo_routes
from mri.api.routes import fusion as fusion_routes
from mri.api.routes import health as health_routes
from mri.api.routes import scans as scans_routes
from mri.auth import router as auth_router
from mri.logging_setup import setup_logging
from mri.security import get_cors_origins, get_max_request_bytes

logger = logging.getLogger("mri.app")


# ---------------------------------------------------------------------------
# Lifespan — graceful shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Set up structured logging on startup, drain on shutdown."""
    setup_logging()
    from mri import metrics as _metrics
    _metrics.init_process_metrics()
    logger.info(
        "app.startup",
        extra={
            "event": "app.startup",
            "version": __version__,
            "cors_origins": get_cors_origins() or "(disabled)",
            "auth_enabled": bool(os.environ.get("MRI_API_KEYS", "").strip()),
            "rate_limit_per_min": int(os.environ.get("MRI_RATE_LIMIT", "60")),
        },
    )
    try:
        yield
    finally:
        logger.info("app.shutdown", extra={"event": "app.shutdown"})
        # Best-effort: tell the scans module to stop accepting new work.
        try:
            from mri.api.routes.scans import shutdown as scans_shutdown
            await scans_shutdown()
        except Exception as e:  # pragma: no cover
            logger.warning(
                "shutdown.scans_error",
                extra={"event": "shutdown.scans_error", "error": str(e)},
            )


def create_app() -> FastAPI:
    app = FastAPI(
        title="project-mri",
        version=__version__,
        description=(
            "Local-first codebase intelligence. "
            "Analyzes Git history, architecture, dependencies, complexity, "
            "tech debt, and coupling — then produces an explainable report."
        ),
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # ---- Middleware (order matters: outermost first) ----
    # 1. Security headers (wraps everything)
    app.add_middleware(SecurityHeadersMiddleware)
    # 2. Request context (sets request_id, logs start/end)
    app.add_middleware(RequestContextMiddleware)
    # 3. Body size cap (before auth/rate so we don't waste auth cycles)
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=get_max_request_bytes())
    # 4. Rate limit
    rate = int(os.environ.get("MRI_RATE_LIMIT", "60"))
    scan_rate = int(os.environ.get("MRI_SCAN_RATE_LIMIT", "5"))
    app.add_middleware(RateLimitMiddleware, per_minute=rate, scan_per_minute=scan_rate)
    # 5. Auth (only kicks in when MRI_API_KEYS is set)
    app.add_middleware(AuthMiddleware)
    # 6. CORS — only allow configured origins
    cors_origins = get_cors_origins()
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["authorization", "x-api-key", "content-type"],
            max_age=600,
        )

    # ---- Error handlers ----
    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Don't leak internal paths or stack traces in error responses.
        return JSONResponse(
            {"detail": exc.detail if isinstance(exc.detail, str) else "Error"},
            status_code=exc.status_code,
            headers=exc.headers or {},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Sanitize validation errors — never echo raw input back
        return JSONResponse(
            {"detail": "Invalid request payload", "errors_count": len(exc.errors())},
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "request.unhandled",
            extra={"event": "request.unhandled", "path": request.url.path},
        )
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    # ---- Routes ----
    app.include_router(health_routes.router)
    app.include_router(scans_routes.router)
    app.include_router(fusion_routes.router)
    app.include_router(demo_routes.router)
    app.include_router(auth_router)
    app.include_router(metrics_router)

    # ---- Self-hosted dashboard (static Next export, embedded in the package) ----
    # Built by apps/dashboard (Next `output: 'export'`, basePath /dashboard) and
    # copied into mri/_frontend/dashboard. Located via importlib.resources so it
    # resolves correctly from source AND from an installed wheel (the previous
    # __file__-relative walk broke once installed into site-packages).
    from importlib.resources import files as _pkg_files

    from fastapi.staticfiles import StaticFiles as _StaticFiles
    from starlette.exceptions import HTTPException as _HTTPException

    try:
        _dashboard_dir = _pkg_files("mri").joinpath("_frontend").joinpath("dashboard")
        _has_dashboard = _dashboard_dir.joinpath("index.html").is_file()
    except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError):
        _has_dashboard = False

    if _has_dashboard:
        class _SPAStaticFiles(_StaticFiles):
            """StaticFiles with SPA fallback: unknown routes serve index.html,
            missing assets (js/css/images) still 404."""

            async def get_response(self, path: str, scope):
                try:
                    return await super().get_response(path, scope)
                except _HTTPException as exc:
                    if exc.status_code == 404:
                        return await super().get_response("index.html", scope)
                    raise

        # The Next export self-references /dashboard/_next/..., which this mount
        # serves. Mounted after the /api routers so the API always wins.
        app.mount(
            "/dashboard",
            _SPAStaticFiles(directory=str(_dashboard_dir), html=True),
            name="dashboard",
        )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def root() -> str:
        return """<!doctype html>
<html><head><meta charset="UTF-8"><title>project-mri API</title>
<style>body{font-family:ui-monospace,monospace;background:#06080C;color:#F5F2EA;padding:48px;max-width:720px;margin:0 auto;}
a{color:#F4A847}</style></head><body>
<h1>◉ project-mri API</h1>
<p>Local-first codebase intelligence — backend.</p>
<ul>
  <li><a href="/api/docs">/api/docs</a> — Swagger UI</li>
  <li><a href="/api/redoc">/api/redoc</a> — ReDoc</li>
  <li><a href="/api/health">/api/health</a> — health</li>
  <li><a href="/api/demo/report.html">/api/demo/report.html</a> — sample report</li>
  <li><a href="/api/demo/report.json">/api/demo/report.json</a> — sample report (JSON)</li>
  <li><a href="/api/scans">/api/scans</a> — all scans</li>
  <li><a href="/api/projects">/api/projects</a> — all projects</li>
</ul>
<p>POST /api/scans with <code>{"project_path": "/abs/path"}</code> to start a scan.</p>
<p>WebSocket: <code>/api/ws/scans/&lt;uuid&gt;</code> for live progress.</p>
</body></html>"""

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"ok": True}

    return app


app = create_app()