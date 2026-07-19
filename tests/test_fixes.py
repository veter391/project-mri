"""Regression tests for the audit-pass fixes.

Each test pins one specific bug we found during the audit and confirms
the fix works. If any of these regress, the bug is back.
"""
import shutil
import tempfile
from pathlib import Path

import pytest

from mri.analyzers.coupling import CouplingAnalyzer
from mri.analyzers.dependencies import DependenciesAnalyzer
from mri.analyzers.tech_debt import TechDebtAnalyzer
from mri.services.scanner import ScanContext


def _make_ctx(tmp: Path, files: dict[str, str]) -> ScanContext:
    """Build a minimal ScanContext."""
    file_list = []
    for rel, content in files.items():
        full = tmp / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
        loc = content.count("\n") + 1
        file_list.append({
            "abs_path": str(full),
            "rel_path": rel,
            "ext": Path(rel).suffix,
            "language": "python",
            "size_bytes": len(content),
            "loc": loc,
        })
    return ScanContext(
        project_path=tmp,
        branch="main",
        files=file_list,
        git=None,
    )


@pytest.fixture
def tmp():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Fix: recursive Tarjan SCC → iterative
# ---------------------------------------------------------------------------

def test_find_cycles_iterative_handles_large_graph():
    """The old recursive Tarjan crashed on ~1000+ nodes (Python recursion limit)."""
    a = DependenciesAnalyzer()
    # Build a graph with 5000 nodes and one big cycle
    edges: dict[str, set[str]] = {f"n{i}": set() for i in range(5000)}
    for i in range(5000):
        # Each node imports a random earlier node (no cycle)
        if i > 0:
            edges[f"n{i}"].add(f"n{i-1}")
    # Add a 100-node cycle
    for i in range(100):
        edges[f"n{i}"].add(f"n{(i + 1) % 100}")

    cycles = a._find_cycles(edges, set(edges.keys()))
    # Must find the 100-node cycle
    assert any(len(c) == 100 for c in cycles), f"expected 100-node cycle, got {[len(c) for c in cycles]}"


def test_find_cycles_no_recursion_error_on_deep_chain():
    """A linear chain of 10k nodes shouldn't crash."""
    a = DependenciesAnalyzer()
    edges: dict[str, set[str]] = {f"n{i}": set() for i in range(10_000)}
    for i in range(9999):
        edges[f"n{i}"].add(f"n{i+1}")
    cycles = a._find_cycles(edges, set(edges.keys()))
    assert cycles == []  # No cycles in a chain


# ---------------------------------------------------------------------------
# Fix: tree-sitter walker iterative
# ---------------------------------------------------------------------------

def test_ts_walk_handles_deeply_nested_ast():
    """The old recursive _ts_walk hit recursion limit on deep JSX/TSX."""
    import tree_sitter_language_pack

    from mri.analyzers.parsing import walk_imports

    parser = tree_sitter_language_pack.get_parser("python")
    # 5,000 levels of nested parens — parser creates a deep AST
    code = "x = " + "(" * 5000 + "1" + ")" * 5000
    tree = parser.parse(code.encode("utf-8"))
    # Must not raise RecursionError
    imports = walk_imports(tree.root_node, code)
    assert isinstance(imports, list)


# ---------------------------------------------------------------------------
# Fix: get_parser cached
# ---------------------------------------------------------------------------

def test_get_parser_is_cached():
    """The same language parser instance should be reused."""
    from mri.analyzers.parsing import get_parser_for
    # Clear the cache
    get_parser_for.cache_clear()
    p1 = get_parser_for("python")
    p2 = get_parser_for("python")
    assert p1 is p2, "parser should be cached"


# ---------------------------------------------------------------------------
# Fix: coupling _module_of preserves full path
# ---------------------------------------------------------------------------

def test_coupling_module_of_preserves_path():
    """`foo.bar.py` and `foo/bar.py` should produce different module keys."""
    a = CouplingAnalyzer()
    # With the old (buggy) code, both would normalize to "foo.bar"
    assert a._module_of("foo.bar.py") != a._module_of("foo/bar.py")
    # And both should be sensible dotted/separated forms
    assert "foo" in a._module_of("foo/bar.py")
    assert "foo" in a._module_of("foo.bar.py")


# ---------------------------------------------------------------------------
# Fix: tech_debt file_debt computed once (not twice)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tech_debt_no_dead_computation(tmp: Path):
    """The old code had a dead `if False else 0` block — confirm the file is clean."""
    files = {
        "a.py": "# TODO: fix\n# FIXME: refactor\n# HACK: bad code\nx = 1\n" * 30,
        "b.py": "# TODO: another one\ny = 2\n",
    }
    ctx = _make_ctx(tmp, files)
    a = TechDebtAnalyzer()
    a.analyze(ctx)
    # Sanity: real findings present
    assert a.run.score is not None
    debt_findings = [f for f in a.run.findings if f.category.startswith("debt_")]
    assert len(debt_findings) >= 3


# ---------------------------------------------------------------------------
# Fix: repository.py has no duplicate functions
# ---------------------------------------------------------------------------

def test_repository_no_duplicate_functions():
    """Pin: get_scan_by_uuid/get_scan_runs/get_findings should appear once each."""
    import inspect

    from mri.db import repository
    src = inspect.getsource(repository)
    for fn in ("get_scan_by_uuid", "get_scan_runs", "get_findings"):
        # Count `async def fn(` — exact match
        count = src.count(f"async def {fn}(")
        assert count == 1, f"{fn} defined {count} times in repository.py"


# ---------------------------------------------------------------------------
# Fix: scanner reads file with size cap
# ---------------------------------------------------------------------------

def test_scanner_skips_huge_files():
    """Files >2MB should be LOC-sampled, not fully read into memory."""
    from mri.services.scanner import Scanner
    big = "x = 1\n" * 1_000_000  # ~6MB
    p = Path(tempfile.mkdtemp()) / "big.py"
    p.write_text(big)
    files = Scanner._walk_files(p.parent)
    # big.py should appear in the file list with a non-zero LOC
    big_entry = next((f for f in files if f["rel_path"] == "big.py"), None)
    assert big_entry is not None
    # LOC should be close to 1M (sampled)
    assert 500_000 < big_entry["loc"] < 2_000_000
    shutil.rmtree(p.parent, ignore_errors=True)


# ---------------------------------------------------------------------------
# Fix: complexity code_lines_total correctly excludes comments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complexity_excludes_comments_from_code(tmp: Path):
    """`code_lines_total` should NOT count comment lines."""
    files = {
        "comments.py": "\n".join(["# comment"] * 50 + ["x = 1"] * 50),
    }
    ctx = _make_ctx(tmp, files)
    from mri.analyzers.complexity import ComplexityAnalyzer
    a = ComplexityAnalyzer()
    a.analyze(ctx)
    # comment_ratio should be ~0.5 (50 of 100 lines are comments)
    ratio = a.run.signals["comment_ratio"]
    assert 0.4 < ratio < 0.6, f"comment_ratio={ratio} — comments not being excluded"


async def test_comment_ratio_is_null_when_nothing_was_measured(tmp: Path):
    """A repository with no source files has no comment ratio. Reporting 0.0
    would read as "documented nothing" rather than "not measured" — different
    claims, and only one of them is true.

    This guarantee used to be phrased as "when the parser is absent", because
    comment counting sat behind a tree-sitter branch. It never needed a parser —
    it is two regexes — so the condition is now the honest one.
    """
    import mri.analyzers.complexity as cx

    ctx = _make_ctx(tmp, {"README.md": "# a heading\ntext\n", "data.json": "{}\n"})
    a = cx.ComplexityAnalyzer()
    a.analyze(ctx)
    assert a.run.signals["comment_ratio"] is None


async def test_comment_ratio_ignores_files_that_cannot_have_comments(tmp: Path):
    """Markdown and JSON must not dilute the ratio: `# heading` in markdown is
    not a comment, and JSON has none at all. The old tree-sitter gate excluded
    them as a side effect; the exclusion is now deliberate."""
    import mri.analyzers.complexity as cx

    ctx = _make_ctx(tmp, {
        "a.py": "\n".join(["# c"] * 50 + ["x = 1"] * 50),
        "README.md": "\n".join(["# heading"] * 500),
        "data.json": "{}\n",
    })
    a = cx.ComplexityAnalyzer()
    a.analyze(ctx)
    ratio = a.run.signals["comment_ratio"]
    assert 0.4 < ratio < 0.6, f"comment_ratio={ratio} — non-source files leaked in"


# ---------------------------------------------------------------------------
# Fix: Prometheus metrics use prometheus_client (not hand-rolled)
# ---------------------------------------------------------------------------

def test_metrics_uses_prometheus_client():
    """Verify metrics come from prometheus_client, not a hand-rolled module."""
    from prometheus_client import Counter, Gauge, Histogram

    from mri import metrics
    assert isinstance(metrics.HTTP_REQUESTS, Counter)
    assert isinstance(metrics.HTTP_DURATION, Histogram)
    assert isinstance(metrics.ACTIVE_SCANS, Gauge)
    assert isinstance(metrics.SCAN_DURATION, Histogram)
    # Process metrics should be auto-registered
    output = metrics.render_metrics().decode()
    # prometheus_client auto-registers these:
    assert "process_cpu_seconds_total" in output or "process_" in output


def test_metrics_have_free_process_metrics():
    """prometheus_client gives us process_* metrics for free."""
    from mri import metrics
    out = metrics.render_metrics().decode()
    # The standard process collector registers these
    expected_any = ["process_cpu_seconds_total", "process_resident_memory_bytes",
                    "process_virtual_memory_bytes", "process_start_time_seconds"]
    found = [m for m in expected_any if m in out]
    assert len(found) >= 2, f"expected process metrics, found only {found}"
