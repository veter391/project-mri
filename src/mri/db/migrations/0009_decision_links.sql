-- 0009_decision_links.sql
--
-- An ADR and a commit can describe the same decision. Linking them lets a
-- reader see one decision recorded in two places, rather than two unrelated
-- rows, and stops the per-file view double-listing what is really one choice.
--
-- The link is stored, not merged: merging two decisions into one would throw
-- away their distinct rationale, confidence and source_ref. Each keeps its own
-- row; this table records that they are the same decision and how that was
-- established.
--
-- Only *explicit* cross-references make a link — a commit message naming an ADR,
-- or an ADR body naming a commit sha. Fuzzy text similarity is deliberately not
-- used: it would guess at sameness, and a wrong merge of two real decisions is
-- exactly the kind of fabricated relationship this product refuses.

CREATE TABLE IF NOT EXISTS decision_links (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id         INTEGER NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    related_decision_id INTEGER NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    project_id          INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    -- How the link was established: 'commit_names_adr' or 'adr_names_commit'.
    relation            TEXT    NOT NULL,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    -- A decision cannot be linked to itself, and a pair is recorded once.
    CHECK (decision_id != related_decision_id),
    UNIQUE (decision_id, related_decision_id)
);

CREATE INDEX IF NOT EXISTS idx_decision_links_decision ON decision_links(decision_id);
CREATE INDEX IF NOT EXISTS idx_decision_links_related  ON decision_links(related_decision_id);
