"""Cross-source decision linking (block 7.3).

An ADR and a commit can record the same decision. They are linked, not merged,
so each keeps its own rationale and confidence — and only an EXPLICIT
cross-reference makes the link. Fuzzy similarity is deliberately absent: a wrong
merge of two real decisions is the failure this refuses.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from mri.db import fusion_repository as repo
from mri.db.migrator import migrate
from mri.db.repository import get_connection
from mri.fusion import link_related_decisions
from mri.models.fusion import Decision


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "dd.db"
    migrate(path)
    return path


async def _project(conn) -> int:
    pid = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('p', '/p')")).lastrowid)
    await conn.commit()
    return pid


async def test_a_commit_naming_an_adr_is_linked_to_it(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        adr = await repo.insert_decision(conn, Decision(
            summary="ADR-005 — schema migrations", source="adr",
            source_ref="ADR-005-schema-migrations.md", project_id=pid,
        ))
        commit = await repo.insert_decision(conn, Decision(
            summary="feat: migrations", rationale="Implements ADR-005.",
            source="commit", source_ref="deadbeef", commit_sha="deadbeef99", project_id=pid,
        ))
        n = await link_related_decisions(conn, project_id=pid)
        related = await repo.related_decisions(conn, commit.id, project_id=pid)
    assert n == 1
    assert [d.id for d in related] == [adr.id]


async def test_an_adr_naming_a_commit_sha_is_linked_to_it(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        commit = await repo.insert_decision(conn, Decision(
            summary="feat: X", source="commit", source_ref="cafebabe0011",
            commit_sha="cafebabe0011223344", project_id=pid,
        ))
        adr = await repo.insert_decision(conn, Decision(
            summary="ADR-006 — X", rationale="See commit cafebabe0011 for the work.",
            source="adr", source_ref="ADR-006-x.md", project_id=pid,
        ))
        await link_related_decisions(conn, project_id=pid)
        related = await repo.related_decisions(conn, adr.id, project_id=pid)
    assert [d.id for d in related] == [commit.id], "the ADR links to the commit it cites by sha"


async def test_the_link_is_bidirectional(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        adr = await repo.insert_decision(conn, Decision(
            summary="ADR-005 — x", source="adr", source_ref="ADR-005-x.md", project_id=pid))
        commit = await repo.insert_decision(conn, Decision(
            summary="feat: x", rationale="per ADR-005", source="commit",
            source_ref="abc", commit_sha="abc123", project_id=pid))
        await link_related_decisions(conn, project_id=pid)
        from_commit = await repo.related_decisions(conn, commit.id, project_id=pid)
        from_adr = await repo.related_decisions(conn, adr.id, project_id=pid)
    assert [d.id for d in from_commit] == [adr.id]
    assert [d.id for d in from_adr] == [commit.id], "either endpoint sees the other"


async def test_no_link_without_an_explicit_reference(db: Path):
    """Two decisions about the same topic but with no cross-reference are NOT
    linked — fuzzy sameness is forbidden."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await repo.insert_decision(conn, Decision(
            summary="ADR-005 — use SQLite", source="adr", source_ref="ADR-005-x.md", project_id=pid))
        commit = await repo.insert_decision(conn, Decision(
            summary="feat: use SQLite for storage", source="commit",
            source_ref="abc", commit_sha="abc123", project_id=pid))
        n = await link_related_decisions(conn, project_id=pid)
        related = await repo.related_decisions(conn, commit.id, project_id=pid)
    assert n == 0
    assert related == [], "same topic, no explicit reference, no link"


async def test_a_hex_word_that_is_not_a_real_commit_makes_no_link(db: Path):
    """An ADR body may contain a hex-looking word that is not a commit sha. It
    links only if it actually prefixes a stored commit."""
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await repo.insert_decision(conn, Decision(
            summary="ADR-007 — x", rationale="the value 0xdeadbeef aabbccdd is a constant, not a commit.",
            source="adr", source_ref="ADR-007-x.md", project_id=pid))
        await repo.insert_decision(conn, Decision(
            summary="feat: y", source="commit", source_ref="ffff000",
            commit_sha="ffff000111", project_id=pid))
        n = await link_related_decisions(conn, project_id=pid)
    assert n == 0, "a hex word matching no stored commit sha creates no link"


async def test_linking_is_idempotent(db: Path):
    async with get_connection(db) as conn:
        pid = await _project(conn)
        await repo.insert_decision(conn, Decision(
            summary="ADR-005 — x", source="adr", source_ref="ADR-005-x.md", project_id=pid))
        await repo.insert_decision(conn, Decision(
            summary="feat: x", rationale="per ADR-005", source="commit",
            source_ref="abc", commit_sha="abc123", project_id=pid))
        first = await link_related_decisions(conn, project_id=pid)
        again = await link_related_decisions(conn, project_id=pid)
    assert (first, again) == (1, 0), "a re-run adds only newly-derivable links"


async def test_links_are_project_scoped(db: Path):
    async with get_connection(db) as conn:
        a = await _project(conn)
        b = int((await conn.execute("INSERT INTO projects (name, path) VALUES ('b', '/b')")).lastrowid)
        await conn.commit()
        # project A: an ADR-005 and a commit citing it
        await repo.insert_decision(conn, Decision(
            summary="ADR-005 — a", source="adr", source_ref="ADR-005-a.md", project_id=a))
        c_a = await repo.insert_decision(conn, Decision(
            summary="feat: a", rationale="per ADR-005", source="commit",
            source_ref="a1", commit_sha="a1", project_id=a))
        # project B: a commit citing ADR-005, but B has no ADR-005
        c_b = await repo.insert_decision(conn, Decision(
            summary="feat: b", rationale="per ADR-005", source="commit",
            source_ref="b1", commit_sha="b1", project_id=b))
        await link_related_decisions(conn, project_id=a)
        await link_related_decisions(conn, project_id=b)
        assert len(await repo.related_decisions(conn, c_a.id, project_id=a)) == 1
        assert await repo.related_decisions(conn, c_b.id, project_id=b) == [], (
            "project B has no ADR-005, so its commit links to nothing"
        )
