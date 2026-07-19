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
]


@dataclass(slots=True, frozen=True)
class AuthorshipEvidence:
    """What the session logs say about an agent touching one file.

    Every field is a count or a recorded confidence — nothing here is inferred
    beyond what a tool reported doing.
    """

    file_path: str
    ai_write_touches: int
    ai_read_touches: int
    distinct_ai_sessions: int
    #: The strongest single write touch, 0..1. This is the evidence strength:
    #: how sure we are the agent wrote this file at all, not how much of it.
    evidence_strength: float
    last_ai_write: datetime | None

    @property
    def has_write_evidence(self) -> bool:
        return self.ai_write_touches > 0


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
    weighted_risk: float

    @property
    def ai_attributable_risk(self) -> float:
        """The portion of this file's risk that sits under agent-touched code,
        to the strength of the evidence. Correlation, not attribution of blame:
        the agent modified a risky file, which is not the same as the agent
        having caused the risk."""
        return round(self.base_risk * self.evidence.evidence_strength, 2)


async def authorship_evidence_for(
    conn: aiosqlite.Connection, file_paths: list[str]
) -> dict[str, AuthorshipEvidence]:
    """Gather per-file authorship evidence for the given paths.

    One query rather than one per file. Paths with no touches are simply absent
    from the result — an empty answer, not a fabricated zero-strength row.
    """
    if not file_paths:
        return {}

    # The only value interpolated is a run of `?` placeholders, one per path;
    # every path itself is bound. SQLite has no parameterised form for a
    # variable-length IN list, so placeholder expansion is the standard way.
    placeholders = ",".join("?" * len(file_paths))
    query = (
        "SELECT "  # noqa: S608 - only `?` placeholders are interpolated; paths are bound
        "file_path, "
        "sum(CASE WHEN touch_kind IN ('write','create') THEN 1 ELSE 0 END) AS writes, "
        "sum(CASE WHEN touch_kind = 'read' THEN 1 ELSE 0 END) AS reads, "
        "count(DISTINCT session_id) AS sessions, "
        "max(CASE WHEN touch_kind IN ('write','create') THEN confidence END) AS strength, "
        "max(CASE WHEN touch_kind IN ('write','create') THEN occurred_at END) AS last_write "
        "FROM session_file_touches "
        f"WHERE file_path IN ({placeholders}) "
        "GROUP BY file_path"
    )
    cursor = await conn.execute(query, file_paths)
    evidence: dict[str, AuthorshipEvidence] = {}
    for row in await cursor.fetchall():
        data = dict(row)
        last_write_raw = data["last_write"]
        evidence[data["file_path"]] = AuthorshipEvidence(
            file_path=data["file_path"],
            ai_write_touches=int(data["writes"] or 0),
            ai_read_touches=int(data["reads"] or 0),
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
    conn: aiosqlite.Connection, hotspots: dict[str, float]
) -> list[WeightedRisk]:
    """Annotate scored files with authorship evidence, ordered by the risk that
    sits under agent-touched code.

    `hotspots` maps a repo-relative path to a base risk score the scan produced.
    Files without write evidence are still returned — a risky file nobody has
    evidence an agent touched is itself a finding, and dropping it would bias the
    picture towards agent involvement.
    """
    if not hotspots:
        return []

    evidence = await authorship_evidence_for(conn, list(hotspots))
    results: list[WeightedRisk] = []
    for path, base_risk in hotspots.items():
        ev = evidence.get(path) or AuthorshipEvidence(
            file_path=path,
            ai_write_touches=0,
            ai_read_touches=0,
            distinct_ai_sessions=0,
            evidence_strength=0.0,
            last_ai_write=None,
        )
        results.append(
            WeightedRisk(
                file_path=path,
                base_risk=base_risk,
                evidence=ev,
                weighted_risk=round(base_risk * ev.evidence_strength, 2),
            )
        )
    results.sort(key=lambda r: (r.weighted_risk, r.base_risk), reverse=True)
    return results
