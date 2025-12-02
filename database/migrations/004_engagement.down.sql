-- Rollback: 004_engagement
-- Removes engagement mechanics tables

DROP MATERIALIZED VIEW IF EXISTS userland.trending_matters;
DROP INDEX IF EXISTS userland.activity_log_session_idx;
DROP TABLE IF EXISTS userland.activity_log;
DROP TABLE IF EXISTS userland.watches;
