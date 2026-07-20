"""Golden-baseline regression (Rebuild Phase 0.3 / 11.2).

Scan the fixed fixture repo and compare the analysis to the committed baseline.
An unintended change to any analyzer's numbers fails here. When a change IS
intended, regenerate: `MRI_UPDATE_GOLDEN=1 pytest tests/test_golden.py -q`, then
record the delta in tests/golden/README.md before committing the new baseline.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from mri.services.report_generator import render_json
from mri.services.scanner import Scanner, ScanOptions
from tests.golden import BASELINE, build_fixture_repo, canonical


def _scan_fixture(tmp_path: Path) -> str:
    repo = build_fixture_repo(tmp_path / "fixture")
    report = asyncio.run(Scanner().scan(str(repo), opts=ScanOptions()))
    return canonical(json.loads(render_json(report)))


def test_scanner_output_matches_the_golden_baseline(tmp_path: Path):
    current = _scan_fixture(tmp_path)

    if os.environ.get("MRI_UPDATE_GOLDEN"):
        BASELINE.write_text(current + "\n", encoding="utf-8")
        return

    assert BASELINE.exists(), (
        "no golden baseline committed; generate it with "
        "`MRI_UPDATE_GOLDEN=1 pytest tests/test_golden.py`"
    )
    expected = BASELINE.read_text(encoding="utf-8").strip()
    assert current == expected, (
        "scanner output drifted from the golden baseline. If this change is "
        "intentional, regenerate with `MRI_UPDATE_GOLDEN=1 pytest "
        "tests/test_golden.py` and document the delta in tests/golden/README.md."
    )
