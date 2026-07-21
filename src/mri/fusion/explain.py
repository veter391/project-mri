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
from mri.fusion.authorship import authorship_evidence_for, weighted_risk_of
from mri.utils import clean_text

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
    # The path is looked up raw but shown cleaned: a filename could carry a
    # terminal escape or a bidi override on a POSIX host, and the prose is
    # printed straight to an operator's terminal.
    shown_path = clean_text(file_path)

    # Risk scores are 0..100 by construction (analyzer findings are clamped). A
    # negative one is a caller bug; reject it once here so every factor derived
    # from base_risk — the plain risk line and the weighted-risk line below —
    # enforces the same invariant, rather than one failing loudly and the other
    # emitting a nonsensical "risk -5/100".
    if base_risk is not None:
        if base_risk < 0:
            raise ValueError(f"base risk must be non-negative; got {base_risk} for {shown_path}")
        factors.append(Factor(
            "risk", f"risk {round(base_risk)}/100.", round(base_risk, 2),
        ))

    # Authorship: prefer a stored blame-derived line-share (6.2); fall back to
    # touch evidence (the strength-weighted signal) when no share was computed.
    shares = await repo.authorship_for_file(conn, file_path, project_id=project_id)
    evidence = (await authorship_evidence_for(conn, [file_path], project_id=project_id)).get(file_path)

    if shares:
        share = shares[0]
        # State the human share truthfully: some attribution methods can produce
        # one. The blame-derived method never does, but the sentence must match
        # the value it carries, not assume the method.
        human = (
            f"{round(share.share_human)}% human"
            if share.share_human > 0
            else "no human share claimed"
        )
        factors.append(Factor(
            "ai_authorship",
            f"{round(share.share_ai)}% of its current lines are AI-authored "
            f"({round(share.share_unattributed)}% unattributed, {human}), "
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

    # The portion of the file's existing risk that sits under agent-modified code:
    # base risk scaled by evidence strength, never above it (ADR-008's complementary
    # signal). Only when there is a risk to weight and write evidence to weight it
    # by, and only if it rounds to a non-zero share — correlation, not blame.
    if base_risk is not None and evidence and evidence.has_write_evidence:
        weighted = weighted_risk_of(base_risk, evidence.evidence_strength)
        if round(weighted) > 0:
            factors.append(Factor(
                "weighted_risk",
                f"about {round(weighted)} of that risk sits under agent-modified code "
                "— correlation, not blame.",
                {"weighted_risk": weighted, "base_risk": round(base_risk, 2)},
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
        # clean_text the summaries: a commit subject / ADR title can carry an
        # ANSI escape or bidi override, and this prose is printed to a terminal
        # (fusion CLI) as well as a browser, mirroring the shown_path treatment.
        names = [clean_text(d.summary) for d in decisions[:3]]
        more = "" if len(decisions) <= 3 else f", and {len(decisions) - 3} more"
        factors.append(Factor(
            "decisions",
            f"{len(decisions)} decision(s) touch it: " + "; ".join(f'“{n}”' for n in names) + more + ".",
            [d.summary for d in decisions],
        ))

        # Consequences of those decisions. Any real move is labelled correlation;
        # the caveat is only appended when there is a claimed correlation to
        # caveat — "no discernible change — correlation, not causation" would be
        # self-contradictory.
        moves: list[str] = []
        conseq_values: list[dict] = []
        any_correlation = False
        for d in decisions:
            if d.id is None:
                continue
            for c in await repo.consequences_for_decision(conn, d.id, project_id=project_id):
                if c.delta is None:
                    continue
                if c.causal_claim == "none":
                    claim = "no discernible change"
                else:
                    claim = f"{c.metric} {c.delta:+g} ({c.causal_claim})"
                    any_correlation = True
                moves.append(claim)
                conseq_values.append({"metric": c.metric, "delta": c.delta, "claim": c.causal_claim})
        if moves:
            caveat = " — correlation, not causation." if any_correlation else "."
            factors.append(Factor(
                "consequences",
                "Since then: " + ", ".join(moves) + caveat,
                conseq_values,
            ))

    return FileExplanation(file_path=shown_path, factors=factors)
