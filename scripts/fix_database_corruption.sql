-- CITY DATABASE CORRUPTION FIX SCRIPT
-- Generated: 2025-10-28
-- Database: /root/engagic/data/engagic.db

-- =============================================================================
-- PHASE 1: IMMEDIATE FIXES (Low Risk)
-- Simple slug formatting corrections - no data deletion needed
-- =============================================================================

-- Beaumont, TX: formatting difference
UPDATE cities SET slug = 'beaumonttexas' WHERE banana = 'beaumontTX';

-- San Antonio, TX: remove numeric suffix
UPDATE cities SET slug = 'sanantonio' WHERE banana = 'sanantonioTX';

-- Westminster, MD: add city prefix
UPDATE cities SET slug = 'cityofwestminster' WHERE banana = 'westminsterMD';

-- El Paso, TX: formatting difference
UPDATE cities SET slug = 'elpasotexas' WHERE banana = 'elpasoTX';

-- =============================================================================
-- PHASE 2: VENDOR MIGRATION (Medium Risk)
-- Change vendor from 'legistar' to 'granicus' (Granicus acquired Legistar)
-- No slug changes needed - slugs are already correct
-- =============================================================================

-- Bulk fix: All legistar cities should be granicus
UPDATE cities SET vendor = 'granicus' WHERE vendor = 'legistar';

-- =============================================================================
-- PHASE 3: NOVUSAGENDA SLUG FIXES (Low Risk)
-- Fix state code confusion and similar city name issues
-- =============================================================================

-- Arlington, MA: fix state code confusion (was 'va')
UPDATE cities SET slug = 'arlington' WHERE banana = 'arlingtonMA';

-- Arlington, WA: remove incorrect numeric suffix
UPDATE cities SET slug = 'arlington' WHERE banana = 'arlingtonWA';

-- Bloomfield, NJ: fix incomplete city name
UPDATE cities SET slug = 'bloomfieldhills' WHERE banana = 'bloomfieldNJ';

-- Carmichael, CA: fix state code confusion (was 'in')
UPDATE cities SET slug = 'carmel' WHERE banana = 'carmichaelCA';

-- Union City, NJ: fix state code confusion (was 'ca5')
UPDATE cities SET slug = 'unioncity' WHERE banana = 'unioncityNJ';

-- =============================================================================
-- PHASES 1-3 COMPLETE
-- Safe to run these changes immediately
-- Total affected: 4 + 16 + 5 = 25 cities
-- =============================================================================

-- =============================================================================
-- PHASE 4: PRIMEGOV WRONG CITY FIXES (HIGH RISK)
-- DO NOT RUN WITHOUT MANUAL VERIFICATION
-- These cities have meetings from DIFFERENT cities entirely
-- 
-- Required steps for each city:
-- 1. Manually verify correct slug for the INTENDED city
-- 2. Delete incorrect meetings
-- 3. Update slug to correct value
-- 4. Re-sync meetings using daemon
-- =============================================================================

-- WARNING: The following commands are COMMENTED OUT for safety
-- Uncomment and update with VERIFIED correct slugs before running

-- Glen Allen, VA → Currently has Glendale, CA meetings
-- DELETE FROM meetings WHERE banana = 'glenallenVA';
-- UPDATE cities SET slug = 'VERIFY_CORRECT_SLUG_HERE' WHERE banana = 'glenallenVA';

-- Lakeland, FL → Currently has Lake Forest, IL meetings
-- DELETE FROM meetings WHERE banana = 'lakelandFL';
-- UPDATE cities SET slug = 'VERIFY_CORRECT_SLUG_HERE' WHERE banana = 'lakelandFL';

-- Lancaster, SC → Currently has Lancaster, CA meetings
-- DELETE FROM meetings WHERE banana = 'lancasterSC';
-- UPDATE cities SET slug = 'VERIFY_CORRECT_SLUG_HERE' WHERE banana = 'lancasterSC';

-- Palm Harbor, FL → Currently has Palm Bay, FL meetings
-- DELETE FROM meetings WHERE banana = 'palmharborFL';
-- UPDATE cities SET slug = 'VERIFY_CORRECT_SLUG_HERE' WHERE banana = 'palmharborFL';

-- Springfield, VA → Currently has Springfield, OH meetings
-- DELETE FROM meetings WHERE banana = 'springfieldVA';
-- UPDATE cities SET slug = 'VERIFY_CORRECT_SLUG_HERE' WHERE banana = 'springfieldVA';

-- Temple Hills, MD → Currently has Temple, TX meetings
-- DELETE FROM meetings WHERE banana = 'templehillsMD';
-- UPDATE cities SET slug = 'VERIFY_CORRECT_SLUG_HERE' WHERE banana = 'templehillsMD';

-- Santa Maria, CA → Currently has Santa Ana, CA meetings
-- DELETE FROM meetings WHERE banana = 'santamariaCA';
-- UPDATE cities SET slug = 'VERIFY_CORRECT_SLUG_HERE' WHERE banana = 'santamariaCA';

-- =============================================================================
-- VERIFICATION QUERIES
-- Run these after applying fixes to verify success
-- =============================================================================

-- Count cities by corruption status (should show 0 wrong_slug, 0 wrong_vendor after fixes)
-- (Requires running analysis script again)

-- Check Phase 4 cities have no meetings (after deletion)
SELECT banana, name, state, slug, 
       (SELECT COUNT(*) FROM meetings m WHERE m.banana = c.banana) as meeting_count
FROM cities c
WHERE banana IN ('glenallenVA', 'lakelandFL', 'lancasterSC', 'palmharborFL', 
                 'springfieldVA', 'templehillsMD', 'santamariaCA');

-- Verify vendor migration worked
SELECT COUNT(*) as legistar_count FROM cities WHERE vendor = 'legistar';
-- Should return 0

SELECT COUNT(*) as granicus_count FROM cities WHERE vendor = 'granicus';
-- Should return previous legistar count + previous granicus count

-- =============================================================================
-- END OF SCRIPT
-- =============================================================================
