"""Evaluation harness — validate the fusion numbers against known ground truth.

The product's whole claim is that its numbers are honest. This layer proves it:
a labeled corpus with constructed ground truth, metrics measuring how close the
computed answer is, and an over-claim guard that fails if the product ever claims
more than its evidence supports. The guard is a hard assertion; the metrics are a
calibration report.
"""
from __future__ import annotations

from mri.eval.corpus import LabeledCase, build_calibration_case
from mri.eval.guard import Violation, audit_project
from mri.eval.runner import EvalReport, run_eval

__all__ = [
    "EvalReport",
    "LabeledCase",
    "Violation",
    "audit_project",
    "build_calibration_case",
    "run_eval",
]
