-- Rollback: 007_deliberation

DROP TABLE IF EXISTS deliberation_results;
DROP TABLE IF EXISTS deliberation_votes;
DROP TABLE IF EXISTS userland.deliberation_trusted_users;
DROP TABLE IF EXISTS deliberation_comments;
DROP TABLE IF EXISTS deliberation_participants;
DROP TABLE IF EXISTS deliberations;
