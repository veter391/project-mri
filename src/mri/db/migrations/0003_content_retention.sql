-- 0003_content_retention.sql
--
-- Makes `sessions.content_stored` mean something.
--
-- 0002 introduced the flag as the record of whether a session's turn content
-- was retained or only its metadata. As shipped it was decorative: nothing read
-- it before writing `session_events.content`, so a session could claim it kept
-- no content while holding a pasted API key, and switching the flag off
-- retained everything it had already stored. A security audit demonstrated both
-- against a real database.
--
-- The fix belongs in the schema rather than in the ingest code, for the same
-- reason the honesty CHECKs in 0002 do: a caller can forget an invariant, and
-- there will be more than one caller — ingest, backfills, fixup scripts, and
-- whatever a contributor writes next. A trigger holds even for a connection
-- that never goes through this package.
--
-- What is deliberately NOT enforced: the inverse direction. A session with
-- `content_stored = 1` may still have events whose content is NULL, because
-- tool and system turns legitimately carry none. Requiring content there would
-- push callers into writing empty strings, which is precisely the "an empty
-- string is a claim that the turn had no content" failure 0002 set out to
-- avoid.

-- ---------------------------------------------------------------------------
-- Retention is refused at the door
-- ---------------------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS trg_session_events_respect_retention_insert
BEFORE INSERT ON session_events
FOR EACH ROW
WHEN NEW.content IS NOT NULL
     AND (SELECT content_stored FROM sessions WHERE id = NEW.session_id) = 0
BEGIN
    SELECT RAISE(ABORT, 'session_events.content was written for a session whose content_stored is 0 -- pass content = NULL when retention is off');
END;

CREATE TRIGGER IF NOT EXISTS trg_session_events_respect_retention_update
BEFORE UPDATE OF content ON session_events
FOR EACH ROW
WHEN NEW.content IS NOT NULL
     AND (SELECT content_stored FROM sessions WHERE id = NEW.session_id) = 0
BEGIN
    SELECT RAISE(ABORT, 'session_events.content was written for a session whose content_stored is 0 -- pass content = NULL when retention is off');
END;

-- ---------------------------------------------------------------------------
-- Turning retention off is a redaction, not a relabelling
-- ---------------------------------------------------------------------------
--
-- Setting the flag to 0 on a session that had retained content is a request to
-- stop retaining it. Leaving the rows in place while the flag says otherwise
-- would make the flag a lie in the one direction users would rely on it most —
-- "I turned that off". The content is dropped; the hashes stay, so turns can
-- still be correlated and deduplicated afterwards.

CREATE TRIGGER IF NOT EXISTS trg_sessions_redact_on_retention_off
AFTER UPDATE OF content_stored ON sessions
FOR EACH ROW
WHEN OLD.content_stored = 1 AND NEW.content_stored = 0
BEGIN
    UPDATE session_events SET content = NULL WHERE session_id = NEW.id;
END;

-- ---------------------------------------------------------------------------
-- Existing rows
-- ---------------------------------------------------------------------------
--
-- Any row already violating the rule predates the trigger and would otherwise
-- sit there permanently unenforceable. There is no ambiguity about intent: the
-- session said it was not storing content.

UPDATE session_events
SET content = NULL
WHERE content IS NOT NULL
  AND session_id IN (SELECT id FROM sessions WHERE content_stored = 0);
