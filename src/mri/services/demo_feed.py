"""Demo data generator — produces realistic-ish MRI report for showcase.

When the user clicks "Try demo" or hits /api/demo, we don't want to require
a real repo. This generates a deterministic, realistic report for a fake
"my-legacy-app" project — same shape as a real scan, but with plausible
numbers derived from a seed.
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone

from mri.models.scan import (
    AnalyzerRun,
    Finding,
    Project,
    Report,
    ScanStatus,
    Score,
    Severity,
)


# deterministic seeding for demo data; not cryptographic
def deterministic_seed(*parts: str) -> random.Random:  # nosec B311
    h = hashlib.sha256("|".join(parts).encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))  # nosec B311


def generate_demo_report(slug: str = "my-legacy-app") -> Report:
    """Generate a deterministic demo report for `slug`.

    The numbers are chosen to be realistic-but-pessimistic (legacy app style)
    so the UI looks like a real scan, not a marketing demo with all green scores.
    """
    rng = deterministic_seed(slug)
    started = datetime.now(timezone.utc) - timedelta(seconds=rng.randint(15, 45))

    # ----- Analyzers -----

    # 1. git_history
    commit_count = rng.randint(1800, 5200)
    bus_factor = rng.randint(1, 4)
    hotspots = [
        {"path": f"src/{slug}/core/{rng.choice(['parser','engine','router'])}.py",
         "commits": rng.randint(80, 220),
         "churn": rng.randint(2400, 8200),
         "authors": rng.randint(1, 4)}
        for _ in range(5)
    ]
    islands = [
        f"src/{slug}/legacy/{rng.choice(['migration.py','shim.py','compat.py','__init__.py'])}"
        for _ in range(rng.randint(2, 6))
    ]
    gh_score = max(20, 100 - len(hotspots) * 6 - (4 - bus_factor) * 12 - len(islands) * 3)
    gh_findings = []
    for h in hotspots:
        composite = h["commits"] * (1 + (h["churn"] ** 0.5) / 10)
        h["composite"] = round(composite, 1)
        sev = Severity.HIGH if composite > 80 else Severity.MEDIUM if composite > 40 else Severity.LOW
        gh_findings.append(Finding(
            severity=sev,
            category="hotspot",
            title=f"Hotspot: {h['path']}",
            description=f"{h['commits']} commits, ~{h['churn']:,} lines churn, {h['authors']} authors.",
            target_path=h["path"],
            score=min(100.0, h["commits"] * 0.5),
            data=h,
        ))
    for p in islands:
        gh_findings.append(Finding(
            severity=Severity.MEDIUM,
            category="knowledge_island",
            title=f"Knowledge island: {p}",
            description=f"Only 1 author across {rng.randint(5, 30)} commits.",
            target_path=p,
            score=60.0,
        ))

    # 2. architecture
    module_count = rng.randint(8, 18)
    total_loc = rng.randint(40_000, 140_000)
    largest_share = round(rng.uniform(0.35, 0.65), 2)
    arch_score = max(30, 100 - int((largest_share - 0.3) * 100))
    arch_findings = []
    if largest_share > 0.4:
        arch_findings.append(Finding(
            severity=Severity.HIGH if largest_share > 0.55 else Severity.MEDIUM,
            category="god_module",
            title=f"God module: src/{slug}/core/",
            description=f"src/{slug}/core/ holds {int(total_loc * largest_share):,} LOC — {round(largest_share * 100)}% of codebase.",
            target_path=f"src/{slug}/core/",
            score=80.0,
            data={"share": largest_share, "loc": int(total_loc * largest_share)},
        ))
    deep_modules = rng.randint(0, 3)
    for i in range(deep_modules):
        arch_findings.append(Finding(
            severity=Severity.MEDIUM,
            category="deep_nesting",
            title=f"Deep nesting: src/{slug}/services/v2/api/internal/ (depth 6)",
            description="Path nesting reaches depth 6.",
            target_path=f"src/{slug}/services/v2/api/internal/",
            score=50.0,
        ))

    # 3. dependencies
    cycle_count = rng.randint(0, 4)
    dep_score = max(30, 100 - cycle_count * 18 - rng.randint(0, 10))
    dep_findings = []
    cycles = []
    for i in range(cycle_count):
        if rng.random() > 0.5:
            cyc = [f"src/{slug}/auth/session.py", f"src/{slug}/auth/oauth.py", f"src/{slug}/users/models.py"]
        else:
            cyc = [f"src/{slug}/billing/invoice.py", f"src/{slug}/billing/tax.py", f"src/{slug}/billing/export.py", f"src/{slug}/reports/generator.py"]
        cycles.append(cyc)
        dep_findings.append(Finding(
            severity=Severity.HIGH if len(cyc) <= 4 else Severity.MEDIUM,
            category="import_cycle",
            title=f"Import cycle: {' → '.join(cyc)}",
            description=f"Cycle of length {len(cyc)}.",
            score=70.0,
            data={"members": cyc},
        ))

    # 4. complexity
    file_count = rng.randint(180, 480)
    longest = rng.randint(800, 1800)
    comp_score = max(40, 100 - rng.randint(0, 25))
    comp_findings = []
    long_file = f"src/{slug}/core/{rng.choice(['engine.py','router.py','parser.py'])}"
    comp_findings.append(Finding(
        severity=Severity.HIGH if longest > 1500 else Severity.MEDIUM,
        category="long_file",
        title=f"Long file: {long_file} ({longest:,} LOC)",
        description=f"File has {longest:,} lines. Split it.",
        target_path=long_file,
        score=min(100.0, longest / 15),
    ))
    for i in range(rng.randint(2, 5)):
        comp_findings.append(Finding(
            severity=Severity.MEDIUM,
            category="long_function",
            title=f"Long function: process_{rng.choice(['request','event','job','payment'])}() in src/{slug}/core/handler.py ({rng.randint(70, 180)} lines)",
            description=f"Function spans {rng.randint(70, 180)} lines.",
            target_path=f"src/{slug}/core/handler.py",
            target_symbol=f"process_{i}",
            score=60.0,
        ))

    # 5. tech_debt
    todo_count = rng.randint(20, 80)
    fixme_count = rng.randint(5, 20)
    debt_score = max(30, 100 - (todo_count // 4) - (fixme_count * 2))
    debt_findings = []
    for i in range(min(8, todo_count)):
        debt_findings.append(Finding(
            severity=Severity.LOW,
            category="debt_todo",
            title=f"TODO at src/{slug}/{rng.choice(['utils.py','helpers.py','legacy.py','shim.py'])}:{rng.randint(20, 400)}",
            description=f"TODO at line {rng.randint(20, 400)}.",
            target_path=f"src/{slug}/utils.py",
            score=10.0,
        ))
    debt_findings.append(Finding(
        severity=Severity.MEDIUM,
        category="debt_hotspot",
        title=f"Debt hotspot: src/{slug}/legacy/migration.py",
        description=f"{todo_count + fixme_count} debt markers in this file.",
        target_path=f"src/{slug}/legacy/migration.py",
        score=50.0,
    ))

    # 6. coupling
    coupling_score = max(40, 100 - rng.randint(0, 30))
    coupling_findings = [
        Finding(
            severity=Severity.HIGH,
            category="stable_concrete",
            title=f"Painful to change: src/{slug}/core/models.py",
            description="Ca=14, Ce=3, I=0.18 (stable), A=0.10 (concrete), D=0.51.",
            target_path=f"src/{slug}/core/models.py",
            score=85.0,
            data={"Ca": 14, "Ce": 3, "I": 0.18, "A": 0.10, "D": 0.51},
        ),
        Finding(
            severity=Severity.MEDIUM,
            category="stable_concrete",
            title=f"Painful to change: src/{slug}/auth/session.py",
            description="Ca=8, Ce=2, I=0.20, A=0.05, D=0.53.",
            target_path=f"src/{slug}/auth/session.py",
            score=70.0,
            data={"Ca": 8, "Ce": 2, "I": 0.20, "A": 0.05, "D": 0.53},
        ),
    ]

    runs = [
        AnalyzerRun(
            name="git_history", status=ScanStatus.COMPLETED,
            started_at=started + timedelta(milliseconds=200),
            finished_at=started + timedelta(milliseconds=4200),
            duration_ms=4000,
            score=Score(label="history_health", value=gh_score, band=Score.band_for(gh_score),
                        contributors=[f"bus_factor = {bus_factor}", f"{len(hotspots)} hotspots"]),
            findings=gh_findings,
            signals={"commit_count": commit_count, "bus_factor": bus_factor,
                     "hotspots": hotspots, "islands": islands,
                     "authors": rng.randint(8, 22)},
        ),
        AnalyzerRun(
            name="architecture", status=ScanStatus.COMPLETED,
            started_at=started + timedelta(milliseconds=4400),
            finished_at=started + timedelta(milliseconds=6800),
            duration_ms=2400,
            score=Score(label="architecture_health", value=arch_score, band=Score.band_for(arch_score),
                        contributors=[f"{module_count} modules", f"largest = {round(largest_share * 100)}%"]),
            findings=arch_findings,
            signals={"module_count": module_count, "total_loc": total_loc,
                     "largest_share": largest_share},
        ),
        AnalyzerRun(
            name="dependencies", status=ScanStatus.COMPLETED,
            started_at=started + timedelta(milliseconds=7000),
            finished_at=started + timedelta(milliseconds=12500),
            duration_ms=5500,
            score=Score(label="dependency_health", value=dep_score, band=Score.band_for(dep_score),
                        contributors=[f"{cycle_count} cycles"]),
            findings=dep_findings,
            signals={"cycle_count": cycle_count, "edge_count": rng.randint(800, 2400)},
        ),
        AnalyzerRun(
            name="complexity", status=ScanStatus.COMPLETED,
            started_at=started + timedelta(milliseconds=12700),
            finished_at=started + timedelta(milliseconds=16400),
            duration_ms=3700,
            score=Score(label="complexity_health", value=comp_score, band=Score.band_for(comp_score),
                        contributors=[f"{file_count} files", f"longest = {longest} LOC"]),
            findings=comp_findings,
            signals={"file_count": file_count, "longest": longest},
        ),
        AnalyzerRun(
            name="tech_debt", status=ScanStatus.COMPLETED,
            started_at=started + timedelta(milliseconds=16600),
            finished_at=started + timedelta(milliseconds=18300),
            duration_ms=1700,
            score=Score(label="debt_index", value=debt_score, band=Score.band_for(debt_score),
                        contributors=[f"{todo_count} TODOs", f"{fixme_count} FIXMEs"]),
            findings=debt_findings,
            signals={"todo_count": todo_count, "fixme_count": fixme_count},
        ),
        AnalyzerRun(
            name="coupling", status=ScanStatus.COMPLETED,
            started_at=started + timedelta(milliseconds=18500),
            finished_at=started + timedelta(milliseconds=19800),
            duration_ms=1300,
            score=Score(label="coupling_health", value=coupling_score, band=Score.band_for(coupling_score),
                        contributors=["2 painful modules"]),
            findings=coupling_findings,
            signals={"painful_count": 2},
        ),
    ]

    # Compose overall
    weights = {"git_history": 1.0, "architecture": 1.2, "dependencies": 1.0,
               "complexity": 1.0, "tech_debt": 1.0, "coupling": 0.9}
    total_w = sum(weights.values())
    overall = sum(r.score.value * weights[r.name] for r in runs) / total_w
    composition = [
        f"{r.score.label} = {r.score.value} (weight {round(weights[r.name] / total_w, 2)})"
        for r in runs
    ]

    all_findings = []
    for r in runs:
        all_findings.extend(r.findings)
    all_findings.sort(key=lambda f: -(f.score or 0))

    counts: dict[str, int] = {}
    for f in all_findings:
        sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
        counts[sev] = counts.get(sev, 0) + 1

    finished = datetime.now(timezone.utc)
    duration_ms = int((finished - started).total_seconds() * 1000)

    return Report(
        scan_uuid="",
        project=Project(path=f"/home/dev/{slug}", name=slug, default_branch="main"),
        started_at=started,
        finished_at=finished,
        duration_ms=duration_ms,
        scores=[r.score for r in runs],
        overall_health=round(overall, 1),
        overall_band=Score.band_for(overall),
        runs=runs,
        findings=all_findings[:200],
        stats={
            "file_count": file_count,
            "loc_total": total_loc,
            "commit_count": commit_count,
            "languages": {"Python": {"files": int(file_count * 0.7), "loc": int(total_loc * 0.72)},
                          "TypeScript": {"files": int(file_count * 0.18), "loc": int(total_loc * 0.18)},
                          "Other": {"files": int(file_count * 0.12), "loc": int(total_loc * 0.10)}},
            "finding_counts": counts,
        },
        composition=composition,
    )