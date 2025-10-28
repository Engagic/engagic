-- Vendor fixes for cross-contamination issues
-- Generated: 2025-10-28 (post full verification)
-- Changes: granicus → legistar for 24 cities with legistar packet URLs

BEGIN TRANSACTION;

UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='alamogordoNM'; -- Alamogordo, NM
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='boerneTX'; -- Boerne, TX
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='brokenarrowOK'; -- Broken Arrow, OK
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='burlingameCA'; -- Burlingame, CA
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='charlotteNC'; -- Charlotte, NC
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='columbiaMO'; -- Columbia, MO
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='culvercityCA'; -- Culver City, CA
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='deltonaFL'; -- Deltona, FL
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='dentonTX'; -- Denton, TX
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='fontanaCA'; -- Fontana, CA
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='fortlauderdaleFL'; -- Fort Lauderdale, FL
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='fresnoCA'; -- Fresno, CA
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='goletaCA'; -- Goleta, CA
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='haywardCA'; -- Hayward, CA
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='manitowocWI'; -- Manitowoc, WI
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='mantecaCA'; -- Manteca, CA
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='mckinneyTX'; -- McKinney, TX
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='napervilleIL'; -- Naperville, IL
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='ocalaFL'; -- Ocala, FL
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='redondobeachCA'; -- Redondo Beach, CA
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='santarosaCA'; -- Santa Rosa, CA
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='veniceFL'; -- Venice, FL
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='visaliaCA'; -- Visalia, CA
UPDATE cities SET vendor='legistar', updated_at=CURRENT_TIMESTAMP WHERE banana='wellingtonFL'; -- Wellington, FL

COMMIT;
