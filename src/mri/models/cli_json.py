"""Typed JSON shapes for the CLI's ``--json-out`` exports (Phase 9.1).

The `mri fusion` and `mri eval` commands used to hand-build their JSON dicts,
which drifted from the reports they described (a new report field was easy to
forget in the dict). These Pydantic models are the single source of truth for
those payloads: the command maps its report onto the model and dumps it, so the
JSON validates against a schema and cannot silently omit a field.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class FusionFactorJson(BaseModel):
    name: str
    value: object = None


class FusionFileJson(BaseModel):
    file: str
    prose: str
    factors: list[FusionFactorJson] = Field(default_factory=list)


class FusionIngestJson(BaseModel):
    sessions: int
    touches: int


class FusionCorrelationJson(BaseModel):
    linked: int
    commits: int
    #: Write touches with a time but no later commit — a real state, reported
    #: rather than hidden (mirrors CorrelationResult.uncommitted).
    uncommitted: int


class FusionDecisionsJson(BaseModel):
    adr: int
    commit: int
    cross_links: int


class FusionJson(BaseModel):
    """The `mri fusion --json-out` payload."""

    ingest: FusionIngestJson
    correlation: FusionCorrelationJson
    decisions: FusionDecisionsJson
    authored_files: int
    files: list[FusionFileJson] = Field(default_factory=list)


class CalibrationEntryJson(BaseModel):
    expected: float
    computed: float
    error: float


class ViolationJson(BaseModel):
    rule: str
    detail: str
    ref: str


class EvalJson(BaseModel):
    """The `mri eval --json-out` payload."""

    case: str
    calibration: dict[str, CalibrationEntryJson] = Field(default_factory=dict)
    correlation_recall: float
    consequence_false_positive_rate: float
    violations: list[ViolationJson] = Field(default_factory=list)
    passed: bool
