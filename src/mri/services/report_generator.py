"""Report generator — render Report → HTML and JSON."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

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
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html(report: Report) -> str:
    template = _build_env().get_template("report.html.j2")
    return template.render(report=report)


def render_json(report: Report) -> str:
    return report.model_dump_json(indent=2, exclude_none=True)


def write_report_files(report: Report, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{report.scan_uuid or 'demo'}.html"
    json_path = out_dir / f"{report.scan_uuid or 'demo'}.json"
    html_path.write_text(render_html(report), encoding="utf-8")
    json_path.write_text(render_json(report), encoding="utf-8")
    return {"html": html_path, "json": json_path}