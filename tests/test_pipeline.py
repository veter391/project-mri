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


def test_ast_cache_is_budgeted_by_source_size(tmp_path: Path, caplog, monkeypatch):
    """A file-count budget let 5,000 trees hold ~950 MiB while the content cache
    beside it allowed 64 MiB. Trees are budgeted by the source they came from,
    and exhausting a budget is announced rather than silently degrading."""
    import logging

    monkeypatch.setattr(ScanContext, "TREE_SOURCE_BUDGET_CHARS", 200)
    ctx = ScanContext(project_path=tmp_path, branch="main", files=[], git=None)

    body = "import os\n" * 40  # ~400 chars, over the shrunken budget on the 2nd file
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).write_text(body, encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        trees = [ctx.parse_tree(n, "python") for n in ("a.py", "b.py", "c.py")]

    assert all(t is not None for t in trees), "parsing must still work past the budget"
    assert len(ctx._trees) < 3, "the budget did not stop retention"
    assert any("budget_exhausted" in r.message for r in caplog.records), (
        "the cache stopped retaining without saying so"
    )


async def test_a_stuck_analyzer_does_not_hang_the_scan(tmp_path: Path, monkeypatch):
    """The tool scans repositories supplied by whoever calls the API. Nothing
    bounded how long one file could keep a parser busy, so a stuck analyzer held
    a scan slot with no recovery short of restarting the process."""
    import time

    class Wedged(_Stub):
        name = "wedged"

        def analyze(self, ctx: ScanContext) -> None:  # type: ignore[override]
            self._start()
            time.sleep(5)  # longer than the budget below
            self._set_score(100.0, ["never reached"])
            self._finish_ok()

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(Scanner, "ANALYZER_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(Scanner, "ANALYZERS", [Wedged, _analyzer("fine")])

    started = time.perf_counter()
    report = await Scanner().scan(str(tmp_path))
    elapsed = time.perf_counter() - started

    assert elapsed < 4, f"the scan waited {elapsed:.1f}s on a wedged analyzer"
    wedged = next(r for r in report.runs if r.name == "wedged")
    assert "timed out" in (wedged.error_message or ""), "the timeout was not recorded"
    # The rest of the scan still produced a report rather than failing outright.
    assert any(r.name == "fine" and r.score is not None for r in report.runs)
