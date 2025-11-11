# VENDOR ADAPTER REFACTORING PROPOSAL
**Date:** 2025-11-10
**Context:** Vendor adapter complexity growing with 11 adapters totaling ~5,100 lines

---

## EXECUTIVE SUMMARY

**Current state:** Vendor adapters work well but contain duplicate logic and growing complexity
**Primary concern:** Legistar adapter is 980 lines (2.5x base adapter size)
**Impact:** Code duplication, harder maintenance, steeper learning curve for new vendors

**Proposed solution:** Extract 4 utility modules to reduce duplication and isolate complexity

---

## THE NUMBERS

### Current Line Counts
```
Base adapter:               389 lines (shared HTTP, date parsing)
html_agenda_parser.py:      710 lines (5 parsing functions, vendor-specific)

Legistar (giant):           980 lines (API + HTML + attachment filtering)
Granicus (large):           455 lines (view_id discovery + HTML scraping)
IQM2 (new):                 332 lines
CivicPlus:                  325 lines
Berkeley custom:            383 lines
Menlo Park custom:          193 lines
PrimeGov:                   189 lines
NovusAgenda:                195 lines
CivicClerk:                  99 lines
eScribe:                    155 lines

Total vendor code:        ~5,100 lines
```

### Growth Pattern
- **6 vendors (Nov 2)** → **11 vendors (Nov 10)** in 8 days
- New vendors added: IQM2, eScribe (both well-sized at <350 lines)
- Custom adapters: Berkeley, Menlo Park (necessary for high-value cities)

---

## IDENTIFIED PATTERNS

### Pattern 1: Attachment Filtering Logic (Duplicate Code)

**Current state:**
- Legistar: `_filter_leg_ver_attachments()` (48 lines) - deduplicates "Leg Ver1/Ver2" attachments
- PrimeGov: No filtering (just downloads via `download_attachment()`)
- Granicus: Relies on html_agenda_parser
- Others: Various approaches

**Problem:** Attachment deduplication logic is Legistar-specific but would help other vendors

**Proposed extraction:**
```
vendors/utils/attachments.py
├─ filter_duplicate_attachments()  # Generic version matching logic
├─ prioritize_version_attachments()  # "Ver2" > "Ver1" > base
└─ normalize_attachment_metadata()  # Consistent naming across vendors
```

**Estimated savings:** 60-80 lines, clearer separation of concerns

---

### Pattern 2: Item Filtering (Partially Extracted)

**Current state:**
- Legistar: `should_skip_item()` (module-level, 18 lines) - filters procedural items
- Used ONLY in Legistar adapter (line 791)
- Other adapters: Don't filter procedural items (yet)

**Pattern list:**
```python
SKIP_ITEM_PATTERNS = [
    r'appointment',
    r'confirmation',
    r'public comment',
    r'roll call',
    r'approval of (minutes|agenda)',
    r'adjourn',
]
```

**Observation:** This is already well-designed (module-level function, clear regex patterns)

**Proposed action:** Move to shared utility so other adapters can reuse

```
vendors/utils/item_filters.py
├─ should_skip_procedural_item()  # Renamed from should_skip_item
├─ PROCEDURAL_PATTERNS  # Constant (already exists)
└─ add_custom_skip_patterns()  # Allow city-specific overrides
```

**Estimated savings:** Enable other adapters to use this (cleaner data)

---

### Pattern 3: HTML Agenda Parser Sprawl (710 lines, 5 functions)

**Current state:**
`vendors/adapters/html_agenda_parser.py` contains:
1. `parse_primegov_html_agenda()` - PrimeGov-specific parsing
2. `parse_granicus_html_agenda()` - Granicus-specific parsing
3. `parse_legistar_html_agenda()` - Legistar-specific parsing
4. `parse_legistar_legislation_attachments()` - Legistar attachment scraping
5. `parse_novusagenda_html_agenda()` - NovusAgenda-specific parsing
6. Internal helpers: `_extract_agenda_items()`, `_extract_attachments()`, etc.

**Problem:** Single 710-line file with vendor-specific logic (violates single responsibility)

**Proposed restructure:**
```
vendors/adapters/parsers/
├─ __init__.py
├─ primegov_parser.py     (~150 lines)
├─ granicus_parser.py     (~120 lines)
├─ legistar_parser.py     (~250 lines, includes attachment logic)
├─ novusagenda_parser.py  (~100 lines)
└─ base_parser.py         (~90 lines, shared HTML utilities)
```

**Benefits:**
- Easier to find vendor-specific code
- Can test parsers independently
- Clearer ownership (Legistar parser lives with Legistar logic conceptually)
- Reduces html_agenda_parser.py from 710 → 0 lines (deleted)

**Estimated impact:** No line reduction, but MUCH clearer architecture

---

### Pattern 4: Legistar Dual-Mode Complexity (980 lines)

**Current structure:**
```python
LegistarAdapter (980 lines)
├─ API mode (lines 1-400)
│   ├─ _fetch_meetings_api()
│   ├─ _fetch_event_items()
│   ├─ _fetch_matter_attachments()
│   ├─ _parse_xml_events()
│   ├─ _parse_xml_event_items()
│   └─ _parse_xml_attachments()
│
├─ HTML fallback mode (lines 400-800)
│   ├─ _fetch_meetings_html()
│   ├─ _parse_html_agenda_items()
│   └─ _fetch_item_attachments()
│
└─ Shared utilities (lines 800-980)
    ├─ _filter_leg_ver_attachments()
    └─ should_skip_item()
```

**Problem:** Two completely different code paths in one file

**Proposed split:**
```
vendors/adapters/
├─ legistar_adapter.py          (~400 lines, orchestration + API mode)
└─ legistar_html_fallback.py    (~350 lines, HTML scraping mode)

vendors/utils/
└─ attachments.py               (~80 lines, filtering logic)
```

**Approach:**
```python
# legistar_adapter.py
class LegistarAdapter(BaseAdapter):
    def fetch_meetings(self, days_back=7, days_forward=14):
        """Try API first, fall back to HTML"""
        try:
            yield from self._fetch_meetings_api(days_back, days_forward)
        except Exception as e:
            logger.warning(f"API failed: {e}, falling back to HTML")
            from vendors.adapters.legistar_html_fallback import fetch_html_meetings
            yield from fetch_html_meetings(self, days_back, days_forward)
```

**Benefits:**
- Main adapter file: 980 → 400 lines (60% reduction)
- Clear separation: API vs HTML
- Easier to test each mode independently
- HTML fallback can be improved without touching API logic

**Estimated impact:** Legistar becomes readable again

---

## PROPOSED REFACTORING ROADMAP

### Phase 1: Low-Hanging Fruit (1-2 hours)
**Goal:** Extract obvious utilities without breaking anything

1. **Create `vendors/utils/` directory**
   ```bash
   mkdir -p vendors/utils
   touch vendors/utils/__init__.py
   ```

2. **Extract item filtering**
   - Move `should_skip_item()` from legistar_adapter.py → `vendors/utils/item_filters.py`
   - Update Legistar import: `from vendors.utils.item_filters import should_skip_procedural_item`
   - Test: Run linting, type checking, verify Legistar still works

3. **Extract attachment utilities**
   - Move `_filter_leg_ver_attachments()` from Legistar → `vendors/utils/attachments.py`
   - Rename to `filter_version_attachments()` (remove Leg Ver specificity)
   - Generalize for other vendors (e.g., "Draft v1/v2" filtering)

**Deliverable:** 2 new utility modules, Legistar reduced by ~80 lines

---

### Phase 2: HTML Parser Restructure (2-3 hours)
**Goal:** Break up 710-line html_agenda_parser.py into vendor-specific modules

1. **Create parser directory**
   ```bash
   mkdir -p vendors/adapters/parsers
   ```

2. **Split parsers**
   - `primegov_parser.py` - extract `parse_primegov_html_agenda()` + helpers
   - `granicus_parser.py` - extract `parse_granicus_html_agenda()`
   - `legistar_parser.py` - extract Legistar HTML parsing functions
   - `novusagenda_parser.py` - extract NovusAgenda parsing
   - `base_parser.py` - shared HTML utilities (BeautifulSoup helpers, common patterns)

3. **Update imports in adapters**
   ```python
   # Before
   from vendors.adapters.html_agenda_parser import parse_primegov_html_agenda

   # After
   from vendors.adapters.parsers.primegov_parser import parse_html_agenda
   ```

4. **Delete old file**
   ```bash
   rm vendors/adapters/html_agenda_parser.py
   ```

**Deliverable:** Clean parser directory, 710-line monolith eliminated

---

### Phase 3: Legistar Split (2-3 hours)
**Goal:** Separate API and HTML modes in Legistar

1. **Create HTML fallback module**
   - Extract HTML scraping functions → `legistar_html_fallback.py`
   - Keep API functions in main `legistar_adapter.py`

2. **Implement fallback pattern**
   ```python
   def fetch_meetings(self):
       try:
           yield from self._fetch_meetings_api()
       except Exception:
           yield from self._fetch_meetings_html()
   ```

3. **Test both modes**
   - Test API mode with known good cities
   - Test HTML mode with cities that have no API

**Deliverable:** Legistar adapter 980 → ~400 lines, clearer code paths

---

### Phase 4: Documentation & Validation (1 hour)
**Goal:** Ensure refactor is correct and documented

1. **Run full test suite**
   ```bash
   uv run ruff check --fix
   uv run pyright
   python3 -m py_compile vendors/**/*.py
   ```

2. **Update CLAUDE.md**
   - Reflect new `vendors/utils/` directory
   - Update vendor line counts
   - Document new parser structure

3. **Verify no regressions**
   - Test 3-5 cities per vendor
   - Ensure meeting fetching still works
   - Check item extraction accuracy

**Deliverable:** Clean, documented, tested refactor

---

## ESTIMATED IMPACT

### Line Count Reduction
```
Before refactor:
├─ legistar_adapter.py:        980 lines
├─ html_agenda_parser.py:      710 lines
├─ Other adapters:           ~3,410 lines
└─ Total:                    ~5,100 lines

After refactor:
├─ legistar_adapter.py:        400 lines (-60%)
├─ vendors/utils/:             200 lines (new)
├─ vendors/adapters/parsers/:  710 lines (reorganized, not reduced)
├─ Other adapters:           ~3,300 lines (slight reduction from shared utils)
└─ Total:                    ~4,610 lines (-10%)
```

**Total savings:** ~500 lines + MUCH better organization

---

## ARCHITECTURAL BENEFITS

### Before Refactor
```
vendors/
├─ adapters/
│   ├─ base_adapter.py (389 lines)
│   ├─ legistar_adapter.py (980 lines) ← TOO BIG
│   ├─ html_agenda_parser.py (710 lines) ← MIXED CONCERNS
│   └─ [8 other adapters]
└─ factory.py
```

### After Refactor
```
vendors/
├─ adapters/
│   ├─ base_adapter.py (389 lines)
│   ├─ legistar_adapter.py (400 lines) ← READABLE
│   ├─ legistar_html_fallback.py (350 lines) ← CLEAR FALLBACK
│   ├─ parsers/
│   │   ├─ base_parser.py (90 lines)
│   │   ├─ primegov_parser.py (150 lines)
│   │   ├─ granicus_parser.py (120 lines)
│   │   ├─ legistar_parser.py (250 lines)
│   │   └─ novusagenda_parser.py (100 lines)
│   └─ [8 other adapters]
├─ utils/
│   ├─ attachments.py (80 lines) ← REUSABLE
│   └─ item_filters.py (50 lines) ← REUSABLE
└─ factory.py
```

**Benefits:**
- **Discoverability:** Clear where to find vendor-specific logic
- **Testability:** Smaller modules = easier unit tests
- **Maintainability:** Touching PrimeGov parser doesn't risk breaking Legistar
- **Extensibility:** New vendors can reuse utilities immediately
- **Cognitive load:** No single file >500 lines

---

## RISKS & MITIGATIONS

### Risk 1: Breaking existing adapters
**Mitigation:**
- Refactor one adapter at a time
- Run linting + type checking after each change
- Test with real cities before committing

### Risk 2: Import hell (circular dependencies)
**Mitigation:**
- Keep utilities pure (no adapter imports)
- Parsers import from utils, adapters import from parsers
- Clear dependency hierarchy: utils → parsers → adapters

### Risk 3: Overgeneralization
**Mitigation:**
- Don't force commonality where it doesn't exist
- Keep vendor-specific quirks in vendor-specific files
- Utilities should be OBVIOUSLY reusable (not speculative)

---

## RECOMMENDATION

**Priority:** HIGH (but not urgent)

**When to do this:**
- ✅ NOW: Phases 1-2 (extract utils, split parsers) - prevents further accumulation
- ⏸️ LATER: Phase 3 (Legistar split) - can wait until Legistar becomes painful
- ✅ ALWAYS: Phase 4 (validation) - after any refactor

**Reasoning:**
- Vendor adapters are core to your product (data ingestion)
- You're adding vendors FAST (5 in 8 days)
- Current code works but is headed toward "unmaintainable"
- Refactor now = easier to add IQM2/NovusAgenda item-level parsing
- This is classic "entropy resistance" work (exactly what you asked for)

**Alternative:** If you don't refactor, you WILL hit pain when:
1. A new vendor needs attachment filtering (have to duplicate Legistar logic)
2. HTML parsing breaks (have to debug 710-line file)
3. Legistar API changes (980 lines to reason about)

---

## TESTING STRATEGY

For each refactored module:

1. **Compilation test**
   ```bash
   python3 -m py_compile vendors/**/*.py
   ```

2. **Import test**
   ```python
   from vendors.factory import get_adapter
   adapter = get_adapter("legistar", "cambridge")
   assert adapter is not None
   ```

3. **Integration test** (manual spot-check)
   ```python
   # Test 2-3 cities per vendor
   cities = [
       ("legistar", "cambridge"),
       ("primegov", "cityofpaloalto"),
       ("granicus", "santamonica"),
   ]
   for vendor, slug in cities:
       adapter = get_adapter(vendor, slug)
       meetings = list(adapter.fetch_meetings())
       assert len(meetings) > 0
   ```

4. **Regression test**
   - Before refactor: Export meeting counts per city
   - After refactor: Verify counts match (±5% tolerance for date windows)

---

## NEXT STEPS

**Immediate (if approved):**
1. Create `vendors/utils/` directory
2. Extract `item_filters.py` (30 min)
3. Extract `attachments.py` (45 min)
4. Test with 3 cities (15 min)
5. Commit: "Extract vendor utilities (item_filters, attachments)"

**This week (if time permits):**
1. Create `vendors/adapters/parsers/` directory
2. Split html_agenda_parser.py (2 hours)
3. Update all adapter imports (30 min)
4. Test + commit: "Restructure HTML parsers by vendor"

**Next week (optional):**
1. Split Legistar adapter (2 hours)
2. Full regression testing (1 hour)
3. Update documentation (30 min)

---

**Confidence:** 9/10 (this refactor is low-risk, high-value)

**Estimated total time:** 6-8 hours for full roadmap
**Estimated partial time:** 2-3 hours for Phases 1-2 (biggest wins)

---

## DECISION POINT

**Option A: Full refactor (Phases 1-4)**
- Timeline: 6-8 hours over 2-3 sessions
- Impact: 500-line reduction, much clearer architecture
- Risk: Low (incremental, tested changes)

**Option B: Partial refactor (Phases 1-2 only)**
- Timeline: 2-3 hours in one session
- Impact: 200-line reduction, extract utilities + split parsers
- Risk: Very low (minimal scope)

**Option C: Defer**
- Timeline: N/A
- Impact: Continue accumulating complexity
- Risk: Medium (will be harder later)

**Recommended:** Option B (Phases 1-2), then reassess after IQM2/NovusAgenda item-level work

---

**Last updated:** 2025-11-10
**Author:** Claude (via architecture audit)
**Status:** Proposal (awaiting approval)
