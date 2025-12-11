-- Rollback session events table
DROP FUNCTION IF EXISTS cleanup_old_session_events();
DROP TABLE IF EXISTS session_events;
