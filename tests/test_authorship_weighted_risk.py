"""Authorship-weighted risk.

The honesty of this layer is the whole point, so the tests are mostly about what
it refuses to claim: no human share, no line percentage, no risk it did not
already have, and no certainty. See ADR-008 for why line-shares are deferred.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mri.db import fusion_repository as repo
from mri.db.migrator import migrate
from mri.db.repository import get_connection
from mri.fusion import authorship_evidence_for, weight_hotspots
from mri.models.fusion import Session, SessionFileTouch


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "aw.db"
    migrate(path)
    return path


async def _session(conn, external_id: str) -> int:
    session = await repo.upsert_session(
        conn, Session(source="claude_code", external_id=external_id, content_stored=False)
    )
    assert session.id is not None
    return session.id


async def _touch(conn, session_id: int, path: str, kind: str, confidence: float, when: str | None = None):
    await repo.insert_session_file_touch(
        conn,
        SessionFileTouch(
            session_id=session_id, file_path=path, touch_kind=kind,  # type: ignore[arg-type]
            confidence=confidence, occurred_at=when,  # type: ignore[arg-type]
        ),
    )


async def test_evidence_strength_is_the_strongest_touch_not_the_sum(db: Path):
    """Doing something twice does not make it more certain it happened. Ten
    write touches at 0.9 are evidence at 0.9, not at 9.0 or 0.99."""
    async with get_connection(db) as conn:
        sid = await _session(conn, "s1")
        for _ in range(10):
            await _touch(conn, sid, "src/a.py", "write", 0.9)
        evidence = await authorship_evidence_for(conn, ["src/a.py"])
    ev = evidence["src/a.py"]
    assert ev.ai_write_touches == 10
    assert ev.evidence_strength == 0.9


async def test_reads_carry_no_authorship_strength(db: Path):
    """Reading a file is engagement, not authorship. A file only ever read has
    zero evidence strength however many times it was opened."""
    async with get_connection(db) as conn:
        sid = await _session(conn, "s1")
        await _touch(conn, sid, "src/a.py", "read", 0.9)
        await _touch(conn, sid, "src/a.py", "read", 0.9)
        evidence = await authorship_evidence_for(conn, ["src/a.py"])
    ev = evidence["src/a.py"]
    assert ev.ai_read_touches == 2
    assert ev.ai_write_touches == 0
    assert ev.evidence_strength == 0.0
    assert not ev.has_write_evidence


async def test_a_file_with_no_touches_is_absent_not_a_fabricated_zero(db: Path):
    """An empty answer is honest; a zero-strength row would be an assertion we
    looked and found nothing, which we can only make where we actually queried."""
    async with get_connection(db) as conn:
        evidence = await authorship_evidence_for(conn, ["src/untouched.py"])
    assert evidence == {}


async def test_weighting_never_exceeds_the_base_risk(db: Path):
    """Authorship evidence marks where risk sits; it does not amplify it. Even
    at full evidence strength the weighted risk equals, never exceeds, the base."""
    async with get_connection(db) as conn:
        sid = await _session(conn, "s1")
        await _touch(conn, sid, "src/hot.py", "write", 1.0)
        weighted = await weight_hotspots(conn, {"src/hot.py": 80.0})
    assert weighted[0].weighted_risk == 80.0
    assert weighted[0].weighted_risk <= weighted[0].base_risk


async def test_a_risky_file_with_no_ai_evidence_is_kept_and_weighted_to_zero(db: Path):
    """Dropping files nobody has evidence an agent touched would bias the whole
    picture towards agent involvement. They stay, weighted to zero."""
    async with get_connection(db) as conn:
        weighted = await weight_hotspots(conn, {"src/human.py": 90.0})
    assert len(weighted) == 1
    assert weighted[0].base_risk == 90.0
    assert weighted[0].weighted_risk == 0.0
    assert not weighted[0].evidence.has_write_evidence


async def test_no_human_share_is_ever_emitted(db: Path):
    """The layer has no concept of a human share. Absence of an AI touch is
    absence of evidence, which is unattributed — not a claim a human wrote it."""
    async with get_connection(db) as conn:
        sid = await _session(conn, "s1")
        await _touch(conn, sid, "src/a.py", "write", 0.9)
        evidence = await authorship_evidence_for(conn, ["src/a.py"])
    ev = evidence["src/a.py"]
    assert not hasattr(ev, "share_human")
    assert not hasattr(ev, "ai_attributable_lines")


async def test_results_are_ordered_by_ai_attributable_risk(db: Path):
    """The file a reader should look at first is the one whose risk most sits
    under agent-touched code — high base risk with strong evidence."""
    async with get_connection(db) as conn:
        sid = await _session(conn, "s1")
        await _touch(conn, sid, "src/strong_hot.py", "write", 0.9)
        await _touch(conn, sid, "src/weak_hot.py", "write", 0.3)
        weighted = await weight_hotspots(
            conn,
            {"src/strong_hot.py": 70.0, "src/weak_hot.py": 95.0, "src/untouched_hot.py": 99.0},
        )
    assert weighted[0].file_path == "src/strong_hot.py"  # 70 * 0.9 = 63
    assert weighted[1].file_path == "src/weak_hot.py"    # 95 * 0.3 = 28.5
    assert weighted[2].file_path == "src/untouched_hot.py"  # 99 * 0 = 0


async def test_distinct_sessions_are_counted(db: Path):
    """Two agents, or two runs, writing the same file is worth distinguishing
    from one doing it repeatedly."""
    async with get_connection(db) as conn:
        s1 = await _session(conn, "s1")
        s2 = await _session(conn, "s2")
        await _touch(conn, s1, "src/a.py", "write", 0.9)
        await _touch(conn, s2, "src/a.py", "write", 0.9)
        evidence = await authorship_evidence_for(conn, ["src/a.py"])
    assert evidence["src/a.py"].distinct_ai_sessions == 2


async def test_empty_inputs_are_handled(db: Path):
    async with get_connection(db) as conn:
        assert await authorship_evidence_for(conn, []) == {}
        assert await weight_hotspots(conn, {}) == []


# ---------------------------------------------------------------------------
# What the block-6 audits found
# ---------------------------------------------------------------------------


async def test_a_deleted_file_is_authorship_evidence_not_silence(db: Path):
    """An agent deleting a file is the strongest authorship signal, not the
    absence of one. Dropping it made a deleted file read like an untouched one."""
    async with get_connection(db) as conn:
        sid = await _session(conn, "s1")
        await _touch(conn, sid, "src/gone.py", "delete", 0.9)
        evidence = await authorship_evidence_for(conn, ["src/gone.py"])
    ev = evidence["src/gone.py"]
    assert ev.ai_delete_touches == 1
    assert ev.evidence_strength == 0.9, "a delete carries modification strength"
    assert ev.has_write_evidence, "a deleted file is not 'no evidence'"


async def test_read_only_sessions_do_not_count_as_authors(db: Path):
    """distinct_ai_sessions is about who modified the file. A session that only
    read it is not an author of it."""
    async with get_connection(db) as conn:
        writer = await _session(conn, "writer")
        reader = await _session(conn, "reader")
        await _touch(conn, writer, "src/a.py", "write", 0.9)
        await _touch(conn, reader, "src/a.py", "read", 0.9)
        evidence = await authorship_evidence_for(conn, ["src/a.py"])
    ev = evidence["src/a.py"]
    assert ev.distinct_ai_sessions == 1, "only the writing session counts as an author"
    assert ev.ai_read_touches == 1, "the read is still recorded, just not as authorship"


async def test_more_paths_than_the_sql_variable_limit(db: Path):
    """SQLite caps a statement at 32,766 bound variables. A large monorepo
    reaches that with no adversarial input; the query is chunked so it does
    not crash."""
    async with get_connection(db) as conn:
        sid = await _session(conn, "s1")
        await _touch(conn, sid, "src/real.py", "write", 0.9)
        paths = [f"src/f{i}.py" for i in range(40_000)] + ["src/real.py"]
        evidence = await authorship_evidence_for(conn, paths)
    assert set(evidence) == {"src/real.py"}, "chunking must not lose or duplicate the one real row"
    assert evidence["src/real.py"].ai_write_touches == 1


async def test_negative_base_risk_is_refused(db: Path):
    """A negative risk is a caller bug and silently breaks the weighting
    invariant (round(-50 * 0.0, 2) == -0.0, which exceeds -50). It fails loudly."""
    async with get_connection(db) as conn:
        with pytest.raises(ValueError, match="non-negative"):
            await weight_hotspots(conn, {"src/a.py": -50.0})


async def test_a_delete_makes_a_hotspot_weight_nonzero(db: Path):
    """The bias-toward-involvement guard cuts both ways: an agent-deleted path
    that is somehow still scored must carry its evidence, not read as zero."""
    async with get_connection(db) as conn:
        sid = await _session(conn, "s1")
        await _touch(conn, sid, "src/gone.py", "delete", 0.8)
        weighted = await weight_hotspots(conn, {"src/gone.py": 50.0})
    assert weighted[0].weighted_risk == 40.0
    assert weighted[0].evidence.ai_delete_touches == 1
