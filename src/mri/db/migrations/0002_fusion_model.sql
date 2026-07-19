-- 0002_fusion_model.sql
--
-- The data model the fusion layers are built on: agent session provenance,
-- authorship-decomposed risk, decision provenance, and the consequence loop.
--
-- Two rules are enforced by the schema rather than left to callers, because
-- this product's whole claim is that its numbers are honest and a constraint is
-- the only kind of promise that cannot be forgotten:
--
--   * an attribution's shares must sum to 100, and "unattributed" is one of
--     them — so a share that is not known has somewhere to go and cannot be
--     silently folded into another;
--   * a consequence must declare what kind of claim it is making, and the
--     default is `correlation`, never `causation`.
--
-- Session content is nullable throughout. Reading agent logs is local, opt-in
-- and redactable, so metadata-only ingest has to be a first-class state rather
-- than an empty string pretending to be content.

-- ---------------------------------------------------------------------------
-- Session provenance
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Where the session came from: claude_code, cursor, aider, git_notes, ...
    source          TEXT    NOT NULL,
    -- The tool's own identifier, so re-ingesting the same log is idempotent.
    external_id     TEXT    NOT NULL,
    workspace_path  TEXT    NOT NULL DEFAULT '',
    started_at      TEXT,
    ended_at        TEXT,
    -- Whether prompt/response content was stored, or only metadata. Recorded
    -- per session because the setting can change between ingests.
    content_stored  INTEGER NOT NULL DEFAULT 0 CHECK (content_stored IN (0, 1)),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_source    ON sessions(source);
CREATE INDEX IF NOT EXISTS idx_sessions_started   ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_workspace ON sessions(workspace_path);

CREATE TABLE IF NOT EXISTS session_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    -- Position within the session, so ordering survives equal timestamps.
    seq             INTEGER NOT NULL,
    role            TEXT    NOT NULL CHECK (role IN ('user', 'assistant', 'tool', 'system')),
    kind            TEXT    NOT NULL DEFAULT 'message',
    -- NULL when running metadata-only. An empty string would be a claim that
    -- the turn had no content, which is a different statement.
    content         TEXT,
    -- Always present: lets turns be correlated and deduplicated without
    -- retaining what was said.
    content_hash    TEXT    NOT NULL DEFAULT '',
    occurred_at     TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_session_events_session  ON session_events(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_session_events_time     ON session_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_session_events_hash     ON session_events(content_hash);

CREATE TABLE IF NOT EXISTS session_file_touches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    event_id        INTEGER REFERENCES session_events(id) ON DELETE SET NULL,
    file_path       TEXT    NOT NULL,
    -- NULL until the touch is linked to a commit; a session edits files long
    -- before they are committed, and may never commit them at all.
    commit_sha      TEXT,
    touch_kind      TEXT    NOT NULL CHECK (touch_kind IN ('read', 'write', 'create', 'delete')),
    -- How sure the link between session and file is. Correlating a log with a
    -- working tree is inference, and the schema refuses to let it look certain.
    confidence      REAL    NOT NULL DEFAULT 0.0 CHECK (confidence BETWEEN 0.0 AND 1.0),
    occurred_at     TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_touches_session ON session_file_touches(session_id);
CREATE INDEX IF NOT EXISTS idx_touches_file    ON session_file_touches(file_path);
CREATE INDEX IF NOT EXISTS idx_touches_commit  ON session_file_touches(commit_sha);
CREATE INDEX IF NOT EXISTS idx_touches_time    ON session_file_touches(occurred_at);

-- ---------------------------------------------------------------------------
-- Authorship-decomposed attribution
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS authorship_shares (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path           TEXT    NOT NULL,
    commit_sha          TEXT,
    -- Shares are percentages and must account for the whole file. A file whose
    -- provenance is entirely unknown is 100 unattributed, which is a real and
    -- reportable answer — unlike a guess.
    share_ai            REAL    NOT NULL DEFAULT 0.0   CHECK (share_ai           BETWEEN 0.0 AND 100.0),
    share_human         REAL    NOT NULL DEFAULT 0.0   CHECK (share_human        BETWEEN 0.0 AND 100.0),
    share_unattributed  REAL    NOT NULL DEFAULT 100.0 CHECK (share_unattributed BETWEEN 0.0 AND 100.0),
    -- How the split was derived, so a reader can judge it: session_overlap,
    -- git_trailer, blame_heuristic, declared, ...
    method              TEXT    NOT NULL DEFAULT 'unknown',
    confidence          REAL    NOT NULL DEFAULT 0.0 CHECK (confidence BETWEEN 0.0 AND 1.0),
    computed_at         TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    -- Table-level: the three shares must account for the whole file.
    CHECK (abs(share_ai + share_human + share_unattributed - 100.0) < 0.01)
);

CREATE INDEX IF NOT EXISTS idx_authorship_file   ON authorship_shares(file_path);
CREATE INDEX IF NOT EXISTS idx_authorship_commit ON authorship_shares(commit_sha);
CREATE INDEX IF NOT EXISTS idx_authorship_time   ON authorship_shares(computed_at);

-- ---------------------------------------------------------------------------
-- Decision provenance — the "why" behind a change
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    -- What was decided, and why. `rationale` is nullable: a decision mined from
    -- a commit may have a clear what and no recoverable why, and inventing one
    -- would be the exact failure this table exists to prevent.
    summary         TEXT    NOT NULL,
    rationale       TEXT,
    source          TEXT    NOT NULL CHECK (source IN ('adr', 'session', 'commit', 'issue', 'manual')),
    -- Where it came from: an ADR path, a session id, a commit sha.
    source_ref      TEXT    NOT NULL DEFAULT '',
    session_id      INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    file_path       TEXT,
    commit_sha      TEXT,
    decided_at      TEXT,
    confidence      REAL    NOT NULL DEFAULT 0.0 CHECK (confidence BETWEEN 0.0 AND 1.0),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_decisions_source  ON decisions(source, source_ref);
CREATE INDEX IF NOT EXISTS idx_decisions_file    ON decisions(file_path);
CREATE INDEX IF NOT EXISTS idx_decisions_commit  ON decisions(commit_sha);
CREATE INDEX IF NOT EXISTS idx_decisions_session ON decisions(session_id);
CREATE INDEX IF NOT EXISTS idx_decisions_time    ON decisions(decided_at DESC);

-- ---------------------------------------------------------------------------
-- Consequence loop — what measurably happened afterwards
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS consequences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id     INTEGER REFERENCES decisions(id) ON DELETE CASCADE,
    session_id      INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    -- What was measured, over what window, and by how much it moved.
    metric          TEXT    NOT NULL,
    file_path       TEXT,
    window_start    TEXT    NOT NULL,
    window_end      TEXT    NOT NULL,
    baseline_value  REAL,
    observed_value  REAL,
    delta           REAL,
    -- The honesty gate. A row that does not say what kind of claim it makes
    -- cannot exist, and the default is the weaker one. Nothing in this codebase
    -- may write 'causation' without a written justification.
    causal_claim    TEXT    NOT NULL DEFAULT 'correlation'
                    CHECK (causal_claim IN ('correlation', 'causation', 'none')),
    -- Alternative explanations, as JSON. An empty list is a claim that none
    -- were considered, so this defaults to an explicit unknown marker.
    confounders     TEXT    NOT NULL DEFAULT '[]',
    confidence      REAL    NOT NULL DEFAULT 0.0 CHECK (confidence BETWEEN 0.0 AND 1.0),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    -- A consequence with neither a decision nor a session is unattached and
    -- means nothing.
    CHECK (decision_id IS NOT NULL OR session_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_consequences_decision ON consequences(decision_id);
CREATE INDEX IF NOT EXISTS idx_consequences_session  ON consequences(session_id);
CREATE INDEX IF NOT EXISTS idx_consequences_metric   ON consequences(metric);
CREATE INDEX IF NOT EXISTS idx_consequences_file     ON consequences(file_path);
CREATE INDEX IF NOT EXISTS idx_consequences_window   ON consequences(window_start, window_end);
