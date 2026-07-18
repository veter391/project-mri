"""Complexity analyzer — code-level complexity signals.

Computes:
  - LOC distribution (per file)
  - Function size (tree-sitter for Python/JS/Go/Rust/TS)
  - Long files (>500 LOC), long functions (>60 LOC)
  - Comment ratio (proxy for documentation effort)
  - Avg function length per module

Score: rewards balanced file sizes, dense comments. Penalizes mega-files.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from mri.analyzers.base import BaseAnalyzer, ScanContext
from mri.analyzers.parsing import HAS_TREE_SITTER as _HAS_TS
from mri.analyzers.parsing import language_for_extension

# Python comment regex (matches `# ...` after start-of-line whitespace)
_PY_COMMENT = re.compile(r"^\s*#.*$", re.MULTILINE)
# JS/TS/Go/Rust/Java/C/C++ line comments
_C_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)


LONG_FILE_LOC = 500
LONG_FILE_CRIT = 1500
LONG_FN_LINES = 60


class ComplexityAnalyzer(BaseAnalyzer):
    name = "complexity"
    description = "File size, function length, comment ratio"
    score_label = "complexity_health"
    weight = 1.0

    def analyze(self, ctx: ScanContext) -> None:  # type: ignore[override]
        self._start()
        try:
            long_files: list[dict] = []
            long_functions: list[dict] = []
            comment_lines_total = 0
            code_lines_total = 0
            function_lengths: list[int] = []
            file_locs: list[int] = []
            per_lang: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "loc": 0})

            for f in ctx.files:
                rel = f.get("rel_path", "")
                loc = f.get("loc", 0)
                file_locs.append(loc)
                lang = f.get("language", "unknown")
                per_lang[lang]["files"] += 1
                per_lang[lang]["loc"] += loc

                if loc > LONG_FILE_LOC:
                    sev = "high" if loc > LONG_FILE_CRIT else "medium"
                    long_files.append({"path": rel, "loc": loc})

                # Function-level scan if tree-sitter available
                if _HAS_TS:
                    ts_lang = language_for_extension(Path(rel).suffix)
                    if ts_lang:
                        try:
                            # Shared with the other analyzers: read once, parse once.
                            content = ctx.read_text(rel)
                            if content:
                                tree = ctx.parse_tree(rel, ts_lang)
                                if tree is not None:
                                    fns = self._collect_functions(
                                        tree.root_node, content.encode("utf-8")
                                    )
                                    # Count comment lines: Python '#' OR C-style '//'
                                    py_cmts = len(_PY_COMMENT.findall(content))
                                    c_cmts = len(_C_LINE_COMMENT.findall(content))
                                    comment_lines_total += py_cmts + c_cmts
                                    # Keep `code_lines_total` as the total file lines
                                    # (for the comment_ratio calculation). The actual
                                    # "code lines" is loc - comments, available as
                                    # max(0, loc - comments) if you need it.
                                    code_lines_total += loc
                                    content_bytes = content.encode("utf-8")
                                    for fn_name, start, end in fns:
                                        # Function length in lines = newlines between start and end
                                        segment = content_bytes[start:end]
                                        fn_len = segment.count(b"\n")
                                        function_lengths.append(fn_len)
                                        if fn_len > LONG_FN_LINES:
                                            long_functions.append({
                                                "path": rel,
                                                "fn": fn_name,
                                                "lines": fn_len,
                                            })
                        except Exception:  # nosec B110  # parse error; skip this file
                            pass

            # Findings — long files
            for lf in sorted(long_files, key=lambda x: -x["loc"])[:10]:
                sev = "high" if lf["loc"] > LONG_FILE_CRIT else "medium"
                self._add_finding(
                    severity=sev,
                    category="long_file",
                    title=f"Long file: {lf['path']} ({lf['loc']:,} LOC)",
                    description=(
                        f"File has {lf['loc']:,} lines. Split it into smaller units; "
                        f"long files slow comprehension and review."
                    ),
                    target_path=lf["path"],
                    score=min(100.0, lf["loc"] / 15),
                    data=lf,
                )

            # Findings — long functions
            for lfn in sorted(long_functions, key=lambda x: -x["lines"])[:10]:
                self._add_finding(
                    severity="medium" if lfn["lines"] < 200 else "high",
                    category="long_function",
                    title=f"Long function: {lfn['fn']}() in {lfn['path']} ({lfn['lines']} lines)",
                    description=(
                        f"Function '{lfn['fn']}' spans {lfn['lines']} lines. "
                        f"Decompose into named helpers; long functions hide intent."
                    ),
                    target_path=lfn["path"],
                    target_symbol=lfn["fn"],
                    score=min(100.0, lfn["lines"] / 2),
                    data=lfn,
                )

            # Score
            score = 100.0
            contributors: list[str] = []
            if long_files:
                pen = min(30.0, len(long_files) * 4)
                score -= pen
                contributors.append(f"{len(long_files)} files > {LONG_FILE_LOC} LOC (-{pen:.1f})")
            else:
                contributors.append(f"all files <= {LONG_FILE_LOC} LOC")
            if long_functions:
                pen = min(25.0, len(long_functions) * 2)
                score -= pen
                contributors.append(f"{len(long_functions)} functions > {LONG_FN_LINES} lines (-{pen:.1f})")
            # Comment ratio is only meaningful when we actually counted code
            # lines. Without tree-sitter no lines are scanned, so a 0/0 -> 0
            # ratio must NOT trigger a spurious penalty on every project.
            comment_ratio = (
                comment_lines_total / code_lines_total if code_lines_total > 0 else 0.0
            )
            if code_lines_total > 0:
                if comment_ratio < 0.05:
                    score -= 10
                    contributors.append(
                        f"low comment ratio ({round(comment_ratio * 100, 1)}%) (-10.0)"
                    )
            else:
                contributors.append("comment ratio not measured (no line scan)")

            self._set_score(max(0.0, score), contributors)
            self.run.signals = {
                "files_scanned": len(ctx.files),
                "total_loc": sum(file_locs),
                "median_file_loc": median(file_locs) if file_locs else 0,
                "max_file_loc": max(file_locs) if file_locs else 0,
                "function_count": len(function_lengths),
                "median_function_length": median(function_lengths) if function_lengths else 0,
                "long_files": long_files,
                "long_functions": long_functions[:20],
                "per_language": dict(per_lang),
                # null (not 0) when no code lines were scanned — a 0.0 here would
                # falsely read as "documented nothing" rather than "not measured".
                "comment_ratio": round(comment_ratio, 4) if code_lines_total > 0 else None,
            }
            self._finish_ok()
        except Exception as exc:  # pragma: no cover
            self._finish_err(f"{type(exc).__name__}: {exc}")
            raise


    @staticmethod
    def _collect_functions(node: Any, content: bytes) -> list[tuple[str, int, int]]:
        """Return list of (name, start_byte, end_byte) for top-level functions.

        Iterative — the recursive version hit Python's recursion limit on
        deeply nested ASTs (e.g. deeply nested JSX/TSX). We walk top-down
        and only descend into children of the current node, collecting
        function nodes along the way.
        """
        results: list[tuple[str, int, int]] = []
        stack: list[Any] = [node]
        while stack:
            n = stack.pop()
            if n.type in (
                "function_definition",        # python
                "function_declaration",       # js/ts/go/rust
                "method_definition",          # ruby
                "method_declaration",         # java
            ):
                name_node = n.child_by_field_name("name")
                name = (
                    content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="ignore")
                    if name_node else "<anonymous>"
                )
                results.append((name, n.start_byte, n.end_byte))
            stack.extend(n.children)
        return results