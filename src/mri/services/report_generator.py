"""Report generator — render Report → HTML and JSON."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from mri.models.scan import Report

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


@lru_cache(maxsize=1)
def _build_env() -> Environment:
    """The Jinja environment, built once.

    It used to be rebuilt on every render, which recreated the loader and
    recompiled the template each time — measured at 9.5 ms per report versus
    0.009 ms once cached. Jinja's template cache lives on the Environment, so
    discarding it threw away the very thing that makes rendering fast.
    """
    return Environment(
        # Force autoescape: select_autoescape keys on the filename extension, and
        # the template is "report.html.j2" — which ends in .j2, not .html, so the
        # extension heuristic left escaping OFF and every {{ }} rendered raw HTML.
        # This env renders only that one HTML report, so escaping everything is
        # correct and closes a stored-XSS path (a repo filename or commit subject
        # reaching the report unescaped).
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html(report: Report, fusion: list[dict] | None = None) -> str:
    """Render the static report. `fusion`, when given, is a list of
    ``{"file", "prose"}`` entries — the per-file AI-provenance explanation from a
    fusion run — rendered as an extra section. Absent (the scan-time default,
    before any fusion), the report is exactly as before."""
    template = _build_env().get_template("report.html.j2")
    return template.render(report=report, fusion=fusion)


def render_json(report: Report) -> str:
    return report.model_dump_json(indent=2, exclude_none=True)


def write_report_files(report: Report, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{report.scan_uuid or 'demo'}.html"
    json_path = out_dir / f"{report.scan_uuid or 'demo'}.json"
    html_path.write_text(render_html(report), encoding="utf-8")
    json_path.write_text(render_json(report), encoding="utf-8")
    return {"html": html_path, "json": json_path}