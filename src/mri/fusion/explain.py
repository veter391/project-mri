"""Per-file explanation — facts over magic scores (block 6.3).

The manifesto is "explain before recommending; facts over magic scores." This
layer is where the fusion pieces become the one sentence the product exists to
say: for a file, *why* it is worth attention and *who touched what*, with every
clause traceable to a stored fact.

It produces two things that cannot disagree, because one is rendered from the
other: a machine-readable list of `factors` (each a name, a value, and the
evidence behind it) and a `prose` string built by joining exactly those factors.
Nothing appears in the prose that is not a factor, and no factor is invented —
a clause is omitted when its evidence is absent, rather than filled with a guess.

The honesty rules the layers below enforce carry through to the wording:
unattributed lines are never described as human, a consequence is always
"correlation", and an authorship figure is stated with the sub-1.0 confidence it
was computed at.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import aiosqlite

from mri.db import fusion_repository as repo
from mri.fusion.authorship import authorship_evidence_for

__all__ = ["Factor", "FileExplanation", "explain_file"]


@dataclass(slots=True, frozen=True)
class Factor:
    """One statement the explanation makes, and the evidence for it."""

    name: str
    #: A short human phrase — this is what the prose is built from.
    statement: str
    #: The machine-readable value behind the phrase (a number, a list, a label).
    value: object


@dataclass(slots=True, frozen=True)
class FileExplanation:
    file_path: str
    factors: list[Factor] = field(default_factory=list)

    @property
    def prose(self) -> str:
        """The factors joined into a sentence. Built from `factors` alone, so the
        prose and the machine-readable list can never disagree."""
        if not self.factors:
            return f"{self.file_path}: no fusion evidence — not touched by a recorded agent session."
        body = " ".join(f.statement for f in self.factors)
        return f"{self.file_path}: {body}"


async def explain_file(
    conn: aiosqlite.Connection,
    file_path: str,
    *,
    project_id: int,
    base_risk: float | None = None,
) -> FileExplanation:
    """Fuse a file's risk, authorship, decisions and consequences into an
    explanation. Reads only what is stored; a piece with no evidence contributes
    no clause rather than a fabricated one.
    """
    factors: list[Factor] = []

    if base_risk is not None:
        factors.append(Factor(
            "risk", f"risk {round(base_risk)}/100.", round(base_risk, 2),
        ))

    # Authorship: prefer a stored blame-derived line-share (6.2); fall back to
    # touch evidence (the strength-weighted signal) when no share was computed.
    shares = await repo.authorship_for_file(conn, file_path, project_id=project_id)
    evidence = (await authorship_evidence_for(conn, [file_path], project_id=project_id)).get(file_path)

    if shares:
        share = shares[0]
        factors.append(Factor(
            "ai_authorship",
            f"{round(share.share_ai)}% of its current lines are AI-authored "
            f"({round(share.share_unattributed)}% unattributed, no human share claimed), "
            f"at confidence {share.confidence}.",
            {"ai": share.share_ai, "unattributed": share.share_unattributed,
             "human": share.share_human, "confidence": share.confidence},
        ))
    elif evidence and evidence.has_write_evidence:
        factors.append(Factor(
            "ai_evidence",
            f"an agent has write evidence on it (strength {evidence.evidence_strength}); "
            "a line-share has not been computed.",
            {"strength": evidence.evidence_strength},
        ))

    if evidence and evidence.distinct_ai_sessions:
        s = evidence.distinct_ai_sessions
        factors.append(Factor(
            "sessions",
            f"Traced to {s} agent session{'s' if s != 1 else ''} "
            f"({evidence.ai_write_touches} write, {evidence.ai_read_touches} read).",
            {"sessions": s, "writes": evidence.ai_write_touches, "reads": evidence.ai_read_touches},
        ))

    decisions = await repo.decisions_affecting_file(conn, file_path, project_id=project_id)
    if decisions:
        names = [d.summary for d in decisions[:3]]
        more = "" if len(decisions) <= 3 else f", and {len(decisions) - 3} more"
        factors.append(Factor(
            "decisions",
            f"{len(decisions)} decision(s) touch it: " + "; ".join(f'“{n}”' for n in names) + more + ".",
            [d.summary for d in decisions],
        ))

        # Consequences of those decisions, always labelled correlation.
        moves: list[str] = []
        conseq_values: list[dict] = []
        for d in decisions:
            if d.id is None:
                continue
            for c in await repo.consequences_for_decision(conn, d.id, project_id=project_id):
                if c.delta is None:
                    continue
                claim = "no discernible change" if c.causal_claim == "none" else (
                    f"{c.metric} {c.delta:+g} ({c.causal_claim})"
                )
                moves.append(claim)
                conseq_values.append({"metric": c.metric, "delta": c.delta, "claim": c.causal_claim})
        if moves:
            factors.append(Factor(
                "consequences",
                "Since then: " + ", ".join(moves) + " — correlation, not causation.",
                conseq_values,
            ))

    return FileExplanation(file_path=file_path, factors=factors)
