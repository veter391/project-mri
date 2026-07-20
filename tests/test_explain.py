"""Per-file explanation — facts over magic scores (block 6.3).

The DoD: a human-readable "why this is risky and who touched what" string plus a
machine-readable factor list, and the two must stay consistent. They cannot
diverge here because the prose is rendered from the factors — these tests pin
that, and the honesty rules the wording must carry.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from mri.db import fusion_repository as repo
from mri.db.migrator import migrate
from mri.db.repository import get_connection
from mri.fusion import explain_file
from mri.models.fusion import (
    AuthorshipShare,
    Consequence,
    Decision,
    Session,
    SessionFileTouch,
)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "exp.db"
    migrate(path)
    return path


async def _project(conn) -> int:
    pid = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('p', '/p')")).lastrowid)
    await conn.commit()
    return pid


async def _ai_touch(conn, pid, path, kind="write"):
    s = await repo.upsert_session(conn, Session(source="claude_code", external_id="s1", project_id=pid))
    await repo.insert_session_file_touch(conn, SessionFileTouch(
        session_id=s.id, project_id=pid, file_path=path, touch_kind=kind, confidence=0.9,
    ))


async def test_prose_is_built_only_from_the_factors(db: Path):
    """Consistency by construction: every factor's statement appears in the
    prose, and the prose says nothing a factor does not."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _ai_touch(conn, pid, "src/a.py")
        await repo.insert_authorship_share(conn, AuthorshipShare(
            project_id=pid, file_path="src/a.py", share_ai=80, share_human=0,
            share_unattributed=20, method="blame_session_commit", confidence=0.9,
        ))
        exp = await explain_file(conn, "src/a.py", project_id=pid, base_risk=70.0)
    assert exp.factors, "there is evidence, so there are factors"
    for factor in exp.factors:
        assert factor.statement in exp.prose, f"factor {factor.name} missing from prose"


async def test_unattributed_is_never_described_as_human(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _ai_touch(conn, pid, "src/a.py")
        await repo.insert_authorship_share(conn, AuthorshipShare(
            project_id=pid, file_path="src/a.py", share_ai=40, share_human=0,
            share_unattributed=60, method="blame_session_commit", confidence=0.9,
        ))
        exp = await explain_file(conn, "src/a.py", project_id=pid)
    assert "unattributed" in exp.prose
    assert "no human share claimed" in exp.prose
    assert "human-authored" not in exp.prose


async def test_a_file_with_no_evidence_says_so_plainly(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        exp = await explain_file(conn, "src/untouched.py", project_id=pid)
    assert exp.factors == []
    assert "no fusion evidence" in exp.prose
    assert "not touched by a recorded agent session" in exp.prose


async def test_consequences_are_labelled_correlation(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        decision = await repo.insert_decision(conn, Decision(
            summary="switched to async ledger", source="adr", source_ref="ADR-1.md",
            project_id=pid, file_path="src/a.py",
        ))
        await repo.insert_consequence(conn, Consequence(
            decision_id=decision.id, project_id=None, metric="complexity", file_path="src/a.py",
            window_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            window_end=datetime(2026, 2, 1, tzinfo=timezone.utc),
            baseline_value=30.0, observed_value=42.0, delta=12.0,
            causal_claim="correlation", confidence=0.5,
        ))
        exp = await explain_file(conn, "src/a.py", project_id=pid)
    assert "switched to async ledger" in exp.prose
    assert "correlation, not causation" in exp.prose
    assert "complexity +12" in exp.prose


async def test_a_sub_noise_consequence_reads_as_no_change(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        decision = await repo.insert_decision(conn, Decision(
            summary="tidied imports", source="commit", source_ref="abc",
            project_id=pid, file_path="src/a.py",
        ))
        await repo.insert_consequence(conn, Consequence(
            decision_id=decision.id, metric="complexity", file_path="src/a.py",
            window_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            window_end=datetime(2026, 2, 1, tzinfo=timezone.utc),
            baseline_value=30.0, observed_value=30.2, delta=0.2,
            causal_claim="none", confidence=0.0,
        ))
        exp = await explain_file(conn, "src/a.py", project_id=pid)
    assert "no discernible change" in exp.prose


async def test_evidence_without_a_computed_share_is_stated_as_such(db: Path):
    """Honest partial state: an agent wrote the file but no line-share was
    computed. The prose says exactly that, not a made-up percentage."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await _ai_touch(conn, pid, "src/a.py")
        exp = await explain_file(conn, "src/a.py", project_id=pid)
    assert "a line-share has not been computed" in exp.prose
    assert "%" not in exp.prose.split("Traced")[0], "no fabricated percentage"


async def test_explanation_is_project_scoped(db: Path):
    """Another project's authorship of a same-named file must not appear here."""
    async with get_connection(db) as conn:
        a = await _project(conn)
        b = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('b', '/b')")).lastrowid)
        await conn.commit()
        sb = await repo.upsert_session(conn, Session(source="claude_code", external_id="sb", project_id=b))
        await repo.insert_session_file_touch(conn, SessionFileTouch(
            session_id=sb.id, project_id=b, file_path="README.md", touch_kind="write", confidence=0.9,
        ))
        exp_a = await explain_file(conn, "README.md", project_id=a)
    assert exp_a.factors == [], "project A has no evidence for this file"
