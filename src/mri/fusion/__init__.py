"""Fusion analysis: turning the ingested session data into risk annotations.

The fusion *tables* (models/fusion.py, db/fusion_repository.py) and their
*ingest* (ingest/) are separate; this package is the analysis on top of them.
It reads what ingest stored and produces answers the base scan cannot, because
the base scan never sees a session log.

Today that is authorship-weighted risk. Decision provenance and the consequence
loop will live here too.
"""
from __future__ import annotations

from mri.fusion.authorship import (
    AuthorshipEvidence,
    WeightedRisk,
    authorship_evidence_for,
    weight_hotspots,
)
from mri.fusion.consequences import measure_consequence, measure_decision_consequences
from mri.fusion.decisions import ingest_adrs, ingest_commits, parse_adr

__all__ = [
    "AuthorshipEvidence",
    "WeightedRisk",
    "authorship_evidence_for",
    "ingest_adrs",
    "ingest_commits",
    "measure_consequence",
    "measure_decision_consequences",
    "parse_adr",
    "weight_hotspots",
]
