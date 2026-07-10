"""Demo endpoints — instant fake scan for showcase without a real repo.

Production-hardened: slug validation, structured logging.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from mri.security import validate_slug
from mri.services.demo_feed import generate_demo_report
from mri.services.report_generator import render_html, render_json

logger = logging.getLogger("mri.demo")
router = APIRouter(prefix="/api/demo", tags=["demo"])


def _make_report(slug: str):
    r = generate_demo_report(slug)
    r.scan_uuid = "demo-" + slug
    return r


@router.get("/scan")
async def demo_scan(slug: str = "my-legacy-app") -> JSONResponse:
    try:
        slug = validate_slug(slug)
    except ValueError as e:
        raise HTTPException(400, str(e))
    report = _make_report(slug)
    return JSONResponse(json.loads(render_json(report)))


@router.get("/report.html", response_class=HTMLResponse)
async def demo_report_html(slug: str = "my-legacy-app") -> HTMLResponse:
    try:
        slug = validate_slug(slug)
    except ValueError as e:
        raise HTTPException(400, str(e))
    report = _make_report(slug)
    return HTMLResponse(render_html(report))


@router.get("/report.json")
async def demo_report_json(slug: str = "my-legacy-app") -> JSONResponse:
    try:
        slug = validate_slug(slug)
    except ValueError as e:
        raise HTTPException(400, str(e))
    report = _make_report(slug)
    return JSONResponse(json.loads(render_json(report)))


@router.get("/feed")
async def demo_feed(slug: str = "my-legacy-app") -> dict:
    try:
        slug = validate_slug(slug)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "slug": slug,
        "lines": [
            f"$ project-mri analyze ./{slug} --output ./report.html",
            "→ loading configuration...",
            "→ git history analyzer · 4,812 commits parsed",
            "→ tree-sitter · 247 files · 18,452 functions",
            "→ dependency graph · 1,247 edges · 8 cycles",
            "→ coupling_evolution_score = 38/100 (high churn · 6 modules)",
            "→ architecture_health = 71/100",
            "→ technical_debt_index = 23/100",
            "→ bus_factor = 4 · knowledge_islands = 2 modules",
            f"→ report saved → ./{slug}-report.html (4.2 MB · self-contained)",
            "$ open ./report.html",
            "→ completed in 20.4s · 0 telemetry events",
        ],
    }