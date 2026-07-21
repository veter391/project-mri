"""The HTML report carries fusion provenance when a run has produced it (9.2).

The static report showed scores and findings but nothing about who authored the
risky files. When fusion explanations are passed, an "AI provenance & decisions"
section renders from their prose; without them (the scan-time default, before any
fusion) the report is exactly as before.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from mri.services.report_generator import render_html
from mri.services.scanner import Scanner, ScanOptions
from tests.golden import build_fixture_repo

_PROSE = "88% of its current lines are AI-authored, traced to 2 agent sessions."


def _real_report(tmp_path: Path):
    repo = build_fixture_repo(tmp_path / "repo")
    return asyncio.run(Scanner().scan(str(repo), opts=ScanOptions()))


def test_fusion_section_renders_when_explanations_are_present(tmp_path: Path):
    report = _real_report(tmp_path)
    html = render_html(report, fusion=[{"file": "app.py", "prose": _PROSE}])
    assert "AI provenance" in html
    assert _PROSE in html
    assert "app.py" in html


def test_no_fusion_section_without_explanations(tmp_path: Path):
    report = _real_report(tmp_path)
    html = render_html(report)
    assert "AI provenance" not in html
    assert "top findings" in html  # the rest of the report still renders


def test_html_is_escaped_no_stored_xss(tmp_path: Path):
    """The template is loaded as report.html.j2, whose .j2 suffix defeated
    select_autoescape and left every {{ }} raw — a stored-XSS path for an
    adversarial filename or commit subject reaching the report. Autoescape is now
    forced on; a script payload in the fusion prose/file must render escaped."""
    report = _real_report(tmp_path)
    html = render_html(report, fusion=[
        {"file": "x<b>.py", "prose": "<script>alert('xss')</script>"},
    ])
    assert "<script>alert('xss')</script>" not in html
    assert "&lt;script&gt;" in html
    assert "x&lt;b&gt;.py" in html
