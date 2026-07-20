"""A labeled evaluation corpus — scenarios whose right answer is known.

The product's numbers are only trustworthy if they match reality on cases where
reality is known. This builds deterministic scenarios — a real git repo, real
session logs, real ADRs — where the ground truth is constructed, not guessed, so
the eval can measure the computed answer against it.

Everything is synthesised in a temp directory, so the corpus is reproducible and
carries its labels with it rather than depending on a checked-in binary repo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["ConsequenceExpectation", "LabeledCase", "build_calibration_case", "seed_consequence_cases"]


@dataclass(slots=True, frozen=True)
class LabeledCase:
    """A built scenario and the ground truth to score against."""

    name: str
    repo: Path
    workspace: Path
    home: Path
    adr_dir: Path
    #: file path -> the true AI-authored percentage of its current lines.
    expected_ai_pct: dict[str, float]
    #: How many write touches genuinely correspond to a commit (correlation
    #: ground truth): the count that *should* be linked.
    expected_correlated_touches: int
    #: file paths the scan would flag, to drive the explanation.
    hotspots: dict[str, float] = field(default_factory=dict)


def _commit(repo: Any, message: str, when: str) -> None:
    """Commit the staged tree with a fixed author/commit date, via GitPython —
    the same library the rest of the codebase uses for git, so the corpus builder
    carries no subprocess surface."""
    import git

    actor = git.Actor("t", "t@t")
    repo.index.commit(message, author=actor, committer=actor, author_date=when, commit_date=when)


def _turn(seq: int, role: str, cwd: str, parts: list[dict], sid: str) -> dict:
    return {
        "type": role, "sessionId": sid, "cwd": cwd,
        "timestamp": f"2026-04-{seq + 1:02d}T10:00:00.000Z",
        "message": {"content": parts},
    }


def build_calibration_case(base: Path) -> LabeledCase:
    """One scenario with three files of known provenance:

    * ``ai_all.py`` — written entirely in a commit an agent write-touched → 100% AI.
    * ``human_all.py`` — written in a commit no session touched → 0% AI.
    * ``mixed.py`` — its current lines split across an agent commit and a later
      human commit, so its AI share is a known fraction.

    Plus an ADR the agent commit references, so the eval can score authorship
    calibration and session->commit correlation recall against known ground
    truth.

    The consequence false-positive cases (a sub-noise window that must claim
    nothing, a clear move that may claim only correlation) are built separately
    by `seed_consequence_cases`, which the runner scores into the FP rate — so
    the honesty guard is exercised against generated data, not only unit rows.
    """
    import git

    repo_path = base / "repo"
    repo_path.mkdir(parents=True)
    repo = git.Repo.init(repo_path)

    adr_dir = repo_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-x.md").write_text(
        "# ADR-001 — Async ledger\n\n- **Status:** Accepted\n\n## Decision\nSwitch.\n",
        encoding="utf-8",
    )

    # Commit 1 (agent): writes ai_all.py (3 lines) and mixed.py (2 lines).
    (repo_path / "ai_all.py").write_text("a1\na2\na3\n", encoding="utf-8")
    (repo_path / "mixed.py").write_text("m1\nm2\n", encoding="utf-8")
    repo.index.add(["ai_all.py", "mixed.py", "docs/adr/ADR-001-x.md"])
    _commit(repo, "feat: ledger core per ADR-001", "2026-04-10T12:00:00")

    # Commit 2 (human): writes human_all.py, and appends 2 lines to mixed.py.
    (repo_path / "human_all.py").write_text("h1\nh2\nh3\nh4\n", encoding="utf-8")
    (repo_path / "mixed.py").write_text("m1\nm2\nm3\nm4\n", encoding="utf-8")
    repo.index.add(["human_all.py", "mixed.py"])
    _commit(repo, "chore: human additions", "2026-04-20T12:00:00")

    # A session that write-touched exactly the agent commit's files, before it.
    home = base / "home"
    proj = home / ".claude" / "projects" / "slug"
    proj.mkdir(parents=True)
    cwd = str(repo_path)
    (proj / "sess.jsonl").write_text("\n".join(json.dumps(r) for r in [
        _turn(0, "assistant", cwd, [
            {"type": "tool_use", "id": "u1", "name": "Write",
             "input": {"file_path": str(repo_path / "ai_all.py")}},
            {"type": "tool_use", "id": "u2", "name": "Write",
             "input": {"file_path": str(repo_path / "mixed.py")}},
        ], "sess-ai"),
        _turn(1, "user", cwd, [
            {"type": "tool_result", "tool_use_id": "u1", "content": "ok"},
            {"type": "tool_result", "tool_use_id": "u2", "content": "ok"},
        ], "sess-ai"),
    ]) + "\n", encoding="utf-8")

    return LabeledCase(
        name="calibration",
        repo=repo_path,
        workspace=repo_path,
        home=home,
        adr_dir=adr_dir,
        expected_ai_pct={
            "ai_all.py": 100.0,       # whole file in the agent commit
            "human_all.py": 0.0,      # no session touched it
            "mixed.py": 50.0,         # 2 of 4 current lines from the agent commit
        },
        expected_correlated_touches=2,  # ai_all.py and mixed.py, both before commit 1
        hotspots={"ai_all.py": 80.0, "human_all.py": 70.0, "mixed.py": 75.0},
    )


@dataclass(slots=True, frozen=True)
class ConsequenceExpectation:
    """A seeded consequence and the strongest claim it is allowed to make."""

    decision: Any  # a stored Decision (carries its id)
    metric: str
    #: The ground-truth ceiling: 'none' for a sub-noise move, 'correlation' for a
    #: real one. The loop may claim this or weaker, never stronger (never causation).
    expected_claim: str


async def seed_consequence_cases(conn: Any, project_id: int) -> list[ConsequenceExpectation]:
    """Insert two consequence scenarios with known right answers, for the FP rate.

    * **Inconclusive** — a decision followed by a sub-noise metric move (< the
      noise threshold). Ground truth: it must claim nothing ('none').
    * **Correlation** — a decision followed by a clear metric move. Ground truth:
      it may claim 'correlation', never causation.

    Pure DB (scans, analyzer runs, decisions); no git needed. Returns the
    expectations so the runner can score whether the loop ever over-claims.
    """
    from datetime import datetime, timezone

    from mri.db import fusion_repository as repo
    from mri.models.fusion import Decision

    def _dt(day: int) -> datetime:
        return datetime(2026, 5, day, tzinfo=timezone.utc)

    async def _scan_score(day: int, metric: str, value: float) -> None:
        cur = await conn.execute(
            "INSERT INTO scans (project_id, scan_uuid, status, started_at) VALUES (?, ?, 'completed', ?)",
            (project_id, f"conseq-{day}-{metric}", _dt(day).isoformat()),
        )
        await conn.execute(
            "INSERT INTO analyzer_runs (scan_id, analyzer_name, status, score_value, score_label)"
            " VALUES (?, ?, 'completed', ?, ?)",
            (int(cur.lastrowid), metric, value, metric),
        )

    # Inconclusive: 50.0 -> 50.4 across the decision is below the noise threshold.
    await _scan_score(1, "complexity", 50.0)
    await _scan_score(20, "complexity", 50.4)
    d_none = await repo.insert_decision(conn, Decision(
        summary="tidy imports", source="commit", source_ref="noise01",
        project_id=project_id, file_path="quiet.py", decided_at=_dt(10), confidence=0.6,
    ))

    # Correlation: 40.0 -> 60.0 is a clear move; it may claim correlation only.
    await _scan_score(1, "architecture", 40.0)
    await _scan_score(20, "architecture", 60.0)
    d_corr = await repo.insert_decision(conn, Decision(
        summary="split god module", source="commit", source_ref="move01",
        project_id=project_id, file_path="split.py", decided_at=_dt(10), confidence=0.6,
    ))
    await conn.commit()

    return [
        ConsequenceExpectation(d_none, "complexity", "none"),
        ConsequenceExpectation(d_corr, "architecture", "correlation"),
    ]
