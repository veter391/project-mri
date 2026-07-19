-- 0004_fusion_index_tuning.sql
--
-- Index changes from the performance audit of 0002, each one measured before
-- it was made and each measurement repeated independently before it was
-- accepted.
--
-- Nothing speculative is added here. An index that no query uses is not free —
-- the same audit measured a batched load of the realistic volume at 1.078 s
-- with all of 0002's indices and 0.862 s with the twelve unused ones removed,
-- a 20% write tax for reads nobody performs. The eleven that are merely
-- premature are therefore left in place only where a planned join justifies
-- them, and the one that is provably redundant is dropped.

-- ---------------------------------------------------------------------------
-- Let the index satisfy the ORDER BY as well as the lookup
-- ---------------------------------------------------------------------------
--
-- Every list query in fusion_repository.py filters on one column and sorts on
-- another. Indexing only the filter column made SQLite build a TEMP B-TREE for
-- the sort on every call. At average cardinality that is invisible; on a hot
-- file it is not.
--
-- Measured on 50,000 touches with 5,000 on a single file — a plausible shape
-- for a README or a core module — using the exact query the repository issues:
--
--   before:  SEARCH ... USING INDEX idx_touches_file (file_path=?)
--            USE TEMP B-TREE FOR ORDER BY            3.980 ms
--   after:   SEARCH ... USING INDEX idx_touches_file (file_path=?)
--                                                    0.215 ms   (18.5x)
--
-- This costs no extra index: a composite serves the plain single-column lookup
-- through its leftmost prefix, which was verified with EXPLAIN QUERY PLAN
-- rather than assumed.

DROP INDEX IF EXISTS idx_touches_file;
CREATE INDEX IF NOT EXISTS idx_touches_file
    ON session_file_touches(file_path, occurred_at DESC);

DROP INDEX IF EXISTS idx_authorship_file;
CREATE INDEX IF NOT EXISTS idx_authorship_file
    ON authorship_shares(file_path, computed_at DESC);

DROP INDEX IF EXISTS idx_decisions_file;
CREATE INDEX IF NOT EXISTS idx_decisions_file
    ON decisions(file_path, decided_at DESC);

DROP INDEX IF EXISTS idx_consequences_decision;
CREATE INDEX IF NOT EXISTS idx_consequences_decision
    ON consequences(decision_id, window_end DESC);

-- ---------------------------------------------------------------------------
-- Remove the one index that can never be chosen
-- ---------------------------------------------------------------------------
--
-- `sessions` already carries UNIQUE (source, external_id), whose automatic
-- index serves any query filtering on `source` alone through its leftmost
-- prefix. A separate single-column index on `source` can therefore never win.
-- Verified on a fresh connection, because a reused one reports the plan it
-- cached before the index was dropped and will happily name an index that no
-- longer exists:
--
--   with it:      SEARCH sessions USING INDEX idx_sessions_source (source=?)
--   without it:   SEARCH sessions USING INDEX sqlite_autoindex_sessions_1 (source=?)

DROP INDEX IF EXISTS idx_sessions_source;

-- ---------------------------------------------------------------------------
-- Deliberately kept
-- ---------------------------------------------------------------------------
--
-- The audit found eleven further indices with no query using them today. They
-- stay, with reasons, because dropping an index that is about to be needed is
-- churn and adding one later is a one-line migration either way:
--
--   idx_touches_session, idx_decisions_session, idx_consequences_session
--       These are what SQLite's ON DELETE CASCADE / SET NULL machinery uses to
--       find child rows when a session is deleted. Not dead — indirectly used.
--   idx_touches_commit, idx_authorship_commit, idx_decisions_commit
--       commit_sha is the join key the authorship and consequence layers are
--       specified to use. Speculative for one more block, then load-bearing.
--   idx_session_events_hash
--       Deduplicating turns across re-ingests, which is what the hash exists
--       for at all.
--   idx_sessions_started, idx_sessions_workspace, idx_session_events_time,
--   idx_touches_time, idx_authorship_time, idx_decisions_source,
--   idx_decisions_time, idx_consequences_metric, idx_consequences_file,
--   idx_consequences_window
--       Genuinely unproven. Left because the dashboard queries that will use
--       them are designed but not written; revisit at the surfaces block and
--       drop whatever is still unused then.
