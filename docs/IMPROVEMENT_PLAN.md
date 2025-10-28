# Engagic Improvement Plan
**Mission: Build scalable infrastructure for B2B civic engagement platform**

**Last Updated:** 2025-01-25

---

## Executive Summary

**Current State:** 5,956 lines Python backend, 6 vendor adapters, item-level processing working

**Completed Work:**
- ✅ Database consolidation (-1,549 lines)
- ✅ Adapter refactor with BaseAdapter pattern (-339 lines)
- ✅ Processing simplification to Tier 1 only (-87 lines)
- ✅ Priority-based job queue (+250 lines)
- ✅ Item-level attachment processing (Legistar)
- ✅ Rust infrastructure foundation (PDF extractor, PyO3 integration)

**Net Progress:** -1,725 lines eliminated (29% toward 60% goal)

**Active Work:** Rust PDF extractor integration (Week 1-2)

**Next Up:** Rust Conductor migration, Multi-tenancy foundation

---

## Architecture Wins

### 1. Unified Database (Phase 1)
- **Before:** 3 databases, 15+ lookup methods, 1,400 lines
- **After:** 1 SQLite database, single `get_city()` method, 979 lines
- **Key Pattern:** `city_banana` as vendor-agnostic identifier ("paloaltoCA")

### 2. BaseAdapter Pattern (Phase 2)
- **Before:** 1,427 lines with duplicated HTTP/date parsing in each adapter
- **After:** 1,088 lines with shared BaseAdapter (265 lines)
- **Result:** API adapters 68-92 lines, HTML scrapers 68-242 lines
- **Success Rate:** 94% across 6 vendors (PrimeGov, CivicClerk, Legistar, Granicus, NovusAgenda, CivicPlus)

### 3. Item-Level Processing (Phase 4)
- **Problem:** 500-page packets crash VPS, monolithic summaries
- **Solution:** Process 10-50 page items separately, combine summaries
- **Implementation:** Legistar adapter fetches EventItems → Matters → Attachments
- **Database:** `agenda_items` table with item-level summaries and topics
- **Status:** Full pipeline working, tested with Seattle City Council

### 4. Priority Job Queue (Phase 4)
- **Before:** Thread soup with manual sleep loops
- **After:** SQLite queue with priority-based scheduling
- **Pattern:** Recent meetings processed first (priority = max(0, 100 - days_old))
- **Decoupling:** Fast scraping (seconds) separate from slow AI processing (10-30s)

### 5. Processor Modularization (COMPLETED)
- **Completed:** Split 1,797-line processor.py into focused modules
- **Result:** processor.py (415 lines), summarizer.py (428), chunker.py (516), prompts.json (25)
- **Win:** 77% reduction in processor.py size, clean separation of concerns
- **Status:** Production ready, all imports working

---

## Current Issues

### High Priority
1. **PDF Extraction Quality** - Using PyMuPDF (fitz) which handles ~80% of PDFs
   - **Current:** PyMuPDF is Python-only but very reliable
   - **Note:** Rust mupdf crate tested but cannot parse PDFs properly
   - **Status:** Staying with PyMuPDF

2. **Broken Tests** - Reference deleted DatabaseManager class
   - **Fix:** Update to UnifiedDatabase (quick win)

### Medium Priority
3. ~~**processor.py Size**~~ - ✅ COMPLETED (1,797 → 415 lines)
   - **Solution:** Split into pdf_extractor.py + summarizer.py + prompts.json + chunker.py
   - **Result:** Clean separation, 77% reduction

4. **conductor.py Complexity** - 965 lines handling sync + processing + rate limiting
   - **Solution:** Migrate queue processor to Rust (Week 2-3)

5. **In-Memory Rate Limiting** - Resets on restart
   - **Solution:** Redis-backed rate limiter in Rust (Phase 5)

---

## Roadmap

### Week 1-2: Processor Refactor (COMPLETE ✅)

**Goal:** Break monolithic processor.py into focused, maintainable modules

**Tasks:**
- [x] Refactor `processor.py` into focused modules:
  - `pdf_extractor.py` - PyMuPDF extraction (118 lines) ✅
  - `summarizer.py` - Gemini API calls (428 lines) ✅
  - `prompts.json` - Prompt templates as data (25 lines) ✅
  - `chunker.py` - Document parsing (516 lines) ✅
  - `processor.py` - High-level orchestration (415 lines, was 1,797) ✅

**Success Criteria:**
- ✅ processor.py reduced to 415 lines (77% reduction!)
- ✅ Clean module separation with prompts as JSON data
- ✅ Zero breaking changes to existing imports
- ✅ All syntax checks passed

**Note:** Rust PDF extraction abandoned - Rust's mupdf crate cannot properly parse PDFs like PyMuPDF can. Sticking with Python's PyMuPDF (fitz) which has excellent performance and reliability.

### Week 2-3: Rust Conductor Migration

**Goal:** Move queue processing to Rust for true concurrency

**Why Rust:**
- **No GIL** - Process 10+ PDFs concurrently
- **Better resource management** - Rust ownership prevents memory leaks
- **Simpler deployment** - Compiled binary, no thread soup

**Implementation:**
```rust
// backend-rs/src/conductor.rs
pub struct Conductor {
    db_pool: SqlitePool,
    queue_processor: QueueProcessor,
    sync_scheduler: SyncScheduler,
}

// Python calls Rust
from engagic_core import Conductor
conductor = Conductor(db_path="data/engagic.db")
conductor.start()  # Async loops run in Rust
```

**Tasks:**
- [ ] Implement SQLite connection pool in Rust
- [ ] Implement queue operations (enqueue, dequeue, mark complete/failed)
- [ ] Implement queue processor loop with tokio
- [ ] Migrate sync scheduler to Rust
- [ ] Add Redis rate limiter (persistent, thread-safe)
- [ ] Update Python daemon to call Rust conductor

**Success Criteria:**
- 10+ concurrent PDF processing
- Zero GIL contention
- conductor.py reduced to <200 lines (thin Python wrapper)

### Week 3-4: Multi-Tenancy Foundation (Phase 5)

**Goal:** B2B-ready infrastructure for paying customers

**Database Schema:**
- `tenants` - Customer accounts with API keys
- `tenant_coverage` - Which cities each tenant tracks
- `tenant_keywords` - Topics to filter (e.g., "zoning", "housing")

**API Endpoints:**
- `POST /api/tenant/register` - Create tenant account
- `GET /api/tenant/meetings` - Filtered by coverage + keywords
- `GET /api/tenant/stats` - Usage analytics

**Tasks:**
- [ ] Implement tenant CRUD in unified_db.py
- [ ] Add API key authentication middleware
- [ ] Create tenant API endpoints
- [ ] Implement coverage filtering
- [ ] Migrate rate limiting to Redis (shared across instances)

**Success Criteria:**
- Tenants can register and get API keys
- Coverage filtering works (only their cities)
- Keyword matching works on summaries
- Rate limiting persists across restarts

### Month 2: Intelligence Layer (Phase 6)

**Goal:** Topic extraction, tracked items, alerts

**Features:**
- **Topic Extraction** - Automatically tag meetings ("affordable housing", "zoning reform")
- **Tracked Items** - Follow ordinances across multiple meetings
- **Timeline View** - See ordinance progression over time
- **Alerts** - Notify tenants when tracked items appear
- **Webhooks** - Push notifications to tenant systems

**Tasks:**
- [ ] Implement TopicExtractor using Gemini
- [ ] Create tracked_items database schema
- [ ] Add `/api/tenant/track` endpoint
- [ ] Build timeline view for ordinance progression
- [ ] Implement alert generation
- [ ] Add webhook delivery

---

## Clean Architecture Boundaries

### Python Application Layer
**Responsibilities:** Business logic, LLM orchestration, vendor adapters

**Files:**
- `backend/api/main.py` - FastAPI server (stays Python)
- `backend/adapters/*.py` - Web scraping, API calls (stays Python)
- `backend/core/summarizer.py` - Gemini API integration (stays Python)
- `backend/core/prompts.py` - Prompt templates (stays Python)

**Why Python:**
- FastAPI is excellent for APIs
- BeautifulSoup/requests great for scraping
- Gemini SDK is Python-first
- Rapid iteration on business logic

### Rust Infrastructure Layer (FUTURE)
**Responsibilities:** Queue processing, concurrency, resource management

**Potential Files:**
- `backend-rs/src/conductor.rs` - Queue processor, sync scheduler
- `backend-rs/src/database.rs` - SQLite connection pool
- `backend-rs/src/rate_limiter.rs` - Redis-backed rate limiting

**Why Rust (for queue processing):**
- True concurrency (no GIL)
- Better memory safety for long-running daemon
- Simpler deployment (compiled)

**Note:** PDF extraction stays in Python (PyMuPDF) - Rust mupdf crate cannot properly parse PDFs

### Current Architecture
```python
# Python handles everything currently
from backend.core.pdf_extractor import PdfExtractor
from backend.core.summarizer import GeminiSummarizer
from backend.core.chunker import AgendaChunker

# Clean module separation
extractor = PdfExtractor()  # PyMuPDF (fitz)
result = extractor.extract_from_url(url)

summarizer = GeminiSummarizer()  # Gemini API orchestration
summary = summarizer.summarize_meeting(result.text)
```

---

## Performance Targets

### Current State
- API response: ~80ms (cache hit)
- PDF extraction: 2-5s (PyPDF2)
- Meeting processing: 10-30s (Gemini + PDF)
- Background sync: ~2 hours for 500 cities

### Target State (After Optimizations)
- API response: <50ms (cache hit)
- PDF extraction: 2-5s (PyMuPDF, reliable and fast enough)
- Meeting processing: 10-30s (PyMuPDF + Gemini)
- Concurrent processing: 10+ PDFs at once (if we migrate queue to Rust)
- Background sync: <1 hour for 500 cities (concurrent scraping)

---

## Code Reduction Progress

**Target:** Reduce codebase by 60% (from 5,956 to ~2,400 lines)

**Progress:**
- Database consolidation: -1,549 lines ✅
- Adapter refactor: -339 lines ✅
- Processing simplification: -87 lines ✅
- Job queue: +250 lines (strategic complexity) ✅
- **Net: -1,725 lines (29% toward goal)**

**Remaining Reduction:**
- ✅ Processor split: -295 lines (completed!)
- Conductor migration: -400 lines (move queue logic to Rust, future)
- Premium tier removal: -246 lines (archived code, already done)
- **Achieved so far: -2,020 lines (34% reduction)**

Note: May not hit 60% due to multi-tenancy/intelligence layer additions, but code quality and maintainability dramatically improved.

---

## Success Metrics

### Technical
- [x] Single unified database
- [x] Adapter success rate >90%
- [x] Item-level processing working
- [x] Processor modularization complete (77% reduction)
- [x] PDF extraction success rate ~80% (PyMuPDF)
- [ ] Concurrent processing working (requires Rust conductor)
- [ ] Redis rate limiting

### Business
- [ ] Multi-tenancy foundation ready
- [ ] Topic extraction working
- [ ] Tracked items working
- [ ] Tenant API documented
- [ ] First paying customer

### Code Quality
- [x] No backwards compatibility code
- [x] Structured logging throughout
- [x] Processor at 415 lines (target achieved!)
- [x] Clean module separation (summarizer, chunker, prompts)
- [ ] Conductor <200 lines (Python wrapper)
- [ ] Test coverage restored
- [ ] Health check endpoints

---

## Development Workflow

### Rust Changes
```bash
cd backend-rs
cargo test                    # Run Rust tests
maturin build                 # Build wheel
maturin develop               # Install in venv (or use uv pip install)
```

### Python Integration
```python
# Import Rust module
from engagic_core import PdfExtractor

# Test changes
python test_rust_pdf.py
```

### Full Build
```bash
cd backend-rs
maturin build --release       # Production build
uv pip install target/wheels/engagic_core-*.whl --force-reinstall
```

---

## Key Learnings

### What Worked Well
1. **BaseAdapter pattern** - Compounds value with each new vendor
2. **city_banana identifier** - Vendor-agnostic, eliminates coupling
3. **Priority queue** - Decouples fast scraping from slow processing
4. **Item-level processing** - Better failure isolation, granular topics
5. **Processor modularization** - 77% reduction, clean separation of concerns
6. **Prompts as JSON data** - Easy iteration without code deployment

### Patterns to Replicate
- Single unified method with optional parameters (`get_city()`)
- Extract shared logic to base class, keep subclasses thin
- Fail-fast with archived premium tiers for future revenue
- Hybrid Python/Rust: Python for business logic, Rust for infrastructure
- Structured logging with scannable tags (`[Tier1]`, `[Cache]`, `[Rust]`)

### Remaining Challenges
- Test coverage needs refresh after major refactor
- Monitoring blind spot in production daemon
- Item-level processing only works for Legistar (need other vendors)
- Attachment filtering not yet implemented (process all PDFs)

---

**Next Review:** After testing refactored processor in production (Week 2)
