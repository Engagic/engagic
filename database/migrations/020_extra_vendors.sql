-- Migration 020: Add extra_vendors to jurisdictions
-- Supports the rare case where one jurisdiction spans multiple vendors
-- (e.g. Maricopa County: Board of Supervisors on OnBase, commissions on CivicPlus).
--
-- Shape: [{"vendor": "civicplus", "slug": "maricopa-commissions"}, ...]
-- NULL for every existing row. Primary vendor/slug columns remain authoritative;
-- extras are additive sync passes against the same banana.

ALTER TABLE jurisdictions ADD COLUMN extra_vendors JSONB;
