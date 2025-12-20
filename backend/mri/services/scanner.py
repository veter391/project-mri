"""Scanner — orchestrates the analyzers and produces a Report.

Walks the project, builds the file inventory, then runs each analyzer in
sequence (could be parallel — left as a TODO if needed). Streams progress
events to subscribers via the callback hook.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from git import Repo as GitRepo
from git.exc import InvalidGitRepositoryError, NoSuchPathError

from mri.analyzers.architecture import ArchitectureAnalyzer
from mri.analyzers.base import BaseAnalyzer, ScanContext
from mri.analyzers.complexity import ComplexityAnalyzer
from mri.analyzers.coupling import CouplingAnalyzer
from mri.analyzers.dependencies import DependenciesAnalyzer
from mri.analyzers.git_history import GitHistoryAnalyzer
from mri.analyzers.tech_debt import TechDebtAnalyzer
from mri.models.scan import Project, Report

LANG_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".php": "php",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
}

EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "venv", ".venv",
    "__pycache__", "dist", "build", "target", ".next", ".nuxt", ".cache",
    ".idea", ".vscode", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "coverage", ".coverage", ".gradle",
}

# Top-level filename patterns that we count as project files
SOURCE_EXTS = set(LANG_BY_EXT.keys())


@dataclass(slots=True)
class ScanOptions:
    branch: str | None = None
    include_globs: list[str] | None = None
    exclude_globs: list[str] | None = None
    depth: int | None = None  # for shallow clone when scanning URL
    cleanup_clone: bool = True  # delete cached clone after scan


@dataclass
class ScanProgress:
    phase: str
    detail: str
    percent: float = 0.0
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


ProgressCallback = Callable[[ScanProgress], Awaitable[None]]


class Scanner:
    """The conductor. Use Scanner().scan(path) → Report."""

    ANALYZERS: list[type[BaseAnalyzer]] = [
        GitHistoryAnalyzer,
        ArchitectureAnalyzer,
        DependenciesAnalyzer,
        ComplexityAnalyzer,
        TechDebtAnalyzer,
        CouplingAnalyzer,
    ]

    def __init__(self, *, on_progress: ProgressCallback | None = None) -> None:
        self._on_progress = on_progress

    async def _emit(self, phase: str, detail: str, percent: float) -> None:
        if self._on_progress:
            await self._on_progress(ScanProgress(phase, detail, percent))

    async def scan(self, project_path: str, opts: ScanOptions | None = None) -> Report:
        """Run a scan on a local path.

        If `project_path` looks like a URL (https:// or git@), it will be
        cloned first. Otherwise, the path is treated as a local directory.

        Returns a Report. Raises ValueError on invalid paths.
        """
        opts = opts or ScanOptions()

        # Detect URL and clone
        clone_cleanup_path: Path | None = None
        if project_path.startswith(("https://", "http://", "git@")):
            from mri.services.repo_cloner import CloneError, clone_repo
            try:
                path = await asyncio.to_thread(
                    clone_repo,
                    project_path,
                    branch=opts.branch,
                    depth=opts.depth,
                )
                clone_cleanup_path = path
            except CloneError as e:
                raise ValueError(f"failed to clone repository: {e}") from e
        else:
            path = Path(project_path).expanduser().resolve()
            if not path.exists() or not path.is_dir():
                raise ValueError(f"Project path does not exist or is not a directory: {project_path}")

        await self._emit("init", f"opening {path}", 0)
        started = datetime.now(timezone.utc)

        # Build file inventory
        await self._emit("walk", "walking files", 5)
        files = await asyncio.to_thread(self._walk_files, path)
        await self._emit("walk", f"{len(files)} files", 10)

        # Open git
        git = await asyncio.to_thread(self._open_git, path)
        branch = opts.branch or (git.active_branch.name if git else "HEAD")
        await self._emit("git", f"branch = {branch}", 12)

        # Build scan context
        ctx = ScanContext(
            project_path=path,
            branch=branch,
            files=files,
            git=git,
            include_globs=opts.include_globs,
            exclude_globs=opts.exclude_globs,
        )

        # Run analyzers in parallel — they share ctx but don't mutate each other.
        # Total time = max(time_per_analyzer), not sum.
        async def run_one(Cls: type, i: int) -> Any:
            pct = 15 + (i * 75 / len(self.ANALYZERS))
            analyzer = Cls()
            await self._emit(
                "analyze",
                f"{analyzer.name} ({i + 1}/{len(self.ANALYZERS)})",
                pct,
            )
            try:
                await analyzer.analyze(ctx)
            except Exception as exc:
                # analyzers handle their own errors; this catches structural ones
                analyzer._finish_err(f"unhandled: {type(exc).__name__}: {exc}")
            return analyzer.run

        # Run all analyzers concurrently with gather — fail-soft via return_exceptions
        runs = await asyncio.gather(
            *[run_one(Cls, i) for i, Cls in enumerate(self.ANALYZERS)],
            return_exceptions=False,
        )

        # Compose report
        await self._emit("compose", "scoring", 92)
        report = self._compose_report(
            path=path,
            files=files,
            git=git,
            branch=branch,
            started=started,
            runs=runs,
        )
        # If this scan came from a URL, optionally clean up the cached clone
        if clone_cleanup_path is not None and opts.cleanup_clone:
            from mri.services.repo_cloner import cleanup_clone
            try:
                await asyncio.to_thread(cleanup_clone, project_path)
            except Exception:
                pass  # cleanup is best-effort  # nosec B110
        await self._emit("done", "report ready", 100)
        return report

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _walk_files(root: Path) -> list[dict[str, Any]]:
        """Synchronous file walk — runs in a thread.

        For files over MAX_LOC_READ_BYTES we count LOC by sampling the
        first chunk instead of reading the whole file. This keeps memory
        bounded and prevents OOM on accidentally-committed huge files
        (videos renamed .py, log files, etc.).
        """
        # Cap reads at 2 MiB — anything bigger is sampled.
        MAX_LOC_READ_BYTES = 2 * 1024 * 1024
        SAMPLE_SIZE = 64 * 1024  # 64 KiB sample
        out: list[dict[str, Any]] = []
        for child in root.rglob("*"):
            if not child.is_file():
                continue
            parts = child.relative_to(root).parts
            if any(p in EXCLUDE_DIRS for p in parts):
                continue
            ext = child.suffix.lower()
            if ext not in SOURCE_EXTS:
                continue
            try:
                size = child.stat().st_size
                rel = str(child.relative_to(root))
                if size == 0:
                    loc = 0
                elif size <= MAX_LOC_READ_BYTES:
                    # Small enough to read in one go
                    with child.open("rb") as f:
                        data = f.read()
                    loc = data.count(b"\n")
                    # If file doesn't end with newline, count the last line too
                    if data and not data.endswith(b"\n"):
                        loc += 1
                else:
                    # Sample-based estimate: count newlines in the first
                    # SAMPLE_SIZE bytes, then extrapolate. Accurate to ~5%
                    # for files with roughly uniform line length.
                    with child.open("rb") as f:
                        sample = f.read(SAMPLE_SIZE)
                    sample_loc = sample.count(b"\n")
                    if sample:
                        avg_line_len = SAMPLE_SIZE / max(sample_loc, 1)
                        loc = int(size / avg_line_len)
                    else:
                        loc = 0
                out.append({
                    "abs_path": str(child),
                    "rel_path": rel,
                    "ext": ext,
                    "language": LANG_BY_EXT.get(ext, "unknown"),
                    "size_bytes": size,
                    "loc": loc,
                })
            except (OSError, PermissionError):
                continue
        return out

    @staticmethod
    def _open_git(path: Path) -> GitRepo | None:
        try:
            return GitRepo(path)
        except (InvalidGitRepositoryError, NoSuchPathError):
            return None

    @staticmethod
    def _compose_report(
        *,
        path: Path,
        files: list[dict],
        git: GitRepo | None,
        branch: str,
        started: datetime,
        runs: list,
    ) -> Report:
        from mri import metrics as _metrics
        _metrics.ACTIVE_SCANS.dec()
        if runs:
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            _metrics.SCAN_DURATION.observe(elapsed)
            any_failed = any(r.status.value == "failed" for r in runs)
            status = "failed" if any_failed else "completed"
            _metrics.SCANS_COMPLETED.labels(status=status).inc(1)
            for run in runs:
                for f in run.findings:
                    sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
                    _metrics.FINDINGS_TOTAL.labels(analyzer=run.name, severity=sev).inc(1)
        from mri.models.scan import Score

        # Weight lookup (independent of analyzer instance — class-level attr)
        weight_map: dict[str, float] = {
            Cls.name: Cls.weight for Cls in Scanner.ANALYZERS
        }

        # Filter to runs with a score
        scored = [r for r in runs if r.score is not None]
        weighted_pairs = [
            (r.score.value, weight_map.get(r.name, 1.0)) for r in scored
        ]
        total_weight = sum(w for _, w in weighted_pairs) or 1.0

        # Weighted overall health
        weighted_sum = sum(v * w for v, w in weighted_pairs)
        overall = weighted_sum / total_weight if weighted_pairs else 50.0

        # Composition ledger
        composition = [
            f"{r.score.label} = {r.score.value} (weight {round(weight_map.get(r.name, 1.0) / total_weight, 2)})"
            for r in scored
        ]

        # Aggregate findings
        findings = []
        finding_counts: dict[str, int] = {}
        for r in runs:
            for f in r.findings:
                findings.append(f)
                sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
                finding_counts[sev] = finding_counts.get(sev, 0) + 1

        findings.sort(key=lambda f: -(f.score or 0))

        # Stats
        total_loc = sum(f["loc"] for f in files)
        per_lang: dict[str, dict] = {}
        for f in files:
            lang = f["language"]
            per_lang.setdefault(lang, {"files": 0, "loc": 0})
            per_lang[lang]["files"] += 1
            per_lang[lang]["loc"] += f["loc"]

        # Commit count from git_history signals
        commit_count = 0
        gh = next((r for r in runs if r.name == "git_history"), None)
        if gh and gh.signals:
            commit_count = gh.signals.get("commit_count", 0)

        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)

        return Report(
            scan_uuid="",  # filled in by API layer after DB insert
            project=Project(
                path=str(path),
                name=path.name,
                default_branch=branch,
            ),
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
            scores=[r.score for r in scored if r.score],
            overall_health=round(overall, 1),
            overall_band=Score.band_for(overall),
            runs=runs,
            findings=findings[:200],  # cap
            stats={
                "file_count": len(files),
                "loc_total": total_loc,
                "languages": per_lang,
                "commit_count": commit_count,
                "finding_counts": finding_counts,
            },
            composition=composition,
        )