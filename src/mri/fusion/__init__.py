"""Fusion analysis: turning the ingested session data into risk annotations.

The fusion *tables* (models/fusion.py, db/fusion_repository.py) and their
*ingest* (ingest/) are separate; this package is the analysis on top of them.
It reads what ingest stored and produces answers the base scan cannot, because
the base scan never sees a session log.

It covers authorship-weighted risk, decision provenance, and the consequence
loop.
"""
from __future__ import annotations

from mri.fusion.authorship import (
    AuthorshipEvidence,
    WeightedRisk,
    authorship_evidence_for,
    weight_hotspots,
)
from mri.fusion.consequences import measure_consequence, measure_decision_consequences
from mri.fusion.correlation import CorrelationResult, correlate_touches_to_commits
from mri.fusion.decisions import ingest_adrs, ingest_commits, parse_adr
from mri.fusion.line_authorship import compute_file_authorship, persist_file_authorship

__all__ = [
    "AuthorshipEvidence",
    "CorrelationResult",
    "WeightedRisk",
    "authorship_evidence_for",
    "compute_file_authorship",
    "correlate_touches_to_commits",
    "ingest_adrs",
    "ingest_commits",
    "measure_consequence",
    "measure_decision_consequences",
    "parse_adr",
    "persist_file_authorship",
    "weight_hotspots",
]
