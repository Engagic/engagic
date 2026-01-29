# Matter Tracking Architecture

**Status:** Production (deployed)
**Purpose:** Track legislative items across meetings to build timelines showing policy evolution
**Core Value:** Model how government actually works - policy as events through time

---

## Why Matter Tracking Exists

### The Problem
Local government business items don't exist in isolation - they evolve across multiple meetings:

- **Ordinances** go through multiple readings (FIRST → SECOND → FINAL)
- **Contracts** get amended and extended across meetings
- **Resolutions** get reconsidered or modified
- **Development proposals** appear in study sessions, public hearings, final votes

Without matter tracking, each appearance looks like a separate item. Users can't answer:
- "What happened to Ordinance 2025-123?"
- "How did this zoning change evolve?"
- "When did the council first discuss this contract?"

### The Solution
**Legislative Timelines** - Track the same legislative matter across all its appearances.

Not just a cost optimization (though it saves ~50% on LLM costs by deduplicating summaries). It's about **modeling policy correctly**.

---

## Architecture Overview

### Three-Table Design

```
city_matters (canonical records)
├── id (composite: banana_hash)
├── matter_file (public ID like "BL2025-1098")
├── matter_id (vendor UUID)
├── title (normalized)
├── canonical_summary (deduplicated)
├── canonical_topics (deduplicated)
├── first_seen, last_seen
└── appearance_count

matter_appearances (timeline)
├── matter_id → city_matters.id
├── meeting_id
├── appearance_date
└── sequence (1st, 2nd, 3rd reading)

items (per-meeting instances)
├── id
├── meeting_id
├── matter_id → city_matters.id (nullable)
├── agenda_number
├── title
├── summary (may reference canonical)
└── attachments
```

### Data Flow

```
Vendor Adapter
  ↓
Meeting Ingestion Service
  ↓
Matter ID Generation ← Uses fallback hierarchy
  ↓
Deduplication Check
  ├─ New matter? → Store in city_matters
  └─ Existing? → Reuse canonical summary (if attachments unchanged)
  ↓
Create Appearance Record
  ↓
Store Agenda Item (with matter_id link)
```

---

## Fallback Hierarchy (Critical Design)

### Why Three Identification Methods?

Different civic tech vendors provide different levels of identifier stability:

1. **Legistar** - Provides stable `matter_file` (e.g., "BL2025-1098", "File #251041")
2. **PrimeGov (LA-style)** - Provides stable `matter_file` (e.g., "25-1206")
3. **PrimeGov (Palo Alto-style)** - Unstable UUIDs, must use title normalization
4. **Granicus** - Vendor UUIDs, moderate stability
5. **CivicClerk/CivicPlus** - Often no stable IDs at all

### The Three-Tier Hierarchy

#### Tier 1: `matter_file` (Preferred - Public Identifier)
```python
generate_matter_id("nashvilleTN", matter_file="BL2025-1098")
# → "nashvilleTN_7a8f3b2c1d9e4f5a"
```

**When to use:** Legistar, LA-style PrimeGov
**Stability:** Highest - Public legislative file number, never changes
**Coverage:** ~40% of cities

#### Tier 2: `matter_id` (Fallback - Vendor UUID)
```python
generate_matter_id("granicus_city", matter_id="fb36db52-abc-123")
# → "granicus_city_a1b2c3d4e5f6g7h8"
```

**When to use:** Granicus, IQM2, some PrimeGov
**Stability:** Medium - Vendor UUID, may change on system migrations
**Coverage:** ~50% of cities

#### Tier 3: `title` (Last Resort - Normalized Title)
```python
generate_matter_id("paloaltoCA", title="FIRST READING: Ordinance 2025-123")
# → "paloaltoCA_c4d5e6f7a8b9c0d1"

generate_matter_id("paloaltoCA", title="SECOND READING: Ordinance 2025-123")
# → "paloaltoCA_c4d5e6f7a8b9c0d1"  # Same ID!
```

**When to use:** Palo Alto-style PrimeGov, cities without stable vendor IDs
**Stability:** Medium - Relies on consistent title formatting
**Coverage:** ~10% of cities

**Normalization rules:**
- Strip reading prefixes (FIRST/SECOND/THIRD/FINAL READING)
- Lowercase everything
- Collapse whitespace
- Exclude generic titles (<30 chars or in exclusion list)

**Generic title exclusion list:**
- "Public Comment"
- "Staff Comments"
- "VTA" / "Caltrain" (transit reports)
- "Closed Session"
- "Open Forum"
- Any title under 30 characters

These items get `matter_id = None` and are always processed individually.

---

## Deduplication Strategy

### Attachment Hash Change Detection

When a matter appears in multiple meetings, we check if the attachments changed:

```python
current_hash = hash_attachments(agenda_item.attachments)
existing_matter = db.get_matter(matter_composite_id)

if existing_matter.attachment_hash == current_hash:
    # Same PDFs - reuse canonical summary
    item.summary = existing_matter.canonical_summary
else:
    # PDFs changed - reprocess
    enqueue_for_processing(item)
```

**Why this matters:**
- 1st reading: Ordinance text (process)
- 2nd reading: Same text (reuse summary)
- 3rd reading: Amended text (reprocess)

### Cost Savings

**Without deduplication:**
- 3 readings × $0.02/item = $0.06 per ordinance

**With deduplication:**
- 1st reading: $0.02 (process)
- 2nd reading: $0.00 (reuse)
- 3rd reading: $0.00 or $0.02 (reuse or reprocess if amended)
- Average: $0.02-$0.04 per ordinance

**50% savings**, but more importantly: **consistent summaries** across timeline.

---

## Cross-City Collision Prevention

### The Problem
What if two cities both have "Ordinance 2025-123"?

### The Solution
Every matter ID includes the `banana` (city identifier):

```python
nashville_id = generate_matter_id("nashvilleTN", matter_file="2025-123")
# → "nashvilleTN_7a8f3b2c1d9e4f5a"

memphis_id = generate_matter_id("memphisTN", matter_file="2025-123")
# → "memphisTN_a1b2c3d4e5f6g7h8"
```

**Banana scope:** All IDs, all fallback paths.

---

## Integration Points

### 1. Vendor Adapters
**Responsibility:** Extract matter identifiers from vendor HTML/API

```python
# legistar_adapter.py
item = {
    "matter_file": "BL2025-1098",  # Preferred!
    "matter_id": "uuid-abc-123",   # Fallback
    "title": "Ordinance Text",     # Last resort
}
```

**Quality checklist:**
- ✅ Extract `matter_file` if available (Legistar File #, PrimeGov MIG)
- ✅ Extract `matter_id` as fallback (vendor UUID)
- ✅ Always include `title` (required for cities without stable IDs)

### 2. Meeting Ingestion Service
**File:** `database/services/meeting_ingestion.py`

**Responsibility:** Generate matter IDs, deduplicate, track appearances

```python
def _process_agenda_items(self, items_data, meeting_obj, city, stats):
    for item_dict in items_data:
        # Generate matter ID using fallback hierarchy
        matter_composite_id = generate_matter_id(
            city.banana,
            item_dict.get("matter_file"),
            item_dict.get("matter_id"),
            item_dict.get("title")
        )

        if matter_composite_id:
            # Track matter + appearance
            self._track_matter(matter_composite_id, item_dict, meeting_obj)
```

### 3. Database Layer
**Files:** `database/repositories/matters.py`, `database/models.py`

**Responsibility:** Store matters, track appearances, deduplicate summaries

**Key methods:**
- `store_matter()` - Create canonical matter record
- `get_matter()` - Retrieve by composite ID
- `create_appearance()` - Track meeting appearance
- `update_matter_tracking()` - Update first_seen, last_seen, appearance_count

---

## Edge Cases & Handling

### 1. Generic/Procedural Items
**Problem:** "Public Comment" appears in every meeting

**Solution:** Return `None` from `generate_matter_id()`, set `matter_id = NULL` in database

```python
generate_matter_id("paloaltoCA", title="Public Comment")
# → None (caller should skip matter tracking)
```

### 2. Reading Prefix Variations
**Problem:** Inconsistent formatting across meetings

**Examples handled:**
- "FIRST READING: Ordinance..."
- "FIRST READ: Ordinance..."
- "REINTRODUCED FIRST READING: Ordinance..."
- "REINTRODUCED SECOND READ: Ordinance..."

**Solution:** Regex patterns in `normalize_title_for_matter_id()`

### 3. Attachment Changes Mid-Timeline
**Problem:** Ordinance amended between readings

**Solution:** Hash attachments, reprocess if changed

```python
if existing_matter.attachment_hash != new_attachment_hash:
    # Enqueue for reprocessing
    enqueue_job(item)
```

### 4. Matter File Format Changes
**Problem:** City changes numbering scheme mid-year

**Impact:** New IDs generated, breaks timeline continuity

**Mitigation:**
- Document when cities change schemes
- Manual mapping if critical (rare)
- Title-based fallback captures some continuity

### 5. Title Typos
**Problem:** "Ordinace 2025-123" (typo) won't match "Ordinance 2025-123"

**Mitigation:**
- Rely on `matter_file` when available (immune to typos)
- Title normalization is last resort only
- Conservative: False negatives > false positives

---

## Performance Implications

### Database Queries
**Per meeting sync:**
- 1 query: Check if matter exists (`get_matter`)
- 1 insert/update: Store or update matter
- N inserts: Create appearance records (one per item with matter)

**Indexes required:**
- `city_matters.id` (PRIMARY KEY)
- `city_matters.banana` (for city filtering)
- `matter_appearances.matter_id` (for timeline queries)
- `items.matter_id` (for joining items to matters)

### LLM Cost Impact
**Deduplication rate:** ~60% (items with matters × reuse rate)

**Example city (Palo Alto, 1 month):**
- 87 items total
- 54 items with matters (62%)
- 33 reused summaries (38% cost savings on those items)
- **Net savings:** ~20% overall

**Scale (500 cities, 1 year):**
- ~10,000 meetings
- ~50,000 items
- ~30,000 unique matters
- **20,000 deduplicated summaries = $400/year savings**

Not huge savings, but **timeline value is priceless** for civic engagement.

---

## Testing Strategy

### Unit Tests
**File:** `tests/test_id_generation.py`

**Coverage:**
- All 3 fallback paths (matter_file, matter_id, title)
- Reading prefix normalization
- Generic title exclusion
- Cross-city collision prevention
- Edge cases (empty strings, None values)

### Integration Tests
**File:** `tests/test_matter_tracking_integration.py`

**Coverage:**
- Full flow: vendor adapter → ingestion → deduplication
- Timeline tracking (1st, 2nd, 3rd readings)
- Attachment hash change detection
- Appearance count accuracy

### Production Validation
**Metrics to monitor:**
- Matter deduplication rate (target: 60%)
- Appearance count distribution (1, 2, 3+ readings)
- Title-based fallback usage (should be <10%)
- Generic item exclusion rate (should be 5-10%)

---

## Known Vendor Data Model Issues

### Charlotte NC (Legistar) - Multiple MatterFiles per Petition

**Discovered:** 2026-01-28

Charlotte's Legistar creates a **new MatterFile** for each procedural stage of the same rezoning petition:

| File # | Type | Stage |
|--------|------|-------|
| 15-25213 | Zoning Hearing | Initial public hearing |
| 15-25255 | Zoning Item | Committee review |
| 15-25304 | Consent Item | Final vote |

All three have the same title: "Rezoning Petition: 2025-103 by Pappas Properties"

**Impact:** 45+ rezoning petitions appear as 3-4 separate matters each (86 excess rows).

**Root cause:** Charlotte encodes the stable identifier (petition number like "2025-103") in the title, but creates new backend MatterFile IDs per stage. Our system keys on MatterFile.

**Potential fix:** Extract petition number from title pattern `Rezoning Petition: (\d{4}-\d{3})` and use as dedup key for Charlotte.

### Colorado Springs (Legistar) - Multiple Data Model Issues

**Discovered:** 2026-01-28

**Issue 1: MatterFile != Ordinance Number**

Colorado Springs MatterFile (e.g., `ZONE-25-0025`) differs from the actual citywide ordinance number (e.g., `25-103` in the title "Ordinance No. 25-103").

**Impact:** Unknown - needs investigation. May cause duplicate matters if same ordinance gets different internal file numbers.

**Issue 2: MatterSponsor = Planning Commission**

For zoning items, Colorado Springs lists "City Planning Commission" as the MatterSponsor (because they forward items to council). This is technically accurate but useless for identifying who actually championed the legislation.

**What we get:** `["City Planning Commission", "City Planning Commission", "City Planning Commission"]`

**What we should show:** Mover (Nadine Hensler), Seconder (Brian Clements) - available in `EventItemMover`/`EventItemSeconder` fields that we don't currently extract.

**Note:** Most Legistar cities use MatterSponsor correctly (actual council members). Colorado Springs is an outlier. The fix is to also extract EventItemMover/Seconder as supplementary data, not replace MatterSponsor logic.

### Legistar API Limitation - Mover/Seconder Not Exposed

**Discovered:** 2026-01-28

The Legistar web frontend displays Mover/Seconder for actions, but the API returns `null` for `EventItemMover` and `EventItemSeconder` fields. Tested on both Colorado Springs and Nashville - both return null.

**What the frontend shows:**
- Mover: Brian Risley
- Seconder: Tom Bailey

**What the API returns:**
```json
{
  "EventItemMover": null,
  "EventItemSeconder": null,
  "EventItemPassedFlag": 1,
  "EventItemActionName": "finally passed"
}
```

**Impact:** Cannot extract Mover/Seconder via API. Would require HTML scraping of Legistar web pages.

**Workaround:** The votes endpoint (`/eventitems/{id}/votes`) does return individual votes with person names and values (Aye/Nay/Absent/Recused). Could potentially infer mover from vote order, but not reliable.

---

## Future Improvements

### 1. Fuzzy Title Matching
For cities without stable IDs, use Levenshtein distance to catch typos:
```python
similarity("Ordinace 2025-123", "Ordinance 2025-123")  # 0.95 → match
```

### 2. Manual Matter Linking (Admin Tool)
For edge cases, allow admins to manually link matters:
```python
POST /admin/matters/link
{
  "matter_id_1": "paloaltoCA_abc123",
  "matter_id_2": "paloaltoCA_def456"
}
```

### 3. Matter Status Tracking
Extract and track matter status from vendor systems:
- Introduced
- In committee
- Public hearing scheduled
- Approved
- Rejected

### 4. Cross-Vendor Matter Linking
Some matters span multiple cities (regional transit, county initiatives):
```python
# Link Nashville and Memphis matters for regional transit bill
create_matter_group([
  "nashvilleTN_abc123",
  "memphisTN_def456"
])
```

---

## References

### Code Files
- **ID Generation:** `database/id_generation.py` (308 lines)
- **Ingestion Service:** `database/services/meeting_ingestion.py`
- **Matter Repository:** `database/repositories/matters.py`
- **Matter Model:** `database/models.py` (Matter class)
- **Tests:** `tests/test_id_generation.py`, `tests/test_matter_tracking_integration.py`

### Documentation
- **Schema:** `docs/SCHEMA.md` (city_matters, matter_appearances tables)
- **API:** `docs/API.md` (matter endpoints)
- **Migration:** `docs/POSTGRES_MIGRATION_SUMMARY.md` (Week 3 - this work)

### Related Features
- **Legislative Timelines:** Frontend displays matter evolution
- **Matter Pages:** `/matters/{matter_id}/timeline` API endpoint
- **City Matter Lists:** `/city/{banana}/matters` API endpoint

---

**Last Updated:** 2025-11-23
**Confidence Level:** 9/10 (Production-tested, handles edge cases)
**Complexity Justified:** Legislative timelines are core product value
