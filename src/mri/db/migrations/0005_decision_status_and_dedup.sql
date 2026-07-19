-- 0005_decision_status_and_dedup.sql
--
-- Two gaps the block-7 audits found in how decisions are recorded.
--
-- First, an ADR carries a lifecycle — Accepted, Superseded — that the parser
-- read but had nowhere to store, so the "a status change is picked up" claim
-- was not actually true. A nullable `status` column makes it true; it is
-- nullable because a decision mined from a commit has no such lifecycle, and an
-- empty string would be a claim that it does.
--
-- Second, nothing stopped the same decision being recorded twice. Two ingests
-- racing, or a re-ingest, could double-insert a commit or an ADR, and a
-- double-counted decision is exactly the kind of quiet inflation the fusion
-- tables exist to prevent. A unique index over the natural key makes the
-- duplicate impossible at the database rather than hoping the ingest checks
-- first — the same approach sessions and session_events already take.

ALTER TABLE decisions ADD COLUMN status TEXT;

-- The natural key of a mined decision is (source, source_ref): an ADR's
-- filename, a commit's sha. Partial, because manually recorded decisions have
-- no source_ref and several of them sharing an empty one is legitimate — the
-- constraint applies only where a source_ref actually identifies something.
CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_natural_key
    ON decisions(source, source_ref)
    WHERE source_ref != '';
