"""Authorship-weighted risk.

This layer answers a narrow, defensible question: of the files a scan already
calls risky, which ones is there evidence an AI coding agent modified, and how
strong is that evidence? It does not answer the broader question the schema's
`authorship_shares` table is shaped for — what fraction of a file's *lines* are
AI-authored — because that fraction cannot be computed honestly from the
evidence available today. ADR-008 records why, with the measurement.

What is honest here:

* A write touch is a tool reporting that it wrote a file, at a specific instant,
  with a confidence below one. Several write touches on a file are evidence the
  agent worked on it; they are not evidence about how many of its current lines
  survive. So evidence *strength* is the strongest single touch, not a sum —
  doing something twice does not make it more certain it happened.
* Absence of an AI touch is not evidence of human authorship. It is absence of
  evidence, which stays unattributed. This module never emits a "human" share.
* The output weights a risk the scan already computed; it does not invent a new
  risk number. A file that is not risky does not become risky by being
  AI-touched, and the weighting says so.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import aiosqlite

__all__ = [
    "AuthorshipEvidence",
    "WeightedRisk",
    "authorship_evidence_for",
    "weight_hotspots",
    "weighted_risk_of",
]

#: SQLite caps a statement at 32,766 bound variables (SQLITE_MAX_VARIABLE_NUMBER
#: since 3.32). One below, so a query with a single extra bound value would
#: still fit.
_SQL_VARIABLE_LIMIT = 32_000


def weighted_risk_of(base_risk: float, evidence_strength: float) -> float:
    """The portion of `base_risk` that sits under agent-modified code: the risk a
    scan already computed, scaled by how strong the evidence is that an agent
    modified the file (0..1). Never exceeds `base_risk` — authorship evidence
    marks where a file's risk sits, it does not amplify it. Correlation, not
    blame: an agent modified a risky file, which is not the same as having caused
    the risk. The single source of this formula, shared by the batch
    `weight_hotspots` and the per-file explanation.
    """
    if base_risk < 0:
        # A negative risk is a caller bug and silently breaks the "weighted never
        # exceeds base" guarantee (round(-50 * 0.0, 2) is -0.0, which is > -50).
        raise ValueError(f"base risk must be non-negative; got {base_risk}")
    return round(base_risk * evidence_strength, 2)


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


@dataclass(slots=True, frozen=True)
class AuthorshipEvidence:
    """What the session logs say about an agent touching one file.

    Every field is a count or a recorded confidence — nothing here is inferred
    beyond what a tool reported doing.
    """

    file_path: str
    ai_write_touches: int
    ai_read_touches: int
    #: An agent deleting a file is authorship evidence too — the strongest kind,
    #: it changed whether the file exists. Counted separately because a deleted
    #: file has no current content to weight risk against, but its evidence must
    #: not read as "no evidence", which is what dropping it would do.
    ai_delete_touches: int
    distinct_ai_sessions: int
    #: The strongest single touch that modified the file — write, create or
    #: delete, 0..1. Evidence that the agent changed this file at all, not how
    #: much of it. Reads never contribute.
    evidence_strength: float
    last_ai_write: datetime | None

    @property
    def has_write_evidence(self) -> bool:
        return self.ai_write_touches > 0 or self.ai_delete_touches > 0


@dataclass(slots=True, frozen=True)
class WeightedRisk:
    """A file's existing risk, annotated with authorship evidence.

    `weighted_risk` is never larger than `base_risk`: authorship evidence marks
    how much of a file's risk sits under agent-modified code, it does not amplify
    the risk itself. A reader who wants the raw number still has `base_risk`.
    """

    file_path: str
    base_risk: float
    evidence: AuthorshipEvidence
    #: base_risk scaled by evidence strength: the portion of this file's risk
    #: that sits under agent-touched code. Correlation, not blame — the agent
    #: modified a risky file, which is not the same as having caused the risk.
    weighted_risk: float


async def authorship_evidence_for(
    conn: aiosqlite.Connection, file_paths: list[str], *, project_id: int
) -> dict[str, AuthorshipEvidence]:
    """Gather per-file authorship evidence for the given paths in one project.

    `project_id` is required: a file path is unique only within a project, and
    two repos in one database sharing a name like "README.md" would otherwise
    blend their AI-touch evidence into one risk number.

    Paths with no touches are simply absent from the result — an empty answer,
    not a fabricated zero-strength row.

    The path list is chunked: SQLite caps a statement at 32,766 bound variables,
    and a large monorepo scan reaches that without any adversarial input. The
    query is aggregated per file with no cross-file joins, so splitting it and
    merging the per-file rows is exact.
    """
    evidence: dict[str, AuthorshipEvidence] = {}
    # One slot of the variable budget goes to project_id; the rest to the paths.
    for batch in _chunks(file_paths, _SQL_VARIABLE_LIMIT - 1):
        # The only value interpolated is a run of `?` placeholders, one per path;
        # every path itself is bound. SQLite has no parameterised form for a
        # variable-length IN list, so placeholder expansion is the standard way.
        placeholders = ",".join("?" * len(batch))
        query = (
            "SELECT "  # noqa: S608 - only `?` placeholders are interpolated; values are bound
            "file_path, "
            "sum(CASE WHEN touch_kind IN ('write','create') THEN 1 ELSE 0 END) AS writes, "
            "sum(CASE WHEN touch_kind = 'read' THEN 1 ELSE 0 END) AS reads, "
            "sum(CASE WHEN touch_kind = 'delete' THEN 1 ELSE 0 END) AS deletes, "
            "count(DISTINCT CASE WHEN touch_kind != 'read' THEN session_id END) AS sessions, "
            "max(CASE WHEN touch_kind != 'read' THEN confidence END) AS strength, "
            "max(CASE WHEN touch_kind != 'read' THEN occurred_at END) AS last_write "
            "FROM session_file_touches "
            f"WHERE project_id = ? AND file_path IN ({placeholders}) "
            "GROUP BY file_path"
        )
        cursor = await conn.execute(query, (project_id, *batch))
        for row in await cursor.fetchall():
            data = dict(row)
            last_write_raw = data["last_write"]
            evidence[data["file_path"]] = AuthorshipEvidence(
                file_path=data["file_path"],
                ai_write_touches=int(data["writes"] or 0),
                ai_read_touches=int(data["reads"] or 0),
                ai_delete_touches=int(data["deletes"] or 0),
                # Sessions that modified the file — read-only sessions are not
                # authors of it, so they do not count here.
                distinct_ai_sessions=int(data["sessions"] or 0),
                # NULL when there were only reads; then the strength is genuinely 0.
                evidence_strength=float(data["strength"]) if data["strength"] is not None else 0.0,
                last_ai_write=(
                    datetime.fromisoformat(last_write_raw)
                    if isinstance(last_write_raw, str)
                    else None
                ),
            )
    return evidence


async def weight_hotspots(
    conn: aiosqlite.Connection, hotspots: dict[str, float], *, project_id: int
) -> list[WeightedRisk]:
    """Annotate one project's scored files with authorship evidence, ordered by
    the risk that sits under agent-touched code.

    `hotspots` maps a repo-relative path to a base risk score the scan produced.
    `project_id` scopes the evidence so a same-named file in another scanned repo
    cannot leak in. Files without write evidence are still returned — a risky
    file nobody has evidence an agent touched is itself a finding, and dropping
    it would bias the picture towards agent involvement.
    """
    if not hotspots:
        return []

    negative = [p for p, r in hotspots.items() if r < 0]
    if negative:
        # Risk scores are 0..100 by construction. A negative one is a caller bug;
        # fail loudly with the offending path (weighted_risk_of also guards, but
        # without the path context this batch call can give).
        raise ValueError(f"base risk must be non-negative; got {hotspots[negative[0]]} for {negative[0]}")

    evidence = await authorship_evidence_for(conn, list(hotspots), project_id=project_id)
    results: list[WeightedRisk] = []
    for path, base_risk in hotspots.items():
        ev = evidence.get(path) or AuthorshipEvidence(
            file_path=path,
            ai_write_touches=0,
            ai_read_touches=0,
            ai_delete_touches=0,
            distinct_ai_sessions=0,
            evidence_strength=0.0,
            last_ai_write=None,
        )
        results.append(
            WeightedRisk(
                file_path=path,
                base_risk=base_risk,
                evidence=ev,
                weighted_risk=weighted_risk_of(base_risk, ev.evidence_strength),
            )
        )
    results.sort(key=lambda r: (r.weighted_risk, r.base_risk), reverse=True)
    return results
