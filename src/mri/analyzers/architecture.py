"""Architecture analyzer — derives a module map from the filesystem tree.

Computes:
  - Module map (top-level dirs become modules, files inside are leaves)
  - Depth distribution (deeply nested dirs == complexity risk)
  - Largest modules by LOC
  - Empty/underused dirs

Score: rewards shallow, balanced module trees. Penalizes god-modules and deep nesting.
"""
from __future__ import annotations

from collections import defaultdict

from mri.analyzers.base import BaseAnalyzer, ScanContext

#: Signals are a summary for display, not a data dump. Every list is capped
#: and the true total is reported beside it, so a truncated view can never be
#: mistaken for the whole picture. Uncapped, these grew with repository size:
#: the audit measured a 2 MB report_json on a 12,000-file repo, written to the
#: database on every scan, unbounded in a watch loop.
SIGNAL_SAMPLE_LIMIT = 50


class ArchitectureAnalyzer(BaseAnalyzer):
    name = "architecture"
    description = "Module map, depth distribution, largest modules"
    score_label = "architecture_health"
    weight = 1.2  # architecture matters a lot

    MAX_HEALTHY_DEPTH = 4
    GOD_MODULE_LOC = 5000

    def analyze(self, ctx: ScanContext) -> None:  # type: ignore[override]
        self._start()
        try:
            # Group files by top-level directory
            modules: dict[str, dict] = defaultdict(lambda: {
                "files": 0,
                "loc": 0,
                "max_depth": 0,
                "languages": set(),
            })

            for f in ctx.files:
                rel = f.get("rel_path", "")
                parts = rel.split("/")
                if not parts or parts == [""]:
                    continue
                top = parts[0] if parts[0] else "(root)"
                if "." in top and "/" not in rel:
                    top = "(root)"  # file in project root
                depth = len(parts) - 1
                modules[top]["files"] += 1
                modules[top]["loc"] += f.get("loc", 0)
                modules[top]["max_depth"] = max(modules[top]["max_depth"], depth)
                lang = f.get("language", "unknown")
                modules[top]["languages"].add(lang)

            if not modules:
                self._set_score(50.0, ["no files to analyze"])
                self._finish_ok()
                return

            # Convert sets to counts for JSON
            modules_view = []
            for name, data in modules.items():
                modules_view.append({
                    "name": name,
                    "files": data["files"],
                    "loc": data["loc"],
                    "max_depth": data["max_depth"],
                    "languages": sorted(data["languages"]),
                })
            modules_view.sort(key=lambda m: -m["loc"])

            # --- God modules (single module dominates LOC) ---
            total_loc = sum(m["loc"] for m in modules_view)
            god_modules = []
            for m in modules_view:
                share = m["loc"] / max(total_loc, 1)
                if m["loc"] > self.GOD_MODULE_LOC or share > 0.5:
                    god_modules.append({**m, "share": round(share, 3)})

            for gm in god_modules[:3]:
                self._add_finding(
                    severity="high" if gm["share"] > 0.6 else "medium",
                    category="god_module",
                    title=f"God module: {gm['name']}/",
                    description=(
                        f"Module '{gm['name']}/' holds {gm['loc']:,} LOC across {gm['files']} files — "
                        f"{round(gm['share'] * 100)}% of the codebase. Extract sub-modules or split concerns."
                    ),
                    target_path=gm["name"] + "/",
                    score=80.0,
                    data=gm,
                )

            # --- Deep nesting ---
            deep = [m for m in modules_view if m["max_depth"] > self.MAX_HEALTHY_DEPTH]
            for m in deep[:5]:
                self._add_finding(
                    severity="medium",
                    category="deep_nesting",
                    title=f"Deep nesting: {m['name']}/ (depth {m['max_depth']})",
                    description=(
                        f"Files in '{m['name']}/' reach depth {m['max_depth']}. "
                        f"Deep trees make imports harder to follow and tests harder to colocate."
                    ),
                    target_path=m["name"] + "/",
                    score=50.0,
                    data=m,
                )

            # --- Module imbalance (gini-ish) ---
            if len(modules_view) >= 3:
                sizes = sorted([m["loc"] for m in modules_view], reverse=True)
                top1 = sizes[0]
                bottom_sum = sum(sizes[1:])
                imbalance = top1 / max(bottom_sum, 1)
                imbalance_note = (
                    f"top module is {round(imbalance, 1)}x the size of all others combined"
                    if imbalance > 1
                    else f"top/bottom ratio = {round(imbalance, 2)}"
                )
            else:
                imbalance = 0
                imbalance_note = "few modules"

            # --- Score ---
            score = 100.0
            contributors: list[str] = []
            if god_modules:
                pen = min(35.0, len(god_modules) * 15 + (god_modules[0]["share"] - 0.4) * 30)
                score -= pen
                contributors.append(
                    f"{len(god_modules)} god module(s); {imbalance_note} (-{pen:.1f})"
                )
            else:
                contributors.append(f"module balance ok ({imbalance_note})")
            if deep:
                pen = min(15.0, len(deep) * 5)
                score -= pen
                contributors.append(f"{len(deep)} deeply-nested module(s) (-{pen:.1f})")

            self._set_score(max(0.0, score), contributors)
            self.run.signals = {
                "module_count": len(modules_view),
                "total_loc": total_loc,
                "modules": modules_view[:SIGNAL_SAMPLE_LIMIT],
                "god_modules": god_modules,
                "deep_modules": deep,
                "imbalance_ratio": round(imbalance, 3) if imbalance else 0,
            }
            self._finish_ok()
        except Exception as exc:  # pragma: no cover
            self._finish_err(f"{type(exc).__name__}: {exc}")
            raise