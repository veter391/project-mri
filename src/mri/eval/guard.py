"""The over-claim guard — the product's trust claims as executable assertions.

Every honesty rule the fusion layers enforce in their own code is re-checked
here, against the *stored* data, so it can run in CI over any real database and
fail the build if the product ever claims more than its evidence supports. The
layers enforce these at write time; this is the independent audit that they held.

The rules, and why each is a trust claim:

* An authorship split accounts for the whole file, and its shares stay in range —
  a split that does not sum to 100, or a share outside 0..100, is a broken number.
* Nothing is ever certain: no authorship, touch, decision or consequence
  confidence reaches 1.0. Attribution from correlated evidence is an estimate.
* No consequence claims **causation**. The loop reports correlation, and the
  schema forbids causation, but the guard says so out loud.
* A sub-noise consequence claims **nothing** (causal_claim 'none', confidence 0)
  — the inconclusive case is never dressed as a clean finding.
* A blame-derived authorship share never asserts a **human** portion: absence of
  AI evidence is unattributed, not human.

`audit_project` returns every violation found. Zero violations is the pass
condition a CI gate asserts.
"""
from __future__ import annotations

from dataclasses import dataclass

import aiosqlite

__all__ = ["Violation", "audit_project"]

#: Deltas at or below this are within re-scoring noise and must not be a
#: correlation — mirrors consequences.NOISE_THRESHOLD.
_NOISE = 1.0


@dataclass(slots=True, frozen=True)
class Violation:
    rule: str
    detail: str
    #: The row that broke the rule, for a human chasing it down.
    ref: str


async def audit_project(conn: aiosqlite.Connection, project_id: int) -> list[Violation]:
    """Every over-claim in a project's stored fusion data. Empty means clean."""
    out: list[Violation] = []

    # --- authorship shares ---
    cursor = await conn.execute(
        "SELECT id, file_path, share_ai, share_human, share_unattributed, method, confidence"
        " FROM authorship_shares WHERE project_id = ?",
        (project_id,),
    )
    for row in await cursor.fetchall():
        sid, path, ai, human, unattr, method, conf = row
        total = float(ai) + float(human) + float(unattr)
        if abs(total - 100.0) >= 0.01:
            out.append(Violation("shares_sum_to_100", f"shares total {total:.2f}", f"authorship {sid} {path}"))
        for name, val in (("ai", ai), ("human", human), ("unattributed", unattr)):
            if not (0.0 <= float(val) <= 100.0):
                out.append(Violation("share_in_range", f"{name}={val}", f"authorship {sid} {path}"))
        if float(conf) >= 1.0:
            out.append(Violation("confidence_below_1", f"confidence {conf}", f"authorship {sid} {path}"))
        if method == "blame_session_commit" and float(human) > 0.0:
            out.append(Violation(
                "no_human_from_blame", f"human={human} from blame method", f"authorship {sid} {path}"
            ))

    # --- session file touches: correlation is never certain ---
    cursor = await conn.execute(
        "SELECT id, file_path, confidence FROM session_file_touches"
        " WHERE project_id = ? AND confidence >= 1.0",
        (project_id,),
    )
    for sid, path, conf in await cursor.fetchall():
        out.append(Violation("touch_confidence_below_1", f"confidence {conf}", f"touch {sid} {path}"))

    # --- consequences: correlation only, never certain, inconclusive claims nothing ---
    cursor = await conn.execute(
        "SELECT c.id, c.metric, c.causal_claim, c.confidence, c.delta"
        " FROM consequences c JOIN decisions d ON d.id = c.decision_id"
        " WHERE d.project_id = ?",
        (project_id,),
    )
    for cid, metric, claim, conf, delta in await cursor.fetchall():
        ref = f"consequence {cid} {metric}"
        if claim == "causation":
            out.append(Violation("never_causation", "causal_claim is causation", ref))
        if float(conf) >= 1.0:
            out.append(Violation("confidence_below_1", f"confidence {conf}", ref))
        if delta is not None and abs(float(delta)) < _NOISE and claim == "correlation":
            out.append(Violation(
                "inconclusive_claims_nothing",
                f"delta {delta} within noise but claims correlation", ref,
            ))

    # --- decisions: a stated confidence is never certainty ---
    cursor = await conn.execute(
        "SELECT id, source, confidence FROM decisions WHERE project_id = ? AND confidence >= 1.0",
        (project_id,),
    )
    for did, source, conf in await cursor.fetchall():
        out.append(Violation("confidence_below_1", f"confidence {conf}", f"decision {did} {source}"))

    return out
