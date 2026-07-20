"""The fusion pipeline — one call that runs the whole loop for a project.

The individual layers (ingest, correlation, authorship, decisions, consequences,
explanation) each do one honest thing. This composes them in the right order and
returns per-file explanations, so a surface — a CLI command, an MCP tool, an API
route — has one function to call rather than six to sequence correctly.

Order matters and is enforced here: sessions must be ingested before their
touches can be correlated to commits; commits must be correlated before a line
share can be computed; decisions must be ingested before they can be linked or
surfaced. A caller cannot get that wrong by calling this.

Every step is the audited layer beneath it, unchanged. This adds no new
inference — it only runs what already exists, in sequence, scoped to one
project, and gathers the result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite

from mri.fusion.correlation import CorrelationResult, correlate_touches_to_commits
from mri.fusion.decisions import ingest_adrs, ingest_commits, link_related_decisions
from mri.fusion.explain import FileExplanation, explain_file
from mri.fusion.line_authorship import compute_file_authorship, persist_file_authorship
from mri.ingest import IngestResult, ingest_workspace

__all__ = ["FusionReport", "run_fusion"]


@dataclass(slots=True)
class FusionReport:
    """What one fusion run produced — counts from each stage, and the per-file
    explanations for the files asked about. Nothing here is summarised away."""

    ingest: IngestResult = field(default_factory=IngestResult)
    correlation: CorrelationResult = field(default_factory=CorrelationResult)
    adrs: int = 0
    commits: int = 0
    decision_links: int = 0
    authored_files: int = 0
    explanations: list[FileExplanation] = field(default_factory=list)


async def run_fusion(
    conn: aiosqlite.Connection,
    git_repo: Any,
    workspace: Path,
    *,
    project_id: int,
    hotspots: dict[str, float] | None = None,
    adr_dir: Path | None = None,
    store_content: bool = False,
    commit_max_count: int = 2000,
    home: Path | None = None,
) -> FusionReport:
    """Run the full fusion loop for a project and explain its hotspot files.

    `hotspots` maps repo-relative paths to the base risk a scan produced; those
    files get a computed line-share and a per-file explanation. With no hotspots
    the loop still ingests and correlates everything (so the data is there for a
    later query), it just produces no explanations.

    Every stage is scoped to `project_id`, and each is the audited layer beneath:
    this function sequences, it does not re-implement.
    """
    import asyncio

    from mri.fusion.correlation import file_commit_history

    report = FusionReport()

    # Walk the commit history once, bounded, and share it across the stages that
    # need it (correlation and commit->file linking) — otherwise a single run
    # would walk the whole log twice, and unbounded. The bound is the same cap
    # that limits commit ingest.
    history = await asyncio.to_thread(
        file_commit_history, git_repo, max_count=commit_max_count
    )

    # 1. Sessions -> 2. their touches correlated to the commits that carried them.
    report.ingest = await ingest_workspace(
        conn, workspace, project_id=project_id, store_content=store_content, home=home
    )
    report.correlation = await correlate_touches_to_commits(
        conn, git_repo, project_id=project_id, history=history
    )

    # 3. Decisions from ADRs and commits, then cross-source links, then commit
    #    decisions linked to the files they changed (done inside ingest_commits).
    if adr_dir is not None:
        report.adrs = await ingest_adrs(conn, adr_dir, project_id=project_id)
    report.commits = await ingest_commits(
        conn, git_repo, project_id=project_id, max_count=commit_max_count, history=history
    )
    report.decision_links = await link_related_decisions(conn, project_id=project_id)

    # 4. Line-share authorship for the files under attention, then the fused
    #    per-file explanation.
    if hotspots:
        shares = await compute_file_authorship(
            conn, git_repo, list(hotspots), project_id=project_id
        )
        report.authored_files = await persist_file_authorship(
            conn, shares, project_id=project_id
        )
        for path, base_risk in hotspots.items():
            report.explanations.append(
                await explain_file(conn, path, project_id=project_id, base_risk=base_risk)
            )

    return report
