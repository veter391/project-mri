-- 0006_decisions_project_scope.sql
--
-- A decision belongs to a project. Without that link the consequence loop
-- counted decisions from every project in the database as confounders for one
-- project's metric — an audit reproduced project B's commit subjects appearing
-- in project A's consequence and dragging its confidence down. In a multi-repo
-- deployment that is both a wrong number and a cross-tenant leak of what other
-- projects decided.
--
-- Nullable, because a manually recorded decision may not belong to a scanned
-- project, and a decision with no project is simply not a confounder for any
-- project's metric — which is the conservative, correct default.

ALTER TABLE decisions ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_decisions_project ON decisions(project_id);
