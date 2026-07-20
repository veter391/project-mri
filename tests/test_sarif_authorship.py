"""SARIF carries fusion authorship (Rebuild Phase 9.4).

The base SARIF export shipped, but it dropped the moat: a CI reading it saw the
finding's score and nothing about who authored the file. When a fusion run has
computed a share, it now rides along in the finding's properties — a plain fact,
never a severity input.
"""
from __future__ import annotations

from datetime import datetime, timezone

from mri.api.routes.scans import _to_sarif
from mri.models.scan import Report


def _report() -> Report:
    return Report.model_validate({
        "scan_uuid": "u1",
        "project": {"name": "p", "path": "/p"},
        "started_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "overall_health": 80.0,
        "findings": [
            {"severity": "high", "category": "hotspot", "title": "churn",
             "target_path": "app.py", "score": 80},
            {"severity": "low", "category": "smell", "title": "x",
             "target_path": "clean.py", "score": 10},
        ],
    })


def _results_by_file(sarif: dict) -> dict:
    return {
        r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]: r
        for r in sarif["runs"][0]["results"]
    }


def test_authorship_share_rides_along_when_present():
    sarif = _to_sarif(_report(), authorship={
        "app.py": {"ai_authored_pct": 88, "unattributed_pct": 12,
                   "method": "blame_session_commit", "confidence": 0.9},
    })
    by_file = _results_by_file(sarif)
    share = by_file["app.py"]["properties"]["ai_authorship"]
    assert share["ai_authored_pct"] == 88
    assert share["method"] == "blame_session_commit"
    # A file with no computed share carries no fabricated authorship.
    assert "ai_authorship" not in by_file["clean.py"]["properties"]


def test_without_fusion_no_authorship_is_emitted():
    sarif = _to_sarif(_report())  # no fusion run has been done
    assert all(
        "ai_authorship" not in r["properties"]
        for r in sarif["runs"][0]["results"]
    )
