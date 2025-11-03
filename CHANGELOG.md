# Changelog

All notable changes to the Engagic project are documented here.

Format: [Date] - [Component] - [Change Description]

---

## [2025-11-03] New: Motioncount Intelligence Layer (Grounding-Enabled Analysis)

**Using free grounding capacity that was going to waste.** Built complete intelligence layer that uses Gemini 2.0 Flash + Google Search grounding to detect housing law violations.

**What Was Built:**
- Complete grounding-enabled investigative analyzer
- Pre-filter for high-value items (housing/zoning keywords)
- Database schema for storing analysis results with full provenance
- Deploy script following engagic pattern (`./motioncount.sh`)
- Full citation tracking (queries, sources, citation mapping)

**Architecture:**
```
engagic.db (read-only)
  ├─ items table (existing summaries)
  └─ meetings table
         ↓
motioncount miner (NEW)
  ├─ Pre-filter: housing/zoning keywords
  ├─ Gemini 2.0 Flash + Google Search
  ├─ Researches laws, precedents, violations
  └─ Stores results with citations
         ↓
motioncount.db (NEW)
  └─ investigative_analyses table
       ├─ thinking (reasoning steps)
       ├─ research_performed (web searches)
       ├─ violations_detected (law, type, confidence, evidence)
       ├─ grounding_metadata (source URLs + citation mapping)
       └─ critical_analysis (markdown with citations)
```

**Key Insight:**
- Zero re-fetching, zero re-parsing, zero duplicate work
- Reads existing summaries from engagic.db
- Just adds intelligence layer on top
- Uses 1,500 FREE grounded requests/day (paid tier)

**Files Created:**
```
motioncount/
├── analysis/
│   └── investigative.py          # Grounding analyzer (227 lines)
├── database/
│   ├── engagic_reader.py          # Read-only from engagic.db (184 lines)
│   ├── db.py                      # Write to motioncount.db (385 lines)
│   └── models.py                  # Data models (135 lines)
├── scripts/
│   ├── run_investigative_batch.py # Batch processor (229 lines)
│   ├── view_violations.py         # Results viewer (101 lines)
│   └── test_analyzer.py           # Test script (211 lines)
├── config.py                      # Configuration (37 lines)
├── README.md                      # Full documentation
└── DEPLOY.md                      # Deployment guide

motioncount.sh                     # Deploy script (124 lines)
```

**Total Code:** ~1,633 lines

**Deploy Commands:**
```bash
# Single city
./motioncount.sh analyze-city paloaltoCA

# Regional
./motioncount.sh analyze-cities @regions/bay-area.txt

# Batch
./motioncount.sh analyze-unprocessed --limit 50

# View results
./motioncount.sh violations --limit 10
```

**What Gets Analyzed:**
- Pre-filter keywords: SB 35, SB 9, AB 2097, RHNA, housing element, ADU, parking mandates, zoning changes, CEQA
- OR items with 2+ topics: housing, zoning, planning, development
- Typical: 10-30% of items qualify

**What Gets Stored:**
- Thinking process (reasoning steps)
- Web research performed (queries + findings)
- Violations detected (law, type, confidence 1-10, evidence quotes, reasoning)
- Grounding metadata (source URLs, citation mapping)
- Critical analysis (markdown with inline citations)

**Cost Management:**
- Free tier: 1,500 grounded requests/day
- Pre-filter reduces volume by 70-90%
- Typical usage: 50-200 items/day analyzed
- Well within free tier limits

**Provenance Tracking:**
- Full grounding metadata captured
- Source URLs for all claims
- Citation mapping (which text segments link to which sources)
- Programmatic citation insertion available

**Separation of Concerns:**
- engagic: Neutral summarization (public good, open source)
- motioncount: Intelligence layer (grounding-enabled analysis)
- Clean database separation (engagic.db vs motioncount.db)
- Read-only access to engagic data

**Status:** Production ready, deployed on VPS, running first batch

**Value Unlock:**
- Uses free grounding capacity (1,500/day going to waste)
- Detects housing law violations with web-verified evidence
- Zero additional extraction cost (reads existing summaries)
- Builds corpus for future customer features

---

## [2025-11-03] Bug Fix: Summarizer Syntax Error (Extraneous Try Block)

**The issue:** Syntax error in `analysis/llm/summarizer.py` - extraneous `try:` block at line 279 without matching `except` clause.

**Fix:**
- Removed redundant `try:` block at line 279
- Fixed indentation for lines 290-572
- `except` clause at line 550 now properly matches `try:` at line 289

**Files Modified:**
- `analysis/llm/summarizer.py:279,290-572` - Removed extra try block, fixed indentation

**Verification:**
- `uv run ruff check --fix` - All checks passed
- `python3 -m py_compile` - Compilation successful

---

## [2025-11-03] Critical Bug Fix: Batch API Response Mismatching

**The silent data corruption.** Gemini Batch API inline requests do NOT guarantee response order matches request order, causing summaries to be assigned to wrong items.

**The Bug:**
- Used index-based matching: `response[i]` assumed to match `request[i]`
- Gemini Batch API processes requests asynchronously - responses can return out of order
- Item 1 got Item 2's summary, Item 2 got Item 17's summary, etc.
- Affected ALL batch-processed meetings (374+ cities, thousands of meetings)

**Root Cause:**
- Google's own documentation shows JSONL file method uses explicit `key` fields for matching
- But inline requests examples don't show metadata - we assumed index order was preserved
- Asynchronous batch processing means responses can complete in any order

**Fix:**
- Added `metadata: {"item_id": item_id}` to each inline request
- Match responses by metadata item_id instead of array index
- Defensive logging if metadata not supported by SDK
- Fallback plan: Switch to JSONL file method if metadata not available

**Files Modified:**
- `analysis/llm/summarizer.py:280-424` - Added metadata to requests, match by key in responses

**Testing:**
- Created `scripts/test_batch_metadata.py` to verify SDK metadata support
- Will re-process affected meetings if fix works, or implement JSONL method if not

**Impact:**
- Data integrity: Summaries will correctly match their agenda items
- User trust: No more confusing mismatched summaries
- System reliability: Guaranteed request/response matching

**Database Cleanup Required:** All batch-processed meetings need reprocessing with correct matching logic.

---

## [2025-11-02] Frontend Meeting Detail Page Redesign

**The legibility unlock.** Complete visual redesign of meeting detail page with focus on information hierarchy and readability.

**Changes:**
- Removed gradient pill number badges, replaced with inline plain text numbers ("1. ")
- Typography overhaul: System sans-serif titles (18px, weight 500, 1.45 line-height)
- Summary text: 16px Georgia with 0.01em letter-spacing for improved legibility
- Tighter spacing throughout: 1rem card padding (down from 1.25rem), 1rem gaps (down from 1.5rem)
- Attachment indicators moved to top-right corner badges
- Items collapsed by default with rich preview (title, 2 topics, attachment count)
- Pre-highlighting: Blue left border for items with AI summaries available
- Reactive Svelte templating for thinking traces (replaced DOM manipulation race conditions)
- Topic tags reduced from 3 to 2 in preview
- Subtle section labels: 10px uppercase, 1px letter-spacing, 40% opacity

**Files Modified:**
- `frontend/src/routes/[city_url]/[meeting_slug]/+page.svelte` (~400 lines changed)

**Impact:**
- Better information hierarchy (title → summary → attachments)
- More vertical space (20-30% more items visible)
- Improved readability for dense legislative text
- Clear visual indicators for summary availability
- No race conditions in thinking trace expand/collapse

---

## [2025-11-02] Critical Bug Fix: Missing 'type' Field in Attachments

**The silent failure.** All PrimeGov and Granicus cities (524 cities, 63% of platform) were failing to generate summaries due to missing 'type' field in attachment objects.

**The Bug:**
- PrimeGov/Granicus adapters created attachments without 'type' field
- Processor checked `if att_type == "pdf"` → failed (att_type was "unknown")
- PDFs never extracted, items marked "complete" with 0 summaries
- Silent failure - no errors raised, just empty results

**Impact:**
- 171 items in database with broken attachments (Los Angeles, Palo Alto)
- Would have affected 524 cities (461 Granicus + 63 PrimeGov) when scaled
- Caught before platform-wide rollout

**Fixes:**
- `vendors/adapters/html_agenda_parser.py:185` - Added 'type': 'pdf' to PrimeGov attachments
- `vendors/adapters/html_agenda_parser.py:283` - Added 'type': 'pdf' to Granicus attachments
- `vendors/adapters/primegov_adapter.py:154-155` - Defense-in-depth type field check
- `vendors/adapters/granicus_adapter.py:440-441` - Defense-in-depth type field check
- `pipeline/processor.py:321` - Handle "unknown" types defensively

**Database Cleanup:** Deleted 171 broken items, re-synced affected cities with fixed code.

---

## [2025-11-02] Procedural Item Filter

**Cost optimization.** Added filter to skip low-value procedural items before PDF extraction.

**Items Skipped:**
- Review/Approval of Minutes
- Roll Call
- Pledge of Allegiance
- Invocation
- Adjournment

**Implementation:** `pipeline/processor.py:27-41` - Simple pattern matching on item titles

**Impact:** Saves API costs by not summarizing administrative overhead items

---

## [2025-11-02] Database Repository Refactor

**The modularity unlock.** Refactored monolithic db.py into Repository Pattern.

**Changes:**
- Created `database/models.py` (233 lines) - City, Meeting, AgendaItem dataclasses
- Created `database/repositories/base.py` (71 lines) - Shared connection utilities
- Created 5 focused repositories (~250 lines each):
  - `cities.py` - City and zipcode operations (241 lines)
  - `meetings.py` - Meeting storage and retrieval (190 lines)
  - `items.py` - Agenda item operations (115 lines)
  - `queue.py` - Processing queue management (273 lines)
  - `search.py` - Search, topics, cache, stats (202 lines)
- Refactored `database/db.py` to 519-line facade that delegates to repositories
- Fixed missing `agenda_url` field in meetings table schema
- Zero breaking changes to external API

**Impact:**
- Each repository <300 lines (readable in one sitting)
- Clear separation of concerns
- Easier testing and maintenance
- UnifiedDatabase facade maintains simple external interface

**Code Changes:**
- db.py: 1,632 lines → 519 facade + 1,325 in repositories

---

## [2025-11-02] Server Modular Refactor

**The maintainability unlock.** Refactored monolithic main.py into clean modular architecture with separation of concerns.

**Changes:**
- Created `server/middleware/` - Request/response logging, rate limiting (69 lines)
- Created `server/models/` - Pydantic request validation (85 lines)
- Created `server/routes/` - 5 focused route modules (712 lines total):
  - `search.py`, `meetings.py`, `topics.py`, `admin.py`, `monitoring.py`
- Created `server/services/` - Business logic (346 lines)
- Created `server/utils/` - Reusable utilities (227 lines):
  - `geo.py`, `constants.py`, `validation.py`
- Eliminated code duplication:
  - State map: 3x → 1x (in `utils/constants.py`)
  - Meeting+items pattern: 5x → 1x (in `services/meetings.py`)

**Impact:**
- Maintainability: Largest module is 315 lines (search service)
- Testability: Services are pure functions with dependency injection
- Discoverability: Clear module hierarchy, tab-autocomplete friendly
- Zero breaking changes to API contracts
- Frontend: 100% compatible, no changes required

**Code Changes:**
- `server/main.py`: 1,473 → 98 lines (93% reduction)
- Total: -1,375 lines in main.py, reorganized into 20 focused modules

**Documentation:**
- `docs/main_py_refactor.md`
- `docs/frontend_audit_server_refactor.md`

---

## [2025-11-02] Pipeline Modular Refactor

**The clarity unlock.** Refactored conductor.py into 4 focused modules with clear responsibilities.

**Changes:**
- `pipeline/conductor.py` - Lightweight orchestration (268 lines, down from 1,133)
- `pipeline/fetcher.py` - City sync and vendor routing (437 lines, extracted from conductor)
- `pipeline/processor.py` - Queue processing and item assembly (465 lines, refactored)
- `pipeline/analyzer.py` - LLM analysis orchestration (172 lines, extracted from processor)

**Impact:**
- Mental model: "where is vendor sync logic?" → `fetcher.py`
- Each module <500 lines (readable in one sitting)
- Clean imports: `from pipeline.fetcher import Fetcher`
- Easier testing: Each module has focused responsibilities
- Zero breaking changes to external interfaces

**Code Changes:**
- conductor.py: 1,133 → 268 lines
- Net: Extracted into 3 focused modules with single responsibilities

---

## [2025-10-30] Item-First Architecture

**The UX unlock.** Refactored from meeting-summary-only to item-based-first architecture. Backend stores granular items, frontend composes display.

**Changes:**
- Removed concatenation from conductor.py (backend does data, not presentation)
- API endpoints include items array for item-based meetings
- Frontend displays numbered agenda items with topics and attachments
- Graceful fallback to markdown for monolithic meetings
- Zero breaking changes (backward compatible)

**Impact:**
- Users: Navigable, scannable agendas instead of walls of text
- Developers: Clean separation of concerns (backend=data, frontend=UI)
- System: Actually using the granular data we extract (not wasting LLM calls)

**Code Changes:**
- conductor.py: Removed concatenation, keep topic aggregation
- server/main.py: Include items in all search endpoint responses
- Frontend: Item display with topics, attachments, proper hierarchy

---

## [2025-10-30] Directory Reorganization

**The readability unlock.** Reorganized entire codebase into 6 logical clusters with tab-autocomplete-friendly names.

**Changes:**
- Created 6 logical clusters by purpose:
  - `vendors/` - Fetch from civic tech vendors
  - `parsing/` - Extract structured text
  - `analysis/` - LLM intelligence
  - `pipeline/` - Orchestrate the data flow
  - `database/` - Persistence layer
  - `server/` - API endpoints
- Extracted adapter factory (58 lines)
- Extracted vendor rate limiter (45 lines)
- Simplified processor.py (489 → 268 lines)
- Deleted 300+ lines of legacy/fallback code
- Updated all imports for clarity

**Impact:**
- Mental model: "where is PDF parsing?" → `parsing/`
- Tab autocomplete: `v<tab>` for vendors, `a<tab>` for analysis
- Conductor simplified: 1,477 → 1,133 lines (-24%)
- Clean imports: `from parsing.pdf import PdfExtractor`

**Code Deleted:**
- prompts.json (legacy v1), kept only prompts_v2.json
- v1 legacy parsing, removed PDF item detection
- 3 unused processing methods from conductor
- ONE TRUE PATH: HTML items → Batch, No items → Monolith

**Net:** -292 lines deleted + reorganization

---

## [2025-10-28] Granicus Item-Level Processing

**The platform unlock.** Granicus is the largest vendor (467 cities). Now 200+ Granicus cities support item-level processing via HTML agenda parsing.

**Changes:**
- HTML agenda parser extracts items from table structures
- MetaViewer PDF links mapped to specific items
- Full PDF text extraction (15K+ chars per document)
- Same pipeline as Legistar/PrimeGov - zero infrastructure changes

**Impact:**
- Item-level search and alerts for 200+ more cities
- Coverage: 174 cities → 374+ cities with items (58% of platform)
- Process 10-page chunks instead of 250-page packets
- Better failure isolation (one item fails, others succeed)
- Substantive summaries with financial data and policy details

**Code:**
- `vendors/adapters/granicus_adapter.py`
- `vendors/adapters/html_agenda_parser.py`

**Documentation:**
- `docs/BREAKTHROUGH_COMPLETE.md`

---

## [2025-10-15] Topic Extraction & Normalization - DEPLOYED

**The intelligence foundation.** Automatic topic tagging for all meetings and agenda items.

**Changes:**
- Per-item topic extraction using Gemini with JSON structured output
- Topic normalization to 16 canonical topics (`analysis/topics/taxonomy.json`)
- Meeting-level aggregation (sorted by frequency)
- Database storage (topics JSON column on items and meetings)
- API endpoints: `/api/topics`, `/api/search/by-topic`, `/api/topics/popular`
- Frontend displays topic badges on agenda items
- Color-coded topic badges (14 distinct color schemes)

**Impact:**
- Foundation for user subscriptions and smart filtering
- Enables topic-based discovery
- Consistent taxonomy across 500+ cities

**Code:**
- `analysis/topics/normalizer.py` (188 lines)
- `analysis/topics/taxonomy.json` (16 canonical topics)

---

## [2025-10-12] Participation Info Parsing - DEPLOYED

**The civic action unlock.** Parse and display contact info for meeting participation.

**Changes:**
- Parse email/phone/virtual_url/meeting_id from agenda text
- Store in `meetings.participation` JSON column
- Integrated into processing pipeline (`parsing/participation.py`)
- Normalized phone numbers, virtual URLs, hybrid meeting detection
- Frontend displays participation section on meeting pages
- Clickable contact methods: `mailto:`, `tel:`, Zoom URLs
- Badge indicators: "Hybrid Meeting", "Virtual Only"

**Impact:**
- Enables civic action with one click
- Users can directly email council or join Zoom meetings
- Mobile-friendly phone call links

**Code:**
- `parsing/participation.py` (87 lines)

---

## [2025-01-15] Earlier Improvements

**Database Consolidation:**
- 3 databases → 1 unified SQLite
- Net: -1,549 lines

**Adapter Refactor:**
- BaseAdapter pattern for shared HTTP/date logic
- Net: -339 lines

**Processor Modularization:**
- processor.py: 1,797 → 415 lines (-77%)
- Item-level processing for Legistar and PrimeGov
- Priority job queue with SQLite backend

**Total:** -2,017 lines eliminated

---

## Future

Track future milestones in VISION.md.
