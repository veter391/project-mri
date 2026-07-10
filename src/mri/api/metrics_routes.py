"""Metrics endpoint + middleware integration."""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Request, Response

from mri import metrics

logger = logging.getLogger("mri.metrics")
router = APIRouter(tags=["metrics"])


# Cardinality-safe path normalizer (replace UUIDs / numbers with placeholders)
_PATH_NORMALIZER = re.compile(r"(/api/scans)/[a-f0-9]{32}|/(?:[0-9]+)")


def _normalize_path(path: str) -> str:
    """Group dynamic segments to keep metric cardinality low.

    Example: /api/scans/abc123def456.../report.html
          → /api/scans/{id}/report.html
    """
    return _PATH_NORMALIZER.sub(r"\1/{id}", path)


@router.get("/metrics")
async def prometheus_metrics() -> Response:
    """Prometheus-compatible metrics endpoint.

    Includes standard mri_* metrics plus auto-registered:
    - process_* (CPU, memory, fds)
    - python_gc_* (garbage collection stats)
    """
    body, content_type = metrics.render_metrics_with_content_type()
    return Response(content=body, media_type=content_type)


# Backward-compat shim for the old middleware that called
# `record_http_metrics` directly. It now delegates to metrics.record_http.
async def record_http_metrics(request: Request, response: Response, elapsed: float) -> None:
    metrics.record_http(request, response, elapsed)
