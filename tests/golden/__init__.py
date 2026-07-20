"""Golden baseline for the scanner (Rebuild Phase 0.3 / 11.2).

A fixed, deterministic fixture repository is scanned and its report compared to
a committed reference, so an unintended change to any analyzer's numbers fails
CI loudly. Intentional metric changes are made by regenerating the baseline
(`MRI_UPDATE_GOLDEN=1 pytest tests/test_golden.py`) and documenting the delta in
this folder's README.

Determinism is engineered, not hoped for:

* Fixture files are written with an explicit ``\n`` newline, so the byte content
  — and therefore every line-based metric — is identical on Windows and Linux.
* Commits use fixed author/committer dates, so commit SHAs and any time-derived
  metric are stable run to run.
* Volatile runtime fields (timestamps, durations, the scan UUID, the absolute
  repo path) are scrubbed before comparison, and path separators are normalised,
  so only the *analysis* is compared, not the environment it ran in.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

BASELINE = Path(__file__).parent / "baseline_report.json"

#: Fields whose value depends on when/where the scan ran, not on the analysis.
_VOLATILE = {
    "started_at", "finished_at", "created_at", "scanned_at",
    "duration_ms", "scan_uuid", "path",
}


def _git(repo: Path, *args: str, date: str | None = None) -> None:
    import os

    env = None
    if date is not None:
        env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False, env=env)


def _write(path: Path, text: str) -> None:
    # Explicit \n: no platform newline translation, so line counts match on every OS.
    path.write_text(text, encoding="utf-8", newline="\n")


def build_fixture_repo(root: Path) -> Path:
    """A small, fixed Python repo with two commits — the golden subject.

    Deliberately varied so several analyzers have something to say: a branch,
    a nested function, a growing file (churn), and a second module.
    """
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _write(root / "app.py", "def a():\n    return 1\n\n\ndef b(x):\n    if x:\n        return x * 2\n    return 0\n")
    _write(root / "util.py", "# util\nX = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init", date="2026-01-01T00:00:00Z")
    _write(root / "app.py", "def a():\n    return 1\n\n\ndef b(x):\n    if x:\n        return x * 2\n    return 0\n\n\ndef c():\n    return 3\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "add c", date="2026-01-02T00:00:00Z")
    return root


def normalize(report: dict) -> dict:
    """Scrub volatile fields and normalise path separators, in place-ish."""
    def scrub(o: object) -> object:
        if isinstance(o, dict):
            for k in list(o):
                if k in _VOLATILE:
                    o[k] = "<volatile>"
                elif isinstance(o[k], str):
                    o[k] = o[k].replace("\\", "/")
                else:
                    scrub(o[k])
        elif isinstance(o, list):
            for x in o:
                scrub(x)
        return o

    return scrub(json.loads(json.dumps(report)))  # deep copy, then scrub


def canonical(report_json: dict) -> str:
    return json.dumps(normalize(report_json), indent=2, sort_keys=True)
