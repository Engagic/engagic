ALTER TABLE document_source DROP COLUMN IF EXISTS published_on, DROP COLUMN IF EXISTS title;
DROP INDEX IF EXISTS idx_jurisdictions_parent;
ALTER TABLE jurisdictions DROP COLUMN IF EXISTS parent_banana;
DELETE FROM jurisdictions
WHERE type = 'state' AND vendor = 'none'
  AND banana IN ('californiaCA', 'coloradoCO', 'iowaIA', 'minnesotaMN', 'northcarolinaNC',
                 'oregonOR', 'texasTX', 'virginiaVA', 'washingtonWA');
