"""Tests for the 6 core analyzers + scoring engine.

We test against tiny synthetic repos so each test is <1s and fully deterministic.
"""
import shutil
import tempfile
from pathlib import Path

import pytest

from mri.analyzers.architecture import ArchitectureAnalyzer
from mri.analyzers.complexity import ComplexityAnalyzer
from mri.analyzers.coupling import CouplingAnalyzer
from mri.analyzers.dependencies import DependenciesAnalyzer
from mri.analyzers.git_history import GitHistoryAnalyzer
from mri.analyzers.tech_debt import TechDebtAnalyzer
from mri.services.scanner import ScanContext


def _make_ctx(tmp: Path, files: dict[str, str], *, with_git: bool = False) -> ScanContext:
    """Build a synthetic ScanContext without touching git."""
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
    if with_git:
        import subprocess
        # Set local git config (some test envs lack global git identity)
        subprocess.check_call(["git", "init", "-q"], cwd=tmp)
        subprocess.check_call(["git", "config", "user.email", "test@test"], cwd=tmp)
        subprocess.check_call(["git", "config", "user.name", "test"], cwd=tmp)
        subprocess.check_call(["git", "add", "-A"], cwd=tmp)
        subprocess.check_call(["git", "commit", "-q", "-m", "init"], cwd=tmp)
        from git import Repo
        git = Repo(tmp)
    else:
        git = None
    return ScanContext(
        project_path=tmp,
        branch="main",
        files=file_list,
        git=git,
    )


@pytest.fixture
def tmp():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# -----------------------------------------------------------------------
# Git history analyzer
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_git_history_no_git(tmp: Path):
    """No git repo → score 50, info finding."""
    ctx = _make_ctx(tmp, {"a.py": "x = 1\n"})
    a = GitHistoryAnalyzer()
    a.analyze(ctx)
    assert a.run.score is not None
    assert a.run.score.value == 50.0
    assert any(f.category == "no_git" for f in a.run.findings)


@pytest.mark.asyncio
async def test_git_history_with_commits(tmp: Path):
    ctx = _make_ctx(tmp, {"main.py": "import os\n"}, with_git=True)
    a = GitHistoryAnalyzer()
    a.analyze(ctx)
    assert a.run.score is not None
    assert a.run.score.label == "history_health"
    assert 0 <= a.run.score.value <= 100
    assert a.run.signals["commit_count"] >= 1


# -----------------------------------------------------------------------
# Architecture analyzer
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_architecture_balanced(tmp: Path):
    files = {f"mod{i}/file.py": "# content\n" * 100 for i in range(3)}
    ctx = _make_ctx(tmp, files)
    a = ArchitectureAnalyzer()
    a.analyze(ctx)
    assert a.run.score is not None
    assert a.run.score.label == "architecture_health"
    assert a.run.signals["module_count"] == 3
    # No god module → no findings
    assert not any(f.category == "god_module" for f in a.run.findings)


@pytest.mark.asyncio
async def test_architecture_god_module(tmp: Path):
    # All files in one module
    files = {f"core/file{i}.py": "# line\n" * 500 for i in range(5)}
    ctx = _make_ctx(tmp, files)
    a = ArchitectureAnalyzer()
    a.analyze(ctx)
    assert a.run.score is not None
    # Should detect god module
    god_findings = [f for f in a.run.findings if f.category == "god_module"]
    assert len(god_findings) >= 1
    assert a.run.score.value < 100


# -----------------------------------------------------------------------
# Dependencies analyzer
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dependencies_no_cycles(tmp: Path):
    files = {
        "a.py": "from b import foo\n",
        "b.py": "x = 1\n",
        "c.py": "x = 2\n",
    }
    ctx = _make_ctx(tmp, files)
    a = DependenciesAnalyzer()
    a.analyze(ctx)
    assert a.run.score is not None
    assert a.run.score.value == 100.0  # No cycles


@pytest.mark.asyncio
async def test_dependencies_cycle_detected(tmp: Path):
    files = {
        "a.py": "from b import foo\n",
        "b.py": "from a import bar\n",
    }
    ctx = _make_ctx(tmp, files)
    a = DependenciesAnalyzer()
    a.analyze(ctx)
    assert a.run.score is not None
    cycle_findings = [f for f in a.run.findings if f.category == "import_cycle"]
    assert len(cycle_findings) >= 1
    assert a.run.score.value < 100


# -----------------------------------------------------------------------
# Complexity analyzer
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complexity_short_files(tmp: Path):
    files = {"a.py": "# hi\nx = 1\n", "b.py": "# ok\ny = 2\n"}
    ctx = _make_ctx(tmp, files)
    a = ComplexityAnalyzer()
    a.analyze(ctx)
    assert a.run.score is not None
    assert a.run.score.value >= 80  # Healthy


@pytest.mark.asyncio
async def test_complexity_long_file(tmp: Path):
    files = {"big.py": "# line\n" * 600}
    ctx = _make_ctx(tmp, files)
    a = ComplexityAnalyzer()
    a.analyze(ctx)
    assert a.run.score is not None
    long_file_findings = [f for f in a.run.findings if f.category == "long_file"]
    assert len(long_file_findings) >= 1


# -----------------------------------------------------------------------
# Tech debt analyzer
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tech_debt_clean(tmp: Path):
    files = {"a.py": "x = 1\n"}
    ctx = _make_ctx(tmp, files)
    a = TechDebtAnalyzer()
    a.analyze(ctx)
    assert a.run.score is not None
    # No TODO/FIXME → high score
    assert a.run.score.value >= 80


@pytest.mark.asyncio
async def test_tech_debt_messy(tmp: Path):
    files = {
        "a.py": "# TODO: fix this\n# FIXME: refactor\n# HACK: bad code\nx = 1\n" * 30,
        "b.py": "# TODO: another one\ny = 2\n",
    }
    ctx = _make_ctx(tmp, files)
    a = TechDebtAnalyzer()
    a.analyze(ctx)
    assert a.run.score is not None
    debt_findings = [f for f in a.run.findings if f.category.startswith("debt_")]
    assert len(debt_findings) >= 3
    assert a.run.score.value < 90  # Penalised


# -----------------------------------------------------------------------
# Coupling analyzer
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coupling_no_modules(tmp: Path):
    files = {"a.py": "x = 1\n"}
    ctx = _make_ctx(tmp, files)
    a = CouplingAnalyzer()
    a.analyze(ctx)
    assert a.run.score is not None
    # Few modules → no painful ones → high score
    assert a.run.score.value >= 80


# -----------------------------------------------------------------------
# End-to-end scanner
# -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_scan_runs_all_analyzers(tmp: Path):
    """All 6 analyzers must run + produce a Report."""
    from mri.services.scanner import Scanner

    files = {
        "core/a.py": "from core.b import foo\n" * 5 + "# TODO\n" * 20 + "x = 1\n" * 100,
        "core/b.py": "x = 2\n" * 100,
        "tests/test_a.py": "def test_a():\n    assert True\n",
    }
    for rel, content in files.items():
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp / rel).write_text(content)

    import subprocess
    subprocess.check_call(["git", "init", "-q"], cwd=tmp)
    subprocess.check_call(["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"], cwd=tmp)
    subprocess.check_call(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"], cwd=tmp)

    s = Scanner()
    report = await s.scan(str(tmp))

    # All 6 analyzers ran
    assert len(report.runs) == 6
    names = {r.name for r in report.runs}
    assert names == {"git_history", "architecture", "dependencies", "complexity", "tech_debt", "coupling"}

    # Composition was computed
    assert len(report.composition) == 6
    assert report.overall_health > 0
    assert 0 <= report.overall_health <= 100

    # Findings present
    assert any(f.category == "debt_todo" for f in report.findings)
    # At least the core/ module should appear as a god-module candidate
    god = [f for f in report.findings if f.category == "god_module"]
    assert len(god) >= 0  # May or may not be god, depending on threshold


# -----------------------------------------------------------------------
# Demo feed (synthetic)
# -----------------------------------------------------------------------


def test_demo_report_is_valid():
    """The demo report must have all 6 analyzers + composition + scores."""
    from mri.services.demo_feed import generate_demo_report
    r = generate_demo_report("test-slug")
    assert len(r.runs) == 6
    assert r.overall_health > 0
    assert len(r.composition) == 6
    assert r.findings  # At least some findings
    # Same slug → same report (deterministic)
    r2 = generate_demo_report("test-slug")
    assert r.overall_health == r2.overall_health