# Data Cleanup & Corruption Fix - October 2025

## Problem Discovered

Systematic data corruption affecting multiple cities due to incorrect vendor/slug configurations:

**Example Issues:**
- Glendale, CA configured as Granicus, actually uses PrimeGov
- Glendora, CA had broken slug (va4.primegov.com doesn't exist)
- 8 Glendale meetings incorrectly stored under glendoraCA
- Multiple cross-city contamination issues (meetings from City A stored under City B)

**Root Cause:** Optimistic heuristics when deriving city configs led to mismatched vendor/slug combinations.

## What We Built

### 1. Meeting Validation Layer
**File:** `backend/services/meeting_validator.py`

Validates packet URLs match configured vendor/slug before storing meetings. Prevents future corruption by rejecting mismatched data.

**Integration:** Added to `conductor.py` sync process - validates every meeting before storage.

### 2. City Verification Tool
**File:** `scripts/verify_and_fix_all_cities.py`

Comprehensive verification of all 827 cities:
- Tests each vendor/slug combination with HTTP requests
- Special Granicus handling: view_id discovery (1-50) + cache lookup
- Tries slug variations for failures
- Detects cross-contamination (packet URLs from wrong vendor)
- Auto-generates SQL fix statements

**Features:**
- Uses cached Granicus view_ids when available
- Quick slug testing for variations (avoids expensive re-discovery)
- Outputs broken configs + auto-fix SQL

### 3. Health Check Script
**File:** `scripts/health_check.py`

Quick database health monitoring:
- City/meeting counts by vendor
- Cities with zero meetings
- AI processing stats
- Potential corruption detection
- Recent activity tracking

## Current Status (Oct 28, 2025)

### Immediate Fixes Applied
- ✅ Glendale, CA: vendor changed granicus→primegov, slug changed glendale→glendaleca
- ✅ Glendora, CA: slug changed va4→cityofglendora
- ✅ 8 meetings moved from glendoraCA to glendaleCA

### Completed (Oct 28)
✅ **Verification Complete**: All 827 cities verified
- Working configs: ~575 cities (69%)
- Auto-fixed: 73 cities (49 slugs + 24 vendor changes)
- Failed/need research: ~220 cities (27%)

✅ **Cross-Contamination Fixed**:
- 24 vendor mismatches corrected (granicus → legistar)
- ~40 false positives fixed in validators
- Beaumont CA exception added

✅ **Database State**:
- All SQL fixes applied
- 0 meetings (clean slate ready for re-sync)

### Next Steps
1. ✅ Slug corrections applied (49 cities)
2. ✅ Vendor fixes applied (24 cities)
3. ✅ Validator false positives fixed
4. 🔲 Re-sync cities to populate meetings with clean configs
5. 🔲 Manual research for ~200 failed Granicus cities (no view_id found)

## Files Modified

**New Files:**
- `backend/services/meeting_validator.py` - Validation layer (updated: docs.google.com, beaumontca.gov)
- `scripts/verify_and_fix_all_cities.py` - Verification tool (updated: fixed false positives)
- `scripts/health_check.py` - Database health monitoring
- `scripts/vendor_fixes_cross_contamination.sql` - 24 vendor changes (applied)
- `scripts/verification_summary_oct28.md` - Full verification findings

**Modified Files:**
- `backend/services/conductor.py` - Added validation before meeting storage
- `backend/services/meeting_validator.py` - Fixed false positive patterns
- `scripts/verify_and_fix_all_cities.py` - Fixed legistar/granicus detection

**Database:**
- Backup: `data/engagic.db.backup-20251028-015213`
- Fixed: 73 city configs (49 slugs + 24 vendors), moved 8 meetings, deleted all meetings

## Usage

### Run Verification
```bash
python3 scripts/verify_and_fix_all_cities.py
```
Outputs: `scripts/auto_generated_fixes.sql`

### Check Health
```bash
python3 scripts/health_check.py
```

### Apply Fixes
```bash
sqlite3 data/engagic.db < scripts/auto_generated_fixes.sql
```

## Statistics (Before Fix)

- **Total Cities:** 827
- **Total Meetings:** 3,377
- **Cities with 0 meetings:** 524 (63%)
- **Corrupted configs identified:** TBD (verification in progress)
- **Cross-contamination issues:** ~32 detected

## Prevention

Validation layer now prevents future corruption:
- Pre-flight check: packet_url domain must match vendor/slug
- Rejects corrupted meetings instead of storing
- Logs detailed error for investigation

## Notes

- Database corruption was caught early (only 3,377 meetings affected)
- No users impacted (development/early production)
- Fresh sync after fixes will rebuild all meeting data correctly
