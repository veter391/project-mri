-- 0008_decision_files.sql
--
-- Links a decision to the files it concerns. A commit decision changes many
-- files, and `decisions.file_path` is a single column, so a commit mined into
-- one decision could name only one file (or, as it stands, none). The per-file
-- explanation then never surfaces the decisions or consequences behind a file
-- whose decision came from a commit — the exact "why" the product is meant to
-- show.
--
-- A join table rather than duplicating the decision per file: one decision, its
-- rationale and confidence stored once, linked to each file it touched.

CREATE TABLE IF NOT EXISTS decision_files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    -- Denormalised from the decision so a file lookup scopes with one indexed
    -- predicate, the same choice touches/authorship made in 0007.
    project_id  INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    file_path   TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (decision_id, file_path)
);

CREATE INDEX IF NOT EXISTS idx_decision_files_lookup
    ON decision_files(project_id, file_path);
CREATE INDEX IF NOT EXISTS idx_decision_files_decision
    ON decision_files(decision_id);
