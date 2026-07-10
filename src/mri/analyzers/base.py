"""Base analyzer interface.

Every analyzer is a small async unit that:
  1. takes a ScanContext (project path, branch, file list)
  2. computes Findings + a Score (named, ranged, traced)
  3. returns an AnalyzerRun
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mri.models.scan import AnalyzerRun, Finding, ScanStatus, Score


@dataclass(slots=True)
class ScanContext:
    """Everything an analyzer needs to do its job.

    `files` is the pre-walked file list (path, language, size_bytes, loc).
    `git` is the GitPython Repo instance — ready for log/blame/etc.
    """

    project_path: Path
    branch: str
    files: list[dict[str, Any]]
    git: Any  # git.Repo — kept untyped to avoid hard dep here
    include_globs: list[str] | None = None
    exclude_globs: list[str] | None = None

    def is_excluded(self, path: str) -> bool:
        from fnmatch import fnmatch

        if self.exclude_globs:
            return any(fnmatch(path, g) for g in self.exclude_globs)
        return False


class BaseAnalyzer(ABC):
    """Base class for all 6 analyzers."""

    name: str = "unnamed"
    description: str = ""
    score_label: str = "unnamed_score"
    # Higher weight = more impact on overall_health.
    weight: float = 1.0

    def __init__(self) -> None:
        self.run = AnalyzerRun(name=self.name)

    @abstractmethod
    async def analyze(self, ctx: ScanContext) -> AnalyzerRun:
        """Run the analyzer. Mutates self.run and returns it."""
        ...

    # Convenience helpers --------------------------------------------------

    def _start(self) -> None:
        self.run.status = ScanStatus.RUNNING
        self.run.started_at = datetime.now(timezone.utc)

    def _finish_ok(self) -> None:
        self.run.status = ScanStatus.COMPLETED
        self.run.finished_at = datetime.now(timezone.utc)
        if self.run.started_at and self.run.finished_at:
            self.run.duration_ms = int(
                (self.run.finished_at - self.run.started_at).total_seconds() * 1000
            )

    def _finish_err(self, message: str) -> None:
        self.run.status = ScanStatus.FAILED
        self.run.error_message = message
        self.run.finished_at = datetime.now(timezone.utc)
        if self.run.started_at and self.run.finished_at:
            self.run.duration_ms = int(
                (self.run.finished_at - self.run.started_at).total_seconds() * 1000
            )

    def _add_finding(self, **kwargs: Any) -> None:
        # Clamp score to 0..100 to satisfy Pydantic validation
        if "score" in kwargs and kwargs["score"] is not None:
            kwargs["score"] = max(0.0, min(100.0, float(kwargs["score"])))
        self.run.findings.append(Finding(**kwargs))

    def _set_score(self, value: float, contributors: list[str]) -> None:
        self.run.score = Score(
            label=self.score_label,
            value=round(value, 1),
            band=Score.band_for(value),
            contributors=contributors,
        )