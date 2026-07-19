"""Tech debt analyzer — surface-level signals of maintenance backlog.

Computes:
  - TODO / FIXME / HACK / XXX / BUG / DEPRECATED / noqa comment counts
  - Per-file debt density (weighted by severity)
  - Top debt hotspots
  - Generated / vendored code ratio
  - Total debt_index = weighted TODO score

Score: penalizes TODOs more in core files than in tests/examples.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from mri.analyzers.base import BaseAnalyzer, ScanContext

#: One pattern per marker, scanned separately.
#:
#: The performance audit proposed collapsing these into a single alternation
#: with named groups, claiming a 4x win. Measured, it is a loss: 0.69x on
#: ordinary source and still 0.89x on text saturated with markers. Seven simple
#: patterns let CPython's regex engine take its fast literal path, while one
#: seven-way alternation makes it try every branch at every position. The
#: recommendation was not adopted.
#:
#: Note also that the case rules differ deliberately — TODO, FIXME, HACK, XXX
#: and BUG are case-sensitive, DEPRECATED and noqa are not — so any future
#: attempt to merge them must preserve that per-marker, not flatten it.
DEBT_PATTERNS = [
    (re.compile(r"\bTODO\b"), "todo", 1.0),
    (re.compile(r"\bFIXME\b"), "fixme", 2.0),
    (re.compile(r"\bHACK\b"), "hack", 1.5),
    (re.compile(r"\bXXX\b"), "xxx", 1.2),
    (re.compile(r"\bBUG\b"), "bug", 1.0),
    (re.compile(r"\bDEPRECATED\b", re.IGNORECASE), "deprecated", 1.8),
    (re.compile(r"\bnoqa\b", re.IGNORECASE), "noqa", 0.5),
]


GENERATED_PATTERNS = [
    re.compile(r"^#.*auto[-_]?generated", re.IGNORECASE),
    re.compile(r"^//.*auto[-_]?generated", re.IGNORECASE),
    re.compile(r"^/\*.*auto[-_]?generated", re.IGNORECASE),
]

VENDORED_DIRS = {"node_modules", "vendor", "venv", ".venv", "dist", "build", "__pycache__", ".git"}


class TechDebtAnalyzer(BaseAnalyzer):
    name = "tech_debt"
    description = "TODO/FIXME/HACK markers, dead code candidates, vendored ratio"
    score_label = "debt_index"
    # Note: debt_index is INVERSE — higher = more debt = lower health
    # We store it as-is and let the composer invert.
    weight = 1.0

    def analyze(self, ctx: ScanContext) -> None:  # type: ignore[override]
        self._start()
        try:
            debt_by_file: dict[str, dict] = defaultdict(lambda: Counter())
            debt_locations: list[dict] = []
            total_loc = 0
            generated_loc = 0
            vendored_files = 0

            for f in ctx.files:
                rel = f.get("rel_path", "")
                loc = f.get("loc", 0)
                total_loc += loc

                # Skip vendored / generated
                parts = rel.split("/")
                if any(p in VENDORED_DIRS for p in parts):
                    vendored_files += 1
                    continue

                # Shared with the other analyzers: this used to open and read
                # every file itself, so each one was read twice per scan.
                content = ctx.read_text(rel)
                if content is None:
                    continue

                # Generated?
                first_lines = "\n".join(content.splitlines()[:5])
                if any(p.search(first_lines) for p in GENERATED_PATTERNS):
                    generated_loc += loc
                    continue

                for pattern, kind, weight in DEBT_PATTERNS:
                    count = len(pattern.findall(content))
                    if count:
                        debt_by_file[rel][kind] += count
                        # store one location per first occurrence per kind
                        match = pattern.search(content)
                        if match:
                            debt_locations.append({
                                "path": rel,
                                "kind": kind,
                                "line": content.count("\n", 0, match.start()) + 1,
                                "weight": weight,
                            })

            # Aggregate
            total_counts = Counter()  # type: Counter[str]
            for file_counts in debt_by_file.values():
                for k, v in file_counts.items():
                    total_counts[k] += v

            weighted_total = sum(
                total_counts.get(kind, 0) * w for _, kind, w in DEBT_PATTERNS
            )

            # Debt per KLOC
            debt_per_kloc = weighted_total / max(total_loc / 1000, 1)

            # Generate findings
            for loc_info in debt_locations[:30]:
                kind = loc_info["kind"]
                weight = loc_info["weight"]
                sev = "low"
                if kind in {"fixme", "hack", "deprecated"} and weight >= 1.5:
                    sev = "medium"
                if loc_info["path"].endswith(("test.py", "_test.go", ".test.ts", ".test.js", "Test.java")):
                    sev = "info"  # TODOs in tests are fine
                self._add_finding(
                    severity=sev,
                    category=f"debt_{kind}",
                    title=f"{kind.upper()} at {loc_info['path']}:{loc_info['line']}",
                    description=f"Marker '{kind}' at line {loc_info['line']}. Resolve or convert to a tracked issue.",
                    target_path=loc_info["path"],
                    score=weight * 10,
                    data=loc_info,
                )

            # Heuristic: file with too many TODOs is itself a hotspot
            file_debt = []
            for p, c in debt_by_file.items():
                weighted = sum(c.get(kind, 0) * w for _, kind, w in DEBT_PATTERNS)
                file_debt.append({"path": p, "weighted": round(weighted, 1), "raw": dict(c)})
            file_debt.sort(key=lambda x: -x["weighted"])
            for fd in file_debt[:3]:
                if fd["weighted"] >= 5:
                    self._add_finding(
                        severity="medium",
                        category="debt_hotspot",
                        title=f"Debt hotspot: {fd['path']}",
                        description=(
                            f"{sum(fd['raw'].values())} debt markers in this file "
                            f"(weighted: {fd['weighted']}). Address them or split the file."
                        ),
                        target_path=fd["path"],
                        score=fd["weighted"] * 5,
                        data=fd,
                    )

            # Score: invert weighted_per_kloc. Healthy < 1/kLOC, bad > 5/kLOC.
            score = 100.0
            contributors: list[str] = []
            if debt_per_kloc <= 0.5:
                contributors.append(f"debt density = {round(debt_per_kloc, 2)} /kLOC (clean)")
            elif debt_per_kloc <= 2.0:
                score -= 5
                contributors.append(f"debt density = {round(debt_per_kloc, 2)} /kLOC (-5.0)")
            elif debt_per_kloc <= 5.0:
                score -= 15
                contributors.append(f"debt density = {round(debt_per_kloc, 2)} /kLOC (-15.0)")
            else:
                score -= 30
                contributors.append(f"debt density = {round(debt_per_kloc, 2)} /kLOC (-30.0)")

            if total_counts.get("fixme", 0) >= 10:
                score -= 5
                contributors.append(f"{total_counts['fixme']} FIXME markers (-5.0)")

            self._set_score(max(0.0, score), contributors)
            self.run.signals = {
                "debt_total_weighted": round(weighted_total, 1),
                "debt_per_kloc": round(debt_per_kloc, 2),
                "debt_counts": dict(total_counts),
                "vendored_files": vendored_files,
                "generated_loc": generated_loc,
                "total_loc": total_loc,
                "top_debt_files": file_debt[:5],
            }
            self._finish_ok()
        except Exception as exc:  # pragma: no cover
            self._finish_err(f"{type(exc).__name__}: {exc}")
            raise