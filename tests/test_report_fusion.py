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
from mri.services.scanner import ScanOptions, Scanner
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
