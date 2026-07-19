-- 0007_fusion_project_scope.sql
--
-- Finishes the project scoping that 0006 started. 0006 gave `decisions` a
-- project_id and scoped one read path (`_confounders_in_window`); two
-- whole-subsystem audits then reproduced that the rest of the fusion tables
-- were still project-blind:
--
--   * a session is never linked to a project, so `session_file_touches` and
--     `authorship_shares` cannot be scoped either. Two repos scanned into one
--     install, both touching a same-named file ("README.md", "src/index.ts"),
--     blend their authorship evidence — one project's AI touches surface in the
--     other's risk report. Reproduced.
--   * the decisions natural-key `(source, source_ref)` is not project-scoped,
--     so two repos using the ordinary ADR-0001-*.md convention collide: the
--     second silently drops a commit or crashes ADR ingest. Reproduced.
--
-- The product supports multiple projects in one database (projects table, 0001)
-- and is heading for a self-hosted surface, so this is a cross-tenant leak to
-- close before anything is wired on top — which is also where the ingest gains
-- the project link the plan's session-to-project step needs.

-- ---------------------------------------------------------------------------
-- Link the session subsystem to a project
-- ---------------------------------------------------------------------------
--
-- project_id is denormalised onto touches and shares (not just sessions) so the
-- hot file-path lookups scope with one indexed predicate instead of a join on
-- every query. Nullable: a session ingested without a project association is
-- attributable to no project, and is then evidence for none — the conservative
-- default, matching how 0006 treats a decision with no project.

ALTER TABLE sessions             ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE session_file_touches ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE authorship_shares    ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);

-- The file-keyed reads now filter (project_id, file_path); the sort column
-- stays in the index so the covering-index win from 0004 survives the new
-- predicate.
DROP INDEX IF EXISTS idx_touches_file;
CREATE INDEX IF NOT EXISTS idx_touches_file
    ON session_file_touches(project_id, file_path, occurred_at DESC);

DROP INDEX IF EXISTS idx_authorship_file;
CREATE INDEX IF NOT EXISTS idx_authorship_file
    ON authorship_shares(project_id, file_path, computed_at DESC);

-- ---------------------------------------------------------------------------
-- Scope the decisions natural key to the project
-- ---------------------------------------------------------------------------
--
-- COALESCE(project_id, -1) so decisions with no project still dedupe among
-- themselves, while the same (source, source_ref) is allowed once per project.
-- Verified: cross-project same filename allowed, in-project duplicate refused,
-- NULL-project duplicate refused.

DROP INDEX IF EXISTS idx_decisions_natural_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_natural_key
    ON decisions(source, source_ref, COALESCE(project_id, -1))
    WHERE source_ref != '';
