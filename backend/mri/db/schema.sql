-- ============================================================
-- Project MRI — SQLite cache schema
-- All persistent state lives here. Reports are JSON columns.
-- ============================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ----------------------------------------------------------------
-- Projects — every scanned repo is one row here
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path            TEXT    NOT NULL UNIQUE,
    name            TEXT    NOT NULL,
    default_branch  TEXT    NOT NULL DEFAULT 'main',
    first_scanned   TEXT    NOT NULL DEFAULT (datetime('now')),
    last_scanned    TEXT    NOT NULL DEFAULT (datetime('now')),
    last_commit     TEXT,
    file_count      INTEGER NOT NULL DEFAULT 0,
    loc_total       INTEGER NOT NULL DEFAULT 0,
    notes           TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);

-- ----------------------------------------------------------------
-- Scans — every scan run on a project
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scan_uuid       TEXT    NOT NULL UNIQUE,
    status          TEXT    NOT NULL DEFAULT 'pending',  -- pending|running|completed|failed
    started_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT,
    error_message   TEXT    NOT NULL DEFAULT '',
    -- final report data (JSON blob — full Report model)
    report_json     TEXT    NOT NULL DEFAULT '{}',
    -- brief summary for the index page (JSON blob)
    summary_json    TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_scans_project ON scans(project_id);
CREATE INDEX IF NOT EXISTS idx_scans_status  ON scans(status);
CREATE INDEX IF NOT EXISTS idx_scans_started ON scans(started_at DESC);

-- ----------------------------------------------------------------
-- Analyzers — per-scan per-analyzer results (kept separately so we
-- can re-score without re-scanning, and surface partial progress)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analyzer_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id         INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    analyzer_name   TEXT    NOT NULL,         -- 'git_history', 'architecture', ...
    status          TEXT    NOT NULL DEFAULT 'pending',
    started_at      TEXT,
    finished_at     TEXT,
    findings_json   TEXT    NOT NULL DEFAULT '{}',  -- AnalyzerFinding[]
    signals_json    TEXT    NOT NULL DEFAULT '{}',  -- raw signals
    score_value     REAL,                          -- 0..100, NULL if not applicable
    score_label     TEXT,                          -- 'architecture_health' etc.
    error_message   TEXT    NOT NULL DEFAULT '',
    UNIQUE(scan_id, analyzer_name)
);

CREATE INDEX IF NOT EXISTS idx_runs_scan ON analyzer_runs(scan_id);
CREATE INDEX IF NOT EXISTS idx_runs_name ON analyzer_runs(analyzer_name);

-- ----------------------------------------------------------------
-- Findings — flattened per-finding rows for query/filter/export
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS findings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES analyzer_runs(id) ON DELETE CASCADE,
    analyzer_name   TEXT    NOT NULL,
    severity        TEXT    NOT NULL,    -- 'info'|'low'|'medium'|'high'|'critical'
    category        TEXT    NOT NULL,    -- 'hotspot'|'cycle'|'god_module'|...
    title           TEXT    NOT NULL,
    description     TEXT    NOT NULL DEFAULT '',
    target_path     TEXT    NOT NULL DEFAULT '',
    target_symbol   TEXT    NOT NULL DEFAULT '',
    score           REAL,                -- 0..100, contribution to analyzer score
    data_json       TEXT    NOT NULL DEFAULT '{}'  -- extra structured data
);

CREATE INDEX IF NOT EXISTS idx_findings_run      ON findings(run_id);
CREATE INDEX IF NOT EXISTS idx_findings_analyzer ON findings(analyzer_name);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_findings_category ON findings(category);

-- ----------------------------------------------------------------
-- Events — for replaying a scan (audit trail)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scan_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id         INTEGER NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    at              TEXT    NOT NULL DEFAULT (datetime('now')),
    kind            TEXT    NOT NULL,    -- 'progress'|'log'|'error'
    message         TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_scan ON scan_events(scan_id, at);

-- ----------------------------------------------------------------
-- Users — exactly one admin per self-hosted installation
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL UNIQUE,
    password_hash   TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    last_login_at   TEXT
);

-- ----------------------------------------------------------------
-- App settings — JWT secret, integration tokens, etc.
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_settings (
    key             TEXT    PRIMARY KEY,
    value           TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------
-- Cloned repos cache — when user scans a remote URL
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cloned_repos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT    NOT NULL,
    local_path      TEXT    NOT NULL UNIQUE,
    default_branch  TEXT    NOT NULL DEFAULT 'main',
    cloned_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    last_scanned_at TEXT,
    scan_count      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_cloned_repos_url ON cloned_repos(url);

-- ----------------------------------------------------------------
-- Webhook deliveries — for tracking notification history
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT    NOT NULL,
    event           TEXT    NOT NULL,    -- 'scan_complete' | 'scan_failed' | ...
    payload_json    TEXT    NOT NULL,
    status_code     INTEGER,             -- NULL = not yet sent
    response_body   TEXT,
    attempted_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    delivered_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_event ON webhook_deliveries(event);
