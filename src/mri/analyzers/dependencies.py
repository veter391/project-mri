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
from pathlib import Path
from typing import Any

from mri.analyzers.base import BaseAnalyzer, ScanContext
from mri.analyzers.parsing import extract_imports

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

    def analyze(self, ctx: ScanContext) -> None:  # type: ignore[override]
        self._start()
        try:
            # Build module graph: source_module -> set(imported_module)
            edges: dict[str, set[str]] = defaultdict(set)
            all_modules: set[str] = set()

            for f in ctx.files:
                rel = f.get("rel_path", "")
                src_module = self._module_of(rel)
                all_modules.add(src_module)
                content = ctx.read_text(rel)
                if content is None:
                    continue
                imports = extract_imports(ctx, rel, content)
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
            # all_modules is a set; sort with the module name as a secondary key
            # so equal-fan-in modules order stably (set iteration order is not).
            god_consumers = sorted(
                ({"module": m, "fanin": fanin[m], "fanout": fanout[m]} for m in all_modules),
                key=lambda x: (-x["fanin"], x["module"]),
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
                # Five cycles, but a single SCC can hold thousands of
                # modules, so the members are capped too.
                "cycles_sample": [c[:25] for c in cycles[:5]],
                "largest_cycle_size": max((len(c) for c in cycles), default=0),
                "god_consumers": god_consumers,
                "fanin_top": sorted(fanin.items(), key=lambda kv: (-kv[1], kv[0]))[:10],
                "fanout_top": sorted(fanout.items(), key=lambda kv: (-kv[1], kv[0]))[:10],
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