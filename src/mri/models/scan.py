"""Pydantic models for scans, projects, findings, reports.

Every analyzer emits Findings; the Scanner composes them into a Report.
Reports are JSON-serializable end-to-end — we can render them to HTML later.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def weight(self) -> float:
        return {
            Severity.INFO: 0.1,
            Severity.LOW: 0.3,
            Severity.MEDIUM: 0.55,
            Severity.HIGH: 0.8,
            Severity.CRITICAL: 1.0,
        }[self]


class ScanStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Atomic types
# ---------------------------------------------------------------------------


class Finding(BaseModel):
    """One observable fact about a codebase.

    Every analyzer emits findings in this shape. The scoring engine reads
    severity + score; the UI reads title + description + target_path.
    """

    severity: Severity
    category: str = Field(..., description="e.g. hotspot, cycle, god_module")
    title: str
    description: str = ""
    target_path: str = ""
    target_symbol: str = ""
    score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Contribution to analyzer score (0..100). NULL = informational.",
    )
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("score")
    @classmethod
    def _clamp(cls, v: float | None) -> float | None:
        return None if v is None else max(0.0, min(100.0, v))


class Score(BaseModel):
    """One named health signal. Named, ranged, traced.

    `contributors` is the breakdown — what made the score what it is.
    No black boxes. Every score explains itself.
    """

    label: str = Field(..., description="e.g. architecture_health, debt_index")
    value: float = Field(..., ge=0, le=100)
    band: Literal["excellent", "good", "fair", "poor", "critical"] = "fair"
    contributors: list[str] = Field(
        default_factory=list,
        description="Human-readable breakdown. Example: 'bus_factor = 4 (-18)'",
    )

    @classmethod
    def band_for(cls, value: float) -> Literal["excellent", "good", "fair", "poor", "critical"]:
        if value >= 85:
            return "excellent"
        if value >= 70:
            return "good"
        if value >= 50:
            return "fair"
        if value >= 30:
            return "poor"
        return "critical"


class AnalyzerRun(BaseModel):
    """One analyzer's result within a scan."""

    name: str
    status: ScanStatus = ScanStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    score: Score | None = None
    signals: dict[str, Any] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    error_message: str = ""


# ---------------------------------------------------------------------------
# Top-level report
# ---------------------------------------------------------------------------


class Project(BaseModel):
    path: str
    name: str
    default_branch: str = "main"


class ScanSummary(BaseModel):
    """Short version, for indexes and listing."""

    scan_uuid: str
    project_name: str
    project_path: str
    status: ScanStatus
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    overall_health: float | None = None
    overall_band: str = "fair"
    file_count: int = 0
    loc_total: int = 0
    commit_count: int = 0
    finding_counts: dict[str, int] = Field(default_factory=dict)


class Report(BaseModel):
    """Full MRI report. Everything you need to render a static HTML page."""

    scan_uuid: str
    project: Project
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None

    # Top-level scores (composed from analyzers)
    scores: list[Score] = Field(default_factory=list)
    overall_health: float = Field(..., ge=0, le=100)
    overall_band: str = "fair"

    # Per-analyzer detail
    runs: list[AnalyzerRun] = Field(default_factory=list)

    # Flattened findings (all analyzers combined) — for "show me the worst stuff"
    findings: list[Finding] = Field(default_factory=list)

    # Aggregate stats
    stats: dict[str, Any] = Field(default_factory=dict)

    # The explainability ledger: how overall_health was composed
    composition: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API request/response models
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    project_path: str = Field(..., description="Absolute path to the repo to scan")
    branch: str | None = None
    include_globs: list[str] | None = None
    exclude_globs: list[str] | None = None


class ScanAccepted(BaseModel):
    scan_uuid: str
    project_name: str
    project_path: str
    status: ScanStatus = ScanStatus.PENDING
    started_at: datetime
    stream_url: str


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    db_path: str
    uptime_seconds: float