"""Analyzer pipeline shape.

Layers 5-8 of the engine are derived and temporal: risk decomposed by authorship
needs the git history, decision provenance needs authorship, and the consequence
loop compares one scan against an earlier one. A flat list of six equal peers
could express none of that, so these tests pin the ordering contract before
anything depends on it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mri.analyzers.base import BaseAnalyzer, ScanContext, Stage
from mri.services.scanner import Scanner


class _Stub(BaseAnalyzer):
    """Minimal analyzer that records that it ran."""

    def analyze(self, ctx: ScanContext) -> None:  # type: ignore[override]
        self._start()
        self._set_score(100.0, ["stub"])
        self._finish_ok()


def _analyzer(analyzer_name: str, *, stage: Stage = Stage.PRODUCER, requires: tuple = ()) -> type:
    return type(
        f"{analyzer_name.title()}Analyzer",
        (_Stub,),
        {"name": analyzer_name, "stage": stage, "requires": requires},
    )


def _names(classes: list[type]) -> list[str]:
    return [c.name for c in classes]


def test_producers_run_before_fusion():
    fusion = _analyzer("risk", stage=Stage.FUSION)
    producer = _analyzer("history")
    order = _names(Scanner._execution_order([fusion, producer]))
    assert order.index("history") < order.index("risk")


def test_dependencies_are_ordered_before_their_dependants():
    history = _analyzer("history")
    authorship = _analyzer("authorship", stage=Stage.FUSION, requires=("history",))
    decisions = _analyzer("decisions", stage=Stage.FUSION, requires=("authorship",))
    # Deliberately registered in the wrong order.
    order = _names(Scanner._execution_order([decisions, authorship, history]))
    assert order == ["history", "authorship", "decisions"]


def test_unknown_dependency_is_refused():
    """Better to fail loudly than to hand an analyzer an empty result and let it
    report a confident number built on nothing."""
    broken = _analyzer("risk", stage=Stage.FUSION, requires=("does_not_exist",))
    with pytest.raises(ValueError, match="does_not_exist"):
        Scanner._execution_order([broken])


def test_dependency_cycle_is_refused():
    a = _analyzer("a", stage=Stage.FUSION, requires=("b",))
    b = _analyzer("b", stage=Stage.FUSION, requires=("a",))
    with pytest.raises(ValueError, match="cycle"):
        Scanner._execution_order([a, b])


def test_the_shipped_analyzers_order_cleanly():
    order = _names(Scanner._execution_order(Scanner.ANALYZERS))
    assert len(order) == len(Scanner.ANALYZERS)
    assert set(order) == {a.name for a in Scanner.ANALYZERS}


async def test_results_are_published_for_downstream_analyzers(tmp_path: Path):
    """A derived analyzer reads its inputs from ctx.results rather than
    recomputing them."""
    seen: dict[str, object] = {}

    class Downstream(_Stub):
        name = "downstream"
        stage = Stage.FUSION
        requires = ("history",)

        def analyze(self, ctx: ScanContext) -> None:  # type: ignore[override]
            seen["history_run"] = ctx.results.get("history")
            super().analyze(ctx)

    history = _analyzer("history")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    scanner = Scanner()
    original = Scanner.ANALYZERS
    try:
        Scanner.ANALYZERS = [Downstream, history]  # type: ignore[assignment]
        await scanner.scan(str(tmp_path))
    finally:
        Scanner.ANALYZERS = original  # type: ignore[assignment]

    assert seen["history_run"] is not None, "downstream ran before its dependency published"
    assert seen["history_run"].name == "history"


def test_context_carries_seams_for_out_of_tree_inputs(tmp_path: Path):
    """Session logs live outside the scanned tree and the consequence loop needs
    earlier scans; both must have somewhere to go that is not a new field per
    layer."""
    ctx = ScanContext(project_path=tmp_path, branch="main", files=[], git=None)
    assert ctx.sources == {}
    assert ctx.previous_scans == []
    ctx.sources["claude_sessions"] = [{"id": "abc"}]
    ctx.previous_scans.append({"scan_uuid": "older"})
    assert ctx.sources["claude_sessions"][0]["id"] == "abc"
    assert ctx.previous_scans[0]["scan_uuid"] == "older"
