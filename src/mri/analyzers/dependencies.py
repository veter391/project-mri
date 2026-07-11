"""Dependency analyzer — extracts imports across source files, finds cycles.

Strategy:
  - Walk files, parse with tree-sitter for known languages
  - Build module-level dependency graph (intra-module imports aggregated)
  - Detect cycles via iterative Tarjan's SCC
  - Compute fan-in / fan-out per module
"""
from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from mri.analyzers.base import BaseAnalyzer, ScanContext

# Try tree-sitter gracefully — fall back to regex for unsupported langs
try:
    from tree_sitter_language_pack import get_parser  # type: ignore
    _HAS_TS = True
except Exception:  # pragma: no cover
    _HAS_TS = False


# Cache tree-sitter parsers — get_parser() is expensive and we call it
# once per file. LRU cache keeps the last 8 language parsers alive.
@lru_cache(maxsize=8)
def _cached_parser(lang: str):
    return get_parser(lang) if _HAS_TS else None


# Regex fallback for Python (most common)
_PY_IMPORT = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE
)
_JS_IMPORT = re.compile(
    r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\)|import\s*\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)


class DependenciesAnalyzer(BaseAnalyzer):
    name = "dependencies"
    description = "Import graph, fan-in/fan-out, cycle detection"
    score_label = "dependency_health"
    weight = 1.0

    # Language → tree-sitter name
    LANG_TS = {
        "python": "python",
        "javascript": "javascript",
        "typescript": "typescript",
        "tsx": "tsx",
        "go": "go",
        "rust": "rust",
        "java": "java",
        "c": "c",
        "cpp": "cpp",
        "ruby": "ruby",
    }

    async def analyze(self, ctx: ScanContext) -> None:  # type: ignore[override]
        self._start()
        try:
            # Build module graph: source_module -> set(imported_module)
            edges: dict[str, set[str]] = defaultdict(set)
            all_modules: set[str] = set()

            for f in ctx.files:
                rel = f.get("rel_path", "")
                src_module = self._module_of(rel)
                all_modules.add(src_module)
                content = self._safe_read(Path(ctx.project_path) / rel)
                if content is None:
                    continue
                imports = self._extract_imports(rel, content)
                for imp in imports:
                    imp_module = self._module_of(imp)
                    if imp_module and imp_module != src_module:
                        edges[src_module].add(imp_module)
                        all_modules.add(imp_module)

            # Tarjan's SCC for cycle detection
            cycles = self._find_cycles(edges, all_modules)

            # Fan-in / fan-out
            fanin: dict[str, int] = defaultdict(int)
            fanout: dict[str, int] = {m: len(edges.get(m, set())) for m in all_modules}
            for _src, dsts in edges.items():
                for dst in dsts:
                    fanin[dst] += 1

            # God consumers (high fan-in)
            god_consumers = sorted(
                ({"module": m, "fanin": fanin[m], "fanout": fanout[m]} for m in all_modules),
                key=lambda x: -x["fanin"],
            )[:5]

            # Isolated modules (no edges at all — orphans)
            orphans = [
                m for m in all_modules
                if fanin[m] == 0 and fanout[m] == 0 and not m.startswith(".")
            ][:20]

            # Findings
            for cyc in cycles[:5]:
                members = " → ".join(cyc)
                self._add_finding(
                    severity="high" if len(cyc) <= 4 else "medium",
                    category="import_cycle",
                    title=f"Import cycle: {members}",
                    description=(
                        f"Cycle of length {len(cyc)}: {members}. "
                        f"Circular imports block refactoring and slow down startup."
                    ),
                    score=70.0 if len(cyc) <= 4 else 40.0,
                    data={"members": cyc},
                )

            for gc in god_consumers[:3]:
                if gc["fanin"] >= 10:
                    self._add_finding(
                        severity="medium",
                        category="god_module_imports",
                        title=f"Heavy import target: {gc['module']}",
                        description=(
                            f"{gc['fanin']} modules import {gc['module']}. "
                            f"Any change ripples widely. Stabilize its public API."
                        ),
                        target_path=gc["module"],
                        score=50.0,
                        data=gc,
                    )

            # Score
            score = 100.0
            contributors: list[str] = []
            if cycles:
                cycle_pen = min(40.0, sum(min(20, len(c) * 4) for c in cycles))
                score -= cycle_pen
                contributors.append(
                    f"{len(cycles)} import cycle(s) detected (-{cycle_pen:.1f})"
                )
            else:
                contributors.append("no import cycles")
            if god_consumers and god_consumers[0]["fanin"] >= 15:
                pen = min(15.0, god_consumers[0]["fanin"] * 0.5)
                score -= pen
                contributors.append(
                    f"god consumer: {god_consumers[0]['module']} (fan-in {god_consumers[0]['fanin']}) (-{pen:.1f})"
                )

            self._set_score(max(0.0, score), contributors)
            self.run.signals = {
                "module_count": len(all_modules),
                "edge_count": sum(len(d) for d in edges.values()),
                "cycle_count": len(cycles),
                "cycles_sample": cycles[:5],
                "god_consumers": god_consumers,
                "fanin_top": sorted(fanin.items(), key=lambda kv: -kv[1])[:10],
                "fanout_top": sorted(fanout.items(), key=lambda kv: -kv[1])[:10],
                "orphan_count": len(orphans),
            }
            self._finish_ok()
        except Exception as exc:  # pragma: no cover
            self._finish_err(f"{type(exc).__name__}: {exc}")
            raise

    # ---------- helpers ----------

    def _module_of(self, path: str) -> str:
        """Reduce a file path to a module key.

        Strips only the final extension, keeping the full path structure.
        This avoids collisions like `foo.bar.py` vs `foo/bar.py`.
        """
        if not path:
            return ""
        p = Path(path)
        # Strip only the file's extension, keep all parent dirs
        return str(p.with_suffix("")).replace("\\", "/")

    def _safe_read(self, path: Path) -> str | None:
        try:
            if path.stat().st_size > 2_000_000:  # skip >2MB files
                return None
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None

    def _extract_imports(self, path: str, content: str) -> list[str]:
        """Return a list of import paths (strings, possibly relative)."""
        suffix = Path(path).suffix.lower()
        imports: list[str] = []

        # Try tree-sitter first for known langs
        lang_name = None
        if suffix == ".py":
            lang_name = "python"
        elif suffix in (".js", ".mjs", ".cjs"):
            lang_name = "javascript"
        elif suffix in (".ts",):
            lang_name = "typescript"
        elif suffix in (".tsx",):
            lang_name = "tsx"
        elif suffix == ".go":
            lang_name = "go"

        if _HAS_TS and lang_name and lang_name in self.LANG_TS.values():
            try:
                parser = _cached_parser(lang_name)
                if parser is not None:
                    tree = parser.parse(content.encode("utf-8"))
                    imports = self._ts_walk(tree.root_node, content)
                    if imports:
                        return imports
            except Exception:  # nosec  # tree-sitter can fail on malformed input
                pass  # fall back to regex

        # Regex fallback
        if suffix == ".py":
            for m in _PY_IMPORT.finditer(content):
                mod = m.group(1) or m.group(2)
                if mod:
                    imports.append(mod.replace(".", "/") + ".py")
        elif suffix in (".js", ".ts", ".tsx", ".mjs", ".cjs"):
            for m in _JS_IMPORT.finditer(content):
                mod = m.group(1) or m.group(2) or m.group(3)
                if mod and mod.startswith("."):
                    imports.append(mod)
        return imports

    def _ts_walk(self, root: Any, content: str) -> list[str]:
        """Extract import strings from a tree-sitter AST — iterative.

        Recursive version hit Python's recursion limit on deeply nested code.
        Using an explicit stack avoids that and uses less memory.
        """
        imports: list[str] = []
        # We only look at top-level import_statement / import_declaration
        # nodes — no need to walk into function bodies.
        stack: list[Any] = [root]
        quote_re = re.compile(r"""['"]([^'"]+)['"]""")
        while stack:
            node = stack.pop()
            if node.type in ("import_statement", "import_declaration"):
                text = content[node.start_byte:node.end_byte]
                for m in quote_re.finditer(text):
                    imports.append(m.group(1))
            else:
                # Only descend into top-level scope (children of root or module)
                if node.type in ("module", "program", "source_file", "compilation_unit"):
                    stack.extend(node.children)
                elif node.parent is None or node.parent.type in (
                    "module", "program", "source_file", "compilation_unit"
                ):
                    stack.extend(node.children)
        return imports

    def _find_cycles(self, edges: dict[str, set[str]], all_modules: set[str]) -> list[list[str]]:
        """Iterative Tarjan's SCC — returns non-trivial SCCs as cycles.

        The recursive version hit Python's recursion limit on large graphs
        (10k+ modules). This iterative version handles arbitrary sizes
        and is roughly 2x faster due to less function-call overhead.
        """
        index_counter = 0
        index: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        on_stack: set[str] = set()
        stack: list[str] = []
        result: list[list[str]] = []

        # Work stack: (vertex, iterator over neighbours, is_root_call)
        # We push (v, iter(edges[v]), True) on first visit, then
        # continue with (v, iter, False) to resume after child returns.
        for start in sorted(all_modules):
            if start in index:
                continue
            # Simulate the recursive call stack
            work: list[tuple[str, Any, bool]] = [(start, iter(edges.get(start, ())), True)]
            index[start] = index_counter
            lowlinks[start] = index_counter
            index_counter += 1
            stack.append(start)
            on_stack.add(start)

            while work:
                v, it, is_root = work[-1]
                advanced = False
                for w in it:
                    if w not in index:
                        # Recurse into w
                        work[-1] = (v, it, False)
                        work.append((w, iter(edges.get(w, ())), True))
                        index[w] = index_counter
                        lowlinks[w] = index_counter
                        index_counter += 1
                        stack.append(w)
                        on_stack.add(w)
                        advanced = True
                        break
                    elif w in on_stack:
                        lowlinks[v] = min(lowlinks[v], index[w])
                if not advanced:
                    # Done with v — check if v is SCC root
                    if lowlinks[v] == index[v]:
                        scc: list[str] = []
                        while True:
                            w = stack.pop()
                            on_stack.discard(w)
                            scc.append(w)
                            if w == v:
                                break
                        if len(scc) > 1:
                            result.append(scc)
                    work.pop()
                    if work:
                        # Update parent's lowlink with our lowlink
                        pv, _, _ = work[-1]
                        lowlinks[pv] = min(lowlinks[pv], lowlinks[v])
        return result