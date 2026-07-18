"""API middleware: auth, rate limit, security headers, request logging."""
from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from functools import lru_cache
from importlib.resources import files as _pkg_files

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from mri.logging_setup import clear_request_id, set_request_id
from mri.security import check_api_key, is_auth_enabled, sanitize_for_log

logger = logging.getLogger("mri.middleware")

# A base64-encoded sha256 digest: 43 chars of the base64 alphabet plus padding.
_SHA256_B64 = re.compile(r"sha256-[A-Za-z0-9+/]{43}=")


@lru_cache(maxsize=1)
def _dashboard_script_hashes() -> tuple[str, ...]:
    """sha256 hashes of the dashboard's inline bootstrap scripts.

    Written by apps/dashboard/scripts/embed.mjs at build time. Empty when the
    dashboard was never built, in which case the strict policy simply stands.
    """
    try:
        manifest = (
            _pkg_files("mri")
            .joinpath("_frontend", "dashboard", "csp-script-hashes.json")
        )
        if manifest.is_file():
            loaded = json.loads(manifest.read_text(encoding="utf-8"))
            # Validate the full shape, not just the prefix: these values are
            # interpolated into a CSP header, so anything containing a quote or
            # space could smuggle in an extra directive.
            return tuple(h for h in loaded if isinstance(h, str) and _SHA256_B64.fullmatch(h))
    except (OSError, ValueError, ModuleNotFoundError, NotADirectoryError):
        logger.warning("dashboard CSP manifest unreadable; keeping strict script-src")
    return ()

# Paths that don't require auth (health, openapi, demo data, auth endpoints, dashboard)
PUBLIC_PATHS = frozenset({
    "/",
    "/api/health",
    "/api/health/deep",
    "/api/version",
    "/api/openapi.json",
    "/api/docs",
    "/api/redoc",
    "/docs/oauth2-redirect",
    "/healthz",
    "/api/demo/report.html",
    "/api/demo/report.json",
    "/api/demo/scan",
    "/api/demo/feed",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/status",
    "/dashboard",
    "/dashboard/",
})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to every response."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        resp = await call_next(request)
        # Prevent MIME-sniffing
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        # Prevent clickjacking
        resp.headers.setdefault("X-Frame-Options", "DENY")
        # Referrer policy
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        # Disable powerful features
        resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        # HSTS — only meaningful over HTTPS, but harmless in dev
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        # CSP — restrict to same-origin (we don't load external scripts).
        # The embedded dashboard is a Next.js export that bootstraps through
        # inline <script> tags. Those are allowed by exact sha256 hash (emitted
        # at build time by apps/dashboard/scripts/embed.mjs) and only on the
        # /dashboard path — never 'unsafe-inline', and never for the API.
        script_src = "'self'"
        if request.url.path.startswith("/dashboard"):
            hashes = _dashboard_script_hashes()
            if hashes:
                script_src += " " + " ".join(f"'{h}'" for h in hashes)
        csp = (
            "default-src 'self'; "
            f"script-src {script_src}; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' ws: wss:; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        resp.headers.setdefault("Content-Security-Policy", csp)
        return resp


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Set request ID, log request + response, measure latency."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = set_request_id()
        start = time.perf_counter()
        from mri import metrics as _metrics
        _metrics.HTTP_INFLIGHT.inc()
        client = request.client
        client_ip = client.host if client else "-"
        method = request.method
        path = request.url.path
        # Sanitize path before logging
        safe_path = sanitize_for_log(path)
        logger.info(
            "request.start",
            extra={
                "event": "request.start",
                "method": method,
                "path": safe_path,
                "client_ip": client_ip,
            },
        )
        try:
            resp = await call_next(request)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request.error",
                extra={
                    "event": "request.error",
                    "method": method,
                    "path": safe_path,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "error": str(exc),
                },
            )
            raise
        finally:
            clear_request_id()
        elapsed_ms = (time.perf_counter() - start) * 1000
        resp.headers["X-Request-ID"] = rid
        logger.info(
            "request.end",
            extra={
                "event": "request.end",
                "method": method,
                "path": safe_path,
                "status": resp.status_code,
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )
        # Record metrics (skip /metrics endpoint itself to avoid noise)
        if path != "/metrics":
            try:
                from mri.api.metrics_routes import record_http_metrics
                await record_http_metrics(request, resp, elapsed_ms / 1000)
            except Exception as e:
                logger.debug("metrics.record_failed", extra={"error": str(e)})
        return resp


class AuthMiddleware(BaseHTTPMiddleware):
    """Reject unauthenticated requests when API keys are configured.

    Public paths are always allowed.
    Authentication can be provided via:
      Authorization: Bearer <key>     (legacy API key OR JWT)
      X-API-Key: <key>                (legacy API key)
      Cookie: mri_session             (session JWT from login)
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if not is_auth_enabled():
            return await call_next(request)

        path = request.url.path
        if path in PUBLIC_PATHS or path.startswith("/api/demo/") or path.startswith("/dashboard"):
            return await call_next(request)

        # Extract credentials
        token = None
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        if not token:
            token = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
        if not token:
            # Try session cookie
            from mri.config import get_config
            cookie_name = get_config().get("auth", {}).get("session_cookie_name", "mri_session")
            token = request.cookies.get(cookie_name)

        # Accept either a legacy API key or a valid JWT
        accepted = False
        if token:
            # JWT path: 3 dot-separated parts
            if token.count(".") == 2:
                from mri.auth.users import get_user_by_id, verify_token
                claims = verify_token(token)
                if claims is not None:
                    user = get_user_by_id(int(claims["sub"]))
                    if user is not None:
                        accepted = True
            if not accepted and check_api_key(token):
                accepted = True

        if not accepted:
            client = request.client
            client_ip = client.host if client else "-"
            logger.warning(
                "auth.failed",
                extra={
                    "event": "auth.failed",
                    "path": sanitize_for_log(path),
                    "client_ip": client_ip,
                    "key_provided": bool(token),
                },
            )
            return JSONResponse(
                {"detail": "Unauthorized", "hint": "Set MRI_API_KEYS env var and pass via Authorization: Bearer <key>, or log in via the dashboard to get a JWT."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory token bucket rate limiter.

    Limits per client IP, sliding window. Defaults:
      - 60 requests / 60 seconds for general API
      - 5 requests / 60 seconds for scan start
    """

    def __init__(self, app, *, per_minute: int = 60, scan_per_minute: int = 5) -> None:
        super().__init__(app)
        self.per_minute = per_minute
        self.scan_per_minute = scan_per_minute
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._scans: dict[str, list[float]] = defaultdict(list)
        # Timestamps inside a bucket expire, but the IP keys themselves used to
        # live forever: one request from an address that never returned left an
        # entry for the process's lifetime. On a public-facing server that grows
        # without bound, so stale keys are swept once per window.
        self._last_sweep = time.time()

    def _sweep_expired(self, now: float, window: float) -> None:
        """Drop IP keys with nothing inside the window. Runs once per window."""
        if now - self._last_sweep < window:
            return
        self._last_sweep = now
        for bucket in (self._hits, self._scans):
            for ip in [k for k, v in bucket.items() if not any(now - t < window for t in v)]:
                del bucket[ip]

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        client = request.client
        ip = client.host if client else "-"
        path = request.url.path
        # Skip rate limit for public/demo/health/docs/dashboard paths
        if path in { "/", "/api/health", "/api/version", "/api/openapi.json",
                     "/api/docs", "/api/redoc", "/docs/oauth2-redirect",
                     "/healthz" } or path.startswith("/api/demo/") \
                     or path.startswith("/dashboard"):
            return await call_next(request)
        # Determine the limit for this request
        is_scan = path.endswith("/scans") and request.method == "POST"
        bucket = self._scans if is_scan else self._hits
        limit = self.scan_per_minute if is_scan else self.per_minute
        window = 60.0
        now = time.time()
        self._sweep_expired(now, window)
        # Drop expired entries for this address; the sweep above removes keys
        # for addresses that stopped calling entirely.
        bucket[ip] = [t for t in bucket.get(ip, ()) if now - t < window]
        if len(bucket[ip]) >= limit:
            retry_after = max(1, int(window - (now - bucket[ip][0])))
            logger.warning(
                "ratelimit.exceeded",
                extra={
                    "event": "ratelimit.exceeded",
                    "client_ip": ip,
                    "path": sanitize_for_log(request.url.path),
                    "limit": limit,
                    "window_seconds": window,
                },
            )
            return JSONResponse(
                {"detail": "Too Many Requests", "retry_after_seconds": retry_after},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        bucket[ip].append(now)
        return await call_next(request)


# ---------- Body-size guard ----------


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests with bodies larger than MRI_MAX_REQUEST_BYTES."""

    def __init__(self, app, *, max_bytes: int = 1024 * 1024) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > self.max_bytes:
            return JSONResponse(
                {"detail": "Request body too large", "max_bytes": self.max_bytes},
                status_code=413,
            )
        return await call_next(request)