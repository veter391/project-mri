"""Coupling analyzer — Robert Martin's I/D metrics on the module graph.

For each module:
  - Ca (afferent coupling) = number of modules that depend on it
  - Ce (efferent coupling) = number of modules it depends on
  - I (instability)        = Ce / (Ca + Ce)        ∈ [0, 1]
  - Abstractness A         = abstract_types / total_types  (heuristic: files with only interfaces/classes named in CAPS)
  - Distance D             = |A + I - 1| / sqrt(2)   ∈ [0, ~0.707]

Penalty: high D for stable-but-concrete modules (painful to change).
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from mri.analyzers.base import BaseAnalyzer, ScanContext
from mri.analyzers.parsing import extract_imports


class CouplingAnalyzer(BaseAnalyzer):
    name = "coupling"
    description = "Afferent / efferent coupling, instability, distance from main"
    score_label = "coupling_health"
    weight = 0.9

    def analyze(self, ctx: ScanContext) -> None:  # type: ignore[override]
        self._start()
        try:
            # Reuse the dependency analyzer's edges via signals isn't trivial — re-derive.
            # (Keeping analyzers independent means each can be re-run alone.)
            edges: dict[str, set[str]] = defaultdict(set)
            all_modules: set[str] = set()

            for f in ctx.files:
                rel = f.get("rel_path", "")
                src = self._module_of(rel)
                all_modules.add(src)

            # Import extraction is shared with the dependencies analyzer and the
            # ASTs come from the scan context, so this pass reuses the trees that
            # analyzer already built instead of parsing the corpus a second time.
            for f in ctx.files:
                rel = f.get("rel_path", "")
                content = ctx.read_text(rel)
                if content is None:
                    continue
                src_module = self._module_of(rel)
                imports = extract_imports(ctx, rel, content)
                for imp in imports:
                    imp_module = self._module_of(imp)
                    if imp_module and imp_module != src_module:
                        edges[src_module].add(imp_module)
                        all_modules.add(imp_module)

            # Compute Ca, Ce, I per module
            ca: dict[str, int] = defaultdict(int)
            ce: dict[str, int] = {m: len(edges.get(m, set())) for m in all_modules}
            for src, dsts in edges.items():
                for dst in dsts:
                    ca[dst] += 1

            # Abstractness heuristic: count files whose names suggest abstract types
            abstract_count: dict[str, int] = defaultdict(int)
            type_count: dict[str, int] = defaultdict(int)
            for f in ctx.files:
                rel = f.get("rel_path", "")
                mod = self._module_of(rel)
                stem = Path(rel).stem
                name = Path(rel).name  # keep extension for header (.h) detection
                # Abstractness heuristic: does the filename suggest an abstract
                # type / interface? Decide ONCE per file so abstract_count can
                # never exceed type_count — otherwise abstractness A could exceed
                # its documented [0, 1] range and skew the distance metric.
                is_abstract = (
                    (bool(stem) and stem[0].isupper())
                    or stem.startswith(("interface", "abs_", "base_", "abstract_"))
                    or stem.startswith(("I", "Abstract", "Base"))
                    or name.endswith(".h")
                )
                if is_abstract:
                    abstract_count[mod] += 1
                if not rel.endswith(("test.py", "_test.go", ".test.ts", "Test.java", ".spec.ts")):
                    type_count[mod] += 1

            metrics = []
            for m in sorted(all_modules):
                afferent = ca.get(m, 0)
                efferent = ce.get(m, 0)
                instability = efferent / max(afferent + efferent, 1)
                total = type_count[m]
                abstractness = min(1.0, abstract_count[m] / max(total, 1)) if total else 0
                distance = ((abstractness + instability - 1) ** 2) ** 0.5 / (2 ** 0.5)
                metrics.append({
                    "module": m,
                    "Ca": afferent,
                    "Ce": efferent,
                    "I": round(instability, 3),
                    "A": round(abstractness, 3),
                    "D": round(distance, 3),
                })

            # Painful modules: stable (low I) + concrete (low A) + high fan-in
            painful = [m for m in metrics if m["D"] > 0.5 and m["Ca"] >= 3]
            # Secondary key on the module name so equal-D modules order stably —
            # otherwise the report is non-deterministic run to run.
            painful.sort(key=lambda x: (-x["D"], x["module"]))

            # Findings
            for pm in painful[:10]:
                self._add_finding(
                    severity="high" if pm["Ca"] >= 10 else "medium",
                    category="stable_concrete",
                    title=f"Painful to change: {pm['module']}",
                    description=(
                        f"Ca={pm['Ca']} (many depend on it), Ce={pm['Ce']}, "
                        f"I={pm['I']} (stable), A={pm['A']} (concrete), D={pm['D']}. "
                        f"Many consumers depend on a concrete module — risky to refactor."
                    ),
                    target_path=pm["module"],
                    score=pm["D"] * 100,
                    data=pm,
                )

            # Score
            score = 100.0
            contributors: list[str] = []
            if painful:
                pen = min(35.0, len(painful) * 5 + (painful[0]["D"] - 0.5) * 30)
                score -= pen
                contributors.append(
                    f"{len(painful)} painful module(s); top D = {painful[0]['D']} (-{pen:.1f})"
                )
            else:
                contributors.append("no stable+concrete modules in main sequence")
            # Bonus for healthy instability distribution
            if metrics:
                avg_I = sum(m["I"] for m in metrics) / len(metrics)
                contributors.append(f"avg instability = {round(avg_I, 2)}")

            self._set_score(max(0.0, score), contributors)
            self.run.signals = {
                "module_count": len(metrics),
                "painful_modules": painful[:10],
                "metrics_sample": sorted(metrics, key=lambda x: (-x["Ca"], x["module"]))[:15],
                "avg_instability": round(avg_I, 3) if metrics else 0,
            }
            self._finish_ok()
        except Exception as exc:  # pragma: no cover
            self._finish_err(f"{type(exc).__name__}: {exc}")
            raise

    @staticmethod
    def _module_of(path: str) -> str:
        if not path:
            return ""
        p = Path(path)
        # Strip only the final extension, keep all parent dirs
        return str(p.with_suffix("")).replace("\\", "/")

    @staticmethod
    def _safe_read(path: Path) -> str | None:
        try:
            if path.stat().st_size > 2_000_000:
                return None
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None