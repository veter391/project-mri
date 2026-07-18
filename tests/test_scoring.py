"""Score composition.

The rule these tests protect: a number the tool did not measure must never be
presented as an assessment of the user's code.
"""
from __future__ import annotations

from mri.models.scan import AnalyzerRun, ScanStatus, Score
from mri.scoring import UNMEASURED_VALUE, compose_overall


def _run(name: str, value: float | None, *, failed: bool = False) -> AnalyzerRun:
    run = AnalyzerRun(name=name)
    run.status = ScanStatus.FAILED if failed else ScanStatus.COMPLETED
    if value is not None:
        run.score = Score(label=f"{name}_health", value=value, band=Score.band_for(value))
    return run


def test_weighted_average_respects_weights():
    runs = [_run("a", 100.0), _run("b", 0.0)]
    composed = compose_overall(runs, {"a": 3.0, "b": 1.0})
    assert composed.value == 75.0
    assert composed.is_measured


def test_ledger_explains_every_contribution():
    runs = [_run("a", 80.0), _run("b", 40.0)]
    composed = compose_overall(runs, {"a": 1.0, "b": 1.0})
    assert len(composed.ledger) == 2
    assert all("weight" in line for line in composed.ledger)
    assert any("a_health = 80.0" in line for line in composed.ledger)


def test_a_failed_analyzer_is_excluded_not_scored_zero():
    """A crashed analyzer means 'not measured'. Counting it as zero would turn a
    tooling failure into a bad verdict about the user's code."""
    healthy = compose_overall([_run("a", 90.0)], {"a": 1.0})
    with_failure = compose_overall(
        [_run("a", 90.0), _run("b", None, failed=True)], {"a": 1.0, "b": 1.0}
    )
    assert with_failure.value == healthy.value == 90.0
    assert with_failure.unscored == ["b"]


def test_unscored_analyzers_are_named_in_the_ledger():
    composed = compose_overall(
        [_run("a", 90.0), _run("b", None, failed=True)], {"a": 1.0, "b": 1.0}
    )
    assert any("b = not measured" in line for line in composed.ledger)


def test_nothing_scored_is_reported_as_unmeasured():
    composed = compose_overall([_run("a", None, failed=True)], {"a": 1.0})
    assert composed.value == UNMEASURED_VALUE
    assert not composed.is_measured, "a placeholder must not claim to be a measurement"
    assert composed.ledger == []


def test_missing_weight_defaults_to_one():
    composed = compose_overall([_run("a", 60.0), _run("b", 80.0)], {})
    assert composed.value == 70.0


def test_score_carries_provenance_seams_for_the_authorship_layer():
    score = Score(label="risk", value=50.0)
    # Defaults must make no claim at all.
    assert score.decomposition == {}
    assert score.confidence is None
    assert score.causal_claim == "none"

    decomposed = Score(
        label="risk",
        value=50.0,
        decomposition={"ai": 40.0, "human": 35.0, "unattributed": 25.0},
        confidence=0.6,
        causal_claim="correlation",
    )
    assert sum(decomposed.decomposition.values()) == 100.0
    assert decomposed.causal_claim == "correlation"
