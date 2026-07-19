"""Base analyzer interface.

Every analyzer is a small async unit that:
  1. takes a ScanContext (project path, branch, file list)
  2. computes Findings + a Score (named, ranged, traced)
  3. returns an AnalyzerRun
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

from mri.models.scan import AnalyzerRun, Finding, ScanStatus, Score

_logger = logging.getLogger("mri.analyzers")


@dataclass(slots=True)
class ScanContext:
    """Everything an analyzer needs to do its job.

    `files` is the pre-walked file list (path, language, size_bytes, loc).
    `git` is the GitPython Repo instance — ready for log/blame/etc.
    """

    project_path: Path
    branch: str
    files: list[dict[str, Any]]
    git: Any  # git.Repo — kept untyped to avoid hard dep here
    include_globs: list[str] | None = None
    exclude_globs: list[str] | None = None

    # Output of the analyzers that already ran this scan, keyed by name. A
    # derived analyzer reads its inputs from here rather than recomputing them.
    results: dict[str, AnalyzerRun] = field(default_factory=dict)

    # Inputs that do not live in the scanned tree: agent session logs, ingested
    # external metrics, whatever later layers need. Keyed by source name so the
    # context does not grow one field per layer and turn into a god-object.
    sources: dict[str, Any] = field(default_factory=dict)

    # Earlier scans of the same project, most recent first. Correlating a change
    # with its later consequences is inherently temporal, and the
    # single-snapshot contract had nowhere to express that. Empty unless a
    # caller supplies it.
    previous_scans: list[dict[str, Any]] = field(default_factory=list)

    # Shared caches. The analyzers each used to read and parse the same files:
    # measured at five read passes and three tree-sitter parses over the corpus.
    # Both are bounded — retaining every file and every AST on a large repository
    # would be a memory problem, so past the budget content is still returned,
    # just not retained.
    _content: dict[str, str] = field(default_factory=dict, repr=False)
    _trees: dict[tuple[str, str], Any] = field(default_factory=dict, repr=False)
    _content_bytes: int = field(default=0, repr=False)
    _tree_source_chars: int = field(default=0, repr=False)
    _budgets_reported: set[str] = field(default_factory=set, repr=False)
    #: Repo-relative paths of every walked file, `/`-separated. Import
    #: resolution checks candidates against this, so it is built once rather
    #: than per file — rebuilding it inside the resolver made resolution O(n^2).
    _known_files: set[str] | None = field(default=None, repr=False)
    _source_roots: tuple[str, ...] | None = field(default=None, repr=False)

    def known_files(self) -> set[str]:
        """Every walked path, normalised, computed once per scan."""
        if self._known_files is None:
            self._known_files = {
                f.get("rel_path", "").replace("\\", "/") for f in self.files
            }
        return self._known_files

    def source_roots(self) -> tuple[str, ...]:
        """Directory prefixes that absolute imports are relative to.

        An absolute import names a module as the interpreter sees it, not as the
        repository stores it: in a src-layout project `import mri.analyzers` is
        `src/mri/analyzers`. Resolving without this finds nothing at all in the
        most common Python layout — including this repository.

        A source root is the parent of a top-level package: a directory holding
        `__init__.py` whose own parent does not. `""` is always included so flat
        layouts keep working.
        """
        if self._source_roots is None:
            package_dirs = {
                path.rsplit("/", 1)[0]
                for path in self.known_files()
                if path.endswith("/__init__.py")
            }
            roots = {""}
            for directory in package_dirs:
                parent = directory.rsplit("/", 1)[0] if "/" in directory else ""
                # Only a *top-level* package marks a root; nested packages do not.
                if parent not in package_dirs:
                    roots.add(parent)
            self._source_roots = tuple(sorted(roots, key=len))
        return self._source_roots

    #: Stop retaining file contents past this many characters.
    CONTENT_BUDGET_CHARS: ClassVar[int] = 64 * 1024 * 1024
    #: Stop retaining parsed trees past this much *source*.
    #:
    #: Counted in source characters rather than files because a tree's cost
    #: tracks the size of what it came from, not the number of paths. A
    #: file-count budget of 5,000 permitted roughly 950 MiB of ASTs — measured
    #: at ~195 KiB per tree over ~7 KB of source, so about 28x the source it
    #: parses — while the content budget beside it allowed 64 MiB. Two budgets
    #: for the same scan that differ by an order of magnitude are not budgets.
    #: 8 MiB of source lands in the same neighbourhood as the content cache.
    TREE_SOURCE_BUDGET_CHARS: ClassVar[int] = 8 * 1024 * 1024
    #: Files larger than this are never read whole.
    MAX_FILE_BYTES: ClassVar[int] = 2 * 1024 * 1024

    def is_excluded(self, path: str) -> bool:
        from fnmatch import fnmatch

        if self.exclude_globs:
            return any(fnmatch(path, g) for g in self.exclude_globs)
        return False

    def read_text(self, rel_path: str) -> str | None:
        """Read a source file once and share it with every analyzer.

        Returns None when the file is unreadable or larger than
        ``MAX_FILE_BYTES``. The size is checked before reading, so an
        accidentally committed huge file never lands in memory.
        """
        cached = self._content.get(rel_path)
        if cached is not None:
            return cached
        full = self.project_path / rel_path
        try:
            # Containment check. The walk already refuses symlinked files, but
            # this is the single door every analyzer reads through, so it
            # verifies for itself rather than trusting the caller: a scanned
            # repository is untrusted input, and git stores a symlink as an
            # ordinary blob, so `notes.py -> /etc/passwd` is committable.
            if full.is_symlink():
                return None
            resolved = full.resolve()
            if not resolved.is_relative_to(self.project_path.resolve()):
                return None
            if resolved.stat().st_size > self.MAX_FILE_BYTES:
                return None
            text = resolved.read_text(encoding="utf-8", errors="ignore")
        except (OSError, ValueError):
            return None
        if self._content_bytes + len(text) <= self.CONTENT_BUDGET_CHARS:
            self._content[rel_path] = text
            self._content_bytes += len(text)
        else:
            self._warn_budget_exhausted("content", "CONTENT_BUDGET_CHARS")
        return text

    def _warn_budget_exhausted(self, what: str, setting: str) -> None:
        """Say so, once, when a cache stops retaining.

        Past the budget every analyzer re-reads and re-parses from scratch —
        measured at roughly 1,800x for reads and 5,000x for parses. Degrading is
        the right behaviour; degrading silently is not, because nothing in the
        report would explain why a slightly larger repository took far longer.
        """
        if setting in self._budgets_reported:
            return
        self._budgets_reported.add(setting)
        _logger.warning(
            "scan.cache.budget_exhausted",
            extra={
                "event": "scan.cache.budget_exhausted",
                "cache": what,
                "setting": setting,
                "project": str(self.project_path),
            },
        )

    def parse_tree(self, rel_path: str, ts_language: str) -> Any | None:
        """Parse a file with tree-sitter once and share the AST.

        Returns None when no parser is available or the file cannot be read, so
        callers keep their existing "fall back to regex" behaviour.
        """
        key = (rel_path, ts_language)
        cached = self._trees.get(key)
        if cached is not None:
            return cached
        text = self.read_text(rel_path)
        if text is None:
            return None
        from mri.analyzers.parsing import get_parser_for

        parser = get_parser_for(ts_language)
        if parser is None:
            return None
        try:
            tree = parser.parse(text.encode("utf-8"))
        except Exception:
            # Malformed source is expected; the caller falls back to regex.
            return None
        if self._tree_source_chars + len(text) <= self.TREE_SOURCE_BUDGET_CHARS:
            self._trees[key] = tree
            self._tree_source_chars += len(text)
        else:
            self._warn_budget_exhausted("AST", "TREE_SOURCE_BUDGET_CHARS")
        return tree


class Stage(str, Enum):
    """When an analyzer runs.

    PRODUCER analyzers extract facts straight from the repository and depend on
    nothing but the context. FUSION analyzers derive from what producers found —
    risk decomposed by authorship, decisions linked to their consequences — so
    they must run afterwards and in dependency order. Six equal peers in one
    list could not express that.
    """

    PRODUCER = "producer"
    FUSION = "fusion"


class BaseAnalyzer(ABC):
    """Base class for all analyzers."""

    name: str = "unnamed"
    description: str = ""
    score_label: str = "unnamed_score"
    # Higher weight = more impact on overall_health.
    weight: float = 1.0
    #: Which stage this analyzer belongs to.
    stage: ClassVar[Stage] = Stage.PRODUCER
    #: Names of analyzers whose output this one reads from `ctx.results`.
    #: The scanner orders by this and refuses to run on a missing or cyclic
    #: dependency rather than silently handing over an empty result.
    requires: ClassVar[tuple[str, ...]] = ()

    def __init__(self) -> None:
        self.run = AnalyzerRun(name=self.name)

    @abstractmethod
    def analyze(self, ctx: ScanContext) -> AnalyzerRun:
        """Run the analyzer. Mutates self.run and returns it.

        Deliberately synchronous. These are CPU- and IO-bound passes with no
        await points; declaring them async made `gather` look like concurrency
        while actually running them back to back and pinning the event loop for
        the whole scan. The scanner dispatches each one with `asyncio.to_thread`.
        """
        ...

    # Convenience helpers --------------------------------------------------

    def _start(self) -> None:
        self.run.status = ScanStatus.RUNNING
        self.run.started_at = datetime.now(timezone.utc)

    def _finish_ok(self) -> None:
        self.run.status = ScanStatus.COMPLETED
        self.run.finished_at = datetime.now(timezone.utc)
        if self.run.started_at and self.run.finished_at:
            self.run.duration_ms = int(
                (self.run.finished_at - self.run.started_at).total_seconds() * 1000
            )

    def _finish_err(self, message: str) -> None:
        self.run.status = ScanStatus.FAILED
        self.run.error_message = message
        self.run.finished_at = datetime.now(timezone.utc)
        if self.run.started_at and self.run.finished_at:
            self.run.duration_ms = int(
                (self.run.finished_at - self.run.started_at).total_seconds() * 1000
            )

    def _add_finding(self, **kwargs: Any) -> None:
        # Clamp score to 0..100 to satisfy Pydantic validation
        if "score" in kwargs and kwargs["score"] is not None:
            kwargs["score"] = max(0.0, min(100.0, float(kwargs["score"])))
        self.run.findings.append(Finding(**kwargs))

    def _set_score(self, value: float, contributors: list[str]) -> None:
        self.run.score = Score(
            label=self.score_label,
            value=round(value, 1),
            band=Score.band_for(value),
            contributors=contributors,
        )