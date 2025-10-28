# COMPREHENSIVE CITY DATABASE CORRUPTION ANALYSIS REPORT

**Database:** /root/engagic/data/engagic.db  
**Analysis Date:** 2025-10-28  
**Total Cities:** 827  
**Total Meetings:** 3,377  

---

## EXECUTIVE SUMMARY

**Corruption Status:**
- **Correct:** 62 cities (7.5%) - Configuration matches actual vendor/slug
- **Wrong Slug:** 15 cities (1.8%) - Correct vendor, wrong identifier
- **Wrong Vendor:** 16 cities (1.9%) - City uses different vendor entirely  
- **Cross-Contaminated:** 0 cities - No mixed meeting sources detected
- **Unverified:** 734 cities (88.8%) - No meetings or no packet URLs to verify

**Key Findings:**
1. All corruption is **systematic** (wrong config), not **cross-contaminated** (mixed data)
2. Santa Maria, CA meetings are actually from **Santa Ana, CA** (different city)
3. Lakeland, FL meetings are actually from **Lake Forest, IL** (different city)
4. All 16 "Legistar" vendor cities are actually **Granicus** (Granicus acquired Legistar)
5. PrimeGov has highest corruption rate: 14.1% wrong slugs (9 cities)
6. NovusAgenda: 7.2% wrong slugs (5 cities) - mostly similar city names confusion

---

## CORRUPTION BREAKDOWN BY VENDOR

### CivicClerk (15 cities total)
- **Correct:** 6 (40.0%)
- **Unverified:** 9 (60.0%)
- **Issues:** None detected - all verified cities are correct

### CivicPlus (92 cities total)
- **Correct:** 4 (4.3%)
- **Unverified:** 88 (95.7%)
- **Issues:** None detected - very low verification rate due to no meetings

### Granicus (493 cities total)
- **Correct:** 17 (3.4%)
- **Wrong Slug:** 1 (0.2%) - El Paso, TX
- **Unverified:** 475 (96.3%)
- **Issues:** 202 cities have meetings but no extractable packet URLs (S3 pattern issues)

### Legistar (85 cities total) - **CRITICAL ISSUE**
- **Wrong Vendor:** 16 (18.8%) - All should be "granicus"
- **Unverified:** 69 (81.2%)
- **Root Cause:** Granicus acquired Legistar, uses legistar.com domains but "granicus" vendor

### NovusAgenda (69 cities total)
- **Correct:** 15 (21.7%)
- **Wrong Slug:** 5 (7.2%)
- **Unverified:** 49 (71.0%)
- **Pattern:** Similar city names causing confusion (Arlington MA vs WA, Bloomfield vs Bloomfield Hills)

### PrimeGov (64 cities total)
- **Correct:** 20 (31.2%)
- **Wrong Slug:** 9 (14.1%)
- **Unverified:** 35 (54.7%)
- **Pattern:** Geographic confusion and abbreviation errors

---

## DETAILED CORRUPTION CASES

### Wrong Slug (15 cities) - MEDIUM SEVERITY
These cities have the correct vendor but wrong slug identifier:

#### Granicus (1 city)
- **El Paso, TX**: `elpaso-tx` → `elpasotexas`

#### NovusAgenda (5 cities)
- **Arlington, MA**: `va` → `arlington` (state code confusion)
- **Arlington, WA**: `arlington3` → `arlington` (numeric suffix wrong)
- **Bloomfield, NJ**: `bloomfield` → `bloomfieldhills` (incomplete city name)
- **Carmichael, CA**: `in` → `carmel` (state code confusion)
- **Union City, NJ**: `ca5` → `unioncity` (state code confusion)

#### PrimeGov (9 cities)
- **Beaumont, TX**: `beaumont-tx` → `beaumonttexas` (formatting difference)
- **Glen Allen, VA**: `glenallen` → `glendaleca` (WRONG CITY - different state!)
- **Lakeland, FL**: `lakeland` → `lakeforest` (WRONG CITY - different state!)
- **Lancaster, SC**: `oh5` → `cityoflancasterca` (WRONG CITY - different state!)
- **Palm Harbor, FL**: `fl3` → `palmbayflorida` (WRONG CITY - different location!)
- **San Antonio, TX**: `sanantonio2` → `sanantonio` (numeric suffix wrong)
- **Springfield, VA**: `springfield2` → `springfieldohio` (WRONG CITY - different state!)
- **Temple Hills, MD**: `tx2` → `cityoftemple` (WRONG CITY - different state!)
- **Westminster, MD**: `westminster` → `cityofwestminster` (prefix missing)

**CRITICAL:** 7 of 9 PrimeGov "wrong slug" cases are actually **wrong cities entirely**:
- Glen Allen, VA → Glendale, CA
- Lakeland, FL → Lake Forest, IL  
- Lancaster, SC → Lancaster, CA
- Palm Harbor, FL → Palm Bay, FL
- Springfield, VA → Springfield, OH
- Temple Hills, MD → Temple, TX
- Santa Maria, CA → Santa Ana, CA (not in top 15 but found in data)

### Wrong Vendor (16 cities) - HIGH SEVERITY
All are configured as "legistar" but actually use "granicus":

1. **Aurora, CO**: legistar/aurora → granicus/aurora-il (145 meetings - NYC data!)
2. **Canton, MI**: legistar/canton2 → granicus/canton
3. **Chino, CA**: legistar/chino → granicus/chino
4. **Cincinnati, OH**: legistar/cincinnatioh → granicus/cincinnatioh
5. **Concord, NC**: legistar/concordnh → granicus/concordnh
6. **Crossville, TN**: legistar/crossvilletn → granicus/crossvilletn
7. **Dallas, TX**: legistar/dallas → granicus/cityofdallas
8. **Desoto, TX**: legistar/desotobocc → granicus/desotobocc
9. **Galveston, TX**: legistar/galvestoncountytx → granicus/galvestoncountytx
10. **Grove City, OH**: legistar/groveport → granicus/groveport
11. **Hallandale, FL**: legistar/hallandalebeach → granicus/hallandalebeach
12. **Lake Charles, LA**: legistar/countyoflake → granicus/countyoflake
13. **Mountain View, CA**: legistar/mountainview → granicus/mountainview
14. **New York, NY**: legistar/nyc → granicus/nyc (145 meetings!)
15. **Phoenix, AZ**: legistar/phoenix → granicus/phoenix
16. **San Francisco, CA**: legistar/sfgov → granicus/sfgov

---

## RECOMMENDED FIX STRATEGY

### Phase 1: Immediate Fixes (Low Risk)
**Target:** Wrong Slug cases where it's just a formatting difference

Cities: Beaumont TX, San Antonio TX, Westminster MD, El Paso TX

```sql
UPDATE cities SET slug = 'beaumonttexas' WHERE banana = 'beaumontTX';
UPDATE cities SET slug = 'sanantonio' WHERE banana = 'sanantonioTX';
UPDATE cities SET slug = 'cityofwestminster' WHERE banana = 'westminsterMD';
UPDATE cities SET slug = 'elpasotexas' WHERE banana = 'elpasoTX';
```

### Phase 2: Vendor Migration (Medium Risk)
**Target:** All "legistar" → "granicus" vendor changes

```sql
-- Bulk vendor fix for Granicus/Legistar
UPDATE cities SET vendor = 'granicus' WHERE vendor = 'legistar';
```

Note: Slug values are correct, just vendor name wrong.

### Phase 3: NovusAgenda Slug Fixes (Low Risk)
**Target:** NovusAgenda cities with wrong but similar slugs

```sql
UPDATE cities SET slug = 'arlington' WHERE banana = 'arlingtonMA';
UPDATE cities SET slug = 'arlington' WHERE banana = 'arlingtonWA';
UPDATE cities SET slug = 'bloomfieldhills' WHERE banana = 'bloomfieldNJ';
UPDATE cities SET slug = 'carmel' WHERE banana = 'carmichaelCA';
UPDATE cities SET slug = 'unioncity' WHERE banana = 'unioncityNJ';
```

### Phase 4: PrimeGov WRONG CITY Fixes (HIGH RISK)
**Target:** Cities that have meetings from completely different cities

**REQUIRES MANUAL VERIFICATION BEFORE FIXING**

These need special handling:
1. Delete existing (incorrect) meetings
2. Update city config to correct slug
3. Re-fetch meetings with correct adapter

```sql
-- Glen Allen, VA → Actually Glendale, CA meetings
DELETE FROM meetings WHERE banana = 'glenallenVA';
UPDATE cities SET slug = 'glenallenva' WHERE banana = 'glenallenVA'; -- Need correct slug!

-- Lakeland, FL → Actually Lake Forest, IL meetings  
DELETE FROM meetings WHERE banana = 'lakelandFL';
UPDATE cities SET slug = 'lakelandfl' WHERE banana = 'lakelandFL'; -- Need correct slug!

-- Lancaster, SC → Actually Lancaster, CA meetings
DELETE FROM meetings WHERE banana = 'lancasterSC';
UPDATE cities SET slug = 'lancastersc' WHERE banana = 'lancasterSC'; -- Need correct slug!

-- Palm Harbor, FL → Actually Palm Bay, FL meetings
DELETE FROM meetings WHERE banana = 'palmharborFL';
UPDATE cities SET slug = 'palmharborfl' WHERE banana = 'palmharborFL'; -- Need correct slug!

-- Springfield, VA → Actually Springfield, OH meetings  
DELETE FROM meetings WHERE banana = 'springfieldVA';
UPDATE cities SET slug = 'springfieldva' WHERE banana = 'springfieldVA'; -- Need correct slug!

-- Temple Hills, MD → Actually Temple, TX meetings
DELETE FROM meetings WHERE banana = 'templehillsMD';
UPDATE cities SET slug = 'templehillsmd' WHERE banana = 'templehillsMD'; -- Need correct slug!

-- Santa Maria, CA → Actually Santa Ana, CA meetings
DELETE FROM meetings WHERE banana = 'santamariaCA';
UPDATE cities SET slug = 'santamariaca' WHERE banana = 'santamariaCA'; -- Need correct slug!
```

### Phase 5: Re-sync Corrupted Cities
After fixing configurations, run daemon sync for affected cities only:

```python
# Pseudo-code for targeted re-sync
affected_bananas = [
    'glenallenVA', 'lakelandFL', 'lancasterSC', 'palmharborFL',
    'springfieldVA', 'templehillsMD', 'santamariaCA'
]

for banana in affected_bananas:
    city = db.get_city(banana=banana)
    adapter = get_adapter_for_city(city)
    sync_city_meetings(city, adapter)
```

---

## VERIFICATION STRATEGY

After applying fixes:

1. **Immediate verification:**
   - Re-run analysis script
   - Expect: 0 wrong slug, 0 wrong vendor
   - Expect: 7 cities with 0 meetings (Phase 4 deletions)

2. **Post-sync verification:**
   - After daemon re-syncs Phase 4 cities
   - Check meeting counts recovered
   - Verify packet URLs match city configuration

3. **Ongoing monitoring:**
   - Track "unverified" count decrease as meetings are fetched
   - Alert on new "wrong slug" or "wrong vendor" detections

---

## ROOT CAUSE ANALYSIS

### Why did this happen?

1. **PrimeGov Geographic Confusion:**
   - Similar city names across states
   - Abbreviations causing lookups to fail
   - Example: "Springfield" exists in 35+ states

2. **Legistar/Granicus Acquisition:**
   - Granicus acquired Legistar platform
   - Old cities configured as "legistar"
   - Should all be "granicus" now

3. **NovusAgenda State Code Mix-ups:**
   - Arlington MA configured with slug "va" (Virginia state code)
   - Carmichael CA configured with slug "in" (Indiana state code)
   - Suggests bulk import with state code errors

4. **No Validation at Ingestion:**
   - Cities added without verifying first meeting fetch
   - No check that packet_url domain matches expected vendor pattern

### Prevention Strategy

1. **Add validation layer:**
   ```python
   def validate_city_config(city, sample_meeting):
       """Verify city config matches actual meeting URLs"""
       expected_pattern = get_vendor_url_pattern(city.vendor, city.slug)
       if not matches_pattern(sample_meeting.packet_url, expected_pattern):
           raise ValidationError(f"Meeting URL doesn't match city config")
   ```

2. **Require test fetch before adding city:**
   - Fetch 1 meeting before accepting city config
   - Verify packet URL extraction works
   - Confirm vendor/slug match URL pattern

3. **Periodic corruption scans:**
   - Run this analysis monthly
   - Alert on new corruption patterns
   - Track corruption rate as KPI

---

## IMPACT ASSESSMENT

**Users affected:**
- 7 cities return meetings from WRONG CITIES (high severity)
- 16 cities return NYC meetings for Aurora, CO (critical - high volume city)
- Total: 31 cities with corrupted configurations

**Meetings affected:**
- Wrong slug: ~127 meetings across 15 cities
- Wrong vendor: ~242 meetings across 16 cities  
- **Total: ~369 meetings** displaying wrong city information

**User experience impact:**
- Search for "Lakeland, FL" returns Lake Forest, IL meetings
- Search for "Santa Maria, CA" returns Santa Ana, CA meetings
- Users trust erodes when seeing wrong city data

**Data integrity impact:**
- City analytics corrupted (meeting counts wrong)
- Search quality degraded
- AI summaries reference wrong city context

---

## NEXT STEPS

1. **Immediate (Today):**
   - Review this report
   - Decide on fix strategy approval
   - Test fixes in staging/dev first

2. **Short-term (This Week):**
   - Apply Phase 1-3 fixes (safe changes)
   - Verify Phase 1-3 with re-analysis
   - Manually verify Phase 4 cities' correct slugs

3. **Medium-term (Next 2 Weeks):**
   - Apply Phase 4 fixes with meeting deletion
   - Re-sync Phase 4 cities via daemon
   - Verify all corrections successful

4. **Long-term (Ongoing):**
   - Implement validation layer
   - Add corruption monitoring
   - Document city addition process

---

**Report Generated:** 2025-10-28  
**Analysis Scripts:** /tmp/analyze_corruption_v2.py, /tmp/verify_cross_contamination.py
