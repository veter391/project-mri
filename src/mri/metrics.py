"""Prometheus metrics — uses the official prometheus_client library.

This gives us:
- Battle-tested exposition format (scrape-compatible with every Prometheus version)
- Free process metrics (memory, CPU, GC, open fds) via ProcessCollector
- Free Python runtime metrics (GC, file descriptors) via PlatformCollector
- Multi-process support for gunicorn via PROMETHEUS_MULTIPROC_DIR

The previous hand-rolled version worked but lacked these out-of-the-box.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client import REGISTRY as _DEFAULT_REGISTRY

if TYPE_CHECKING:
    from fastapi import Request, Response

# ---------------------------------------------------------------------------
# Registry — we use the default registry so ProcessCollector / GC collector
# register automatically. If you need isolated metrics (testing), pass a
# fresh CollectorRegistry to the metrics below.
# ---------------------------------------------------------------------------

REGISTRY: CollectorRegistry = _DEFAULT_REGISTRY

# Histogram buckets in seconds — chosen for HTTP + scan workloads.
# Wide enough to cover slow API calls, fine-grained enough for fast endpoints.
_HTTP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
_SCAN_BUCKETS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)


# ---------------------------------------------------------------------------
# HTTP metrics
# ---------------------------------------------------------------------------

HTTP_REQUESTS = Counter(
    "mri_http_requests_total",
    "Total HTTP requests received",
    ["method", "path", "status"],
    registry=REGISTRY,
)
HTTP_DURATION = Histogram(
    "mri_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=_HTTP_BUCKETS,
    registry=REGISTRY,
)
HTTP_INFLIGHT = Gauge(
    "mri_http_inflight_requests",
    "In-flight HTTP requests",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Scan metrics
# ---------------------------------------------------------------------------

SCANS_STARTED = Counter(
    "mri_scans_started_total",
    "Total scans started",
    ["source"],  # local | url
    registry=REGISTRY,
)
SCANS_COMPLETED = Counter(
    "mri_scans_completed_total",
    "Total scans completed",
    ["status"],  # completed | failed
    registry=REGISTRY,
)
SCAN_DURATION = Histogram(
    "mri_scan_duration_seconds",
    "Scan duration in seconds",
    buckets=_SCAN_BUCKETS,
    registry=REGISTRY,
)
FINDINGS_TOTAL = Counter(
    "mri_findings_total",
    "Total findings emitted across all scans",
    ["analyzer", "severity"],
    registry=REGISTRY,
)
ACTIVE_SCANS = Gauge(
    "mri_active_scans",
    "Number of scans currently running",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Process metrics (constant after startup)
# ---------------------------------------------------------------------------

PROCESS_STARTED_AT = Gauge(
    "mri_process_started_at_seconds",
    "Unix timestamp when the server started",
    registry=REGISTRY,
)


def init_process_metrics() -> None:
    """Set process-level metrics that are constant after startup."""
    PROCESS_STARTED_AT.set(time.time())


def render_metrics() -> bytes:
    """Render all metrics in Prometheus text format.

    Returns bytes (not str) because generate_latest() returns bytes.
    Includes process_*, python_gc_*, etc. for free.
    """
    return generate_latest(REGISTRY)


def render_metrics_with_content_type() -> tuple[bytes, str]:
    """Render metrics with the correct Content-Type for the response."""
    return render_metrics(), CONTENT_TYPE_LATEST


# ---------------------------------------------------------------------------
# HTTP middleware integration helper
# ---------------------------------------------------------------------------


def record_http(request: Request, response: Response, elapsed: float) -> None:
    """Update HTTP metrics for a request/response pair. Used by middleware."""
    # Import here to avoid circular import (middleware imports metrics)
    from mri.api.metrics_routes import _normalize_path

    path = _normalize_path(request.url.path)
    HTTP_REQUESTS.labels(
        method=request.method,
        path=path,
        status=str(response.status_code),
    ).inc()
    HTTP_DURATION.labels(method=request.method, path=path).observe(elapsed)


__all__ = [
    "REGISTRY",
    "HTTP_REQUESTS",
    "HTTP_DURATION",
    "HTTP_INFLIGHT",
    "SCANS_STARTED",
    "SCANS_COMPLETED",
    "SCAN_DURATION",
    "FINDINGS_TOTAL",
    "ACTIVE_SCANS",
    "PROCESS_STARTED_AT",
    "init_process_metrics",
    "render_metrics",
    "render_metrics_with_content_type",
    "record_http",
]

