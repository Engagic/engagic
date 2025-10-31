# Directory Reorganization (October 2025)

## Summary

Reorganized the entire codebase from mixed concerns in `infocore/` and `jobs/` into 6 logical clusters with tab-autocomplete-friendly names.

**Result:** Clearer mental model, cleaner imports, ~300 lines deleted, improved readability.

---

## Old Structure (Before)

```
engagic/
├── infocore/
│   ├── api/
│   │   ├── main.py
│   │   └── rate_limiter.py
│   ├── database/
│   │   └── unified_db.py
│   ├── processing/
│   │   ├── processor.py (489 lines - mixed concerns)
│   │   ├── summarizer.py (617 lines - with legacy code)
│   │   ├── pdf_extractor.py
│   │   ├── participation_parser.py
│   │   ├── chunker.py
│   │   ├── topic_normalizer.py
│   │   ├── prompts.json (legacy v1)
│   │   └── prompts_v2.json
│   ├── adapters/
│   │   ├── base_adapter.py
│   │   ├── legistar_adapter.py
│   │   └── ... (6 total)
│   └── config.py
│
└── jobs/
    ├── conductor.py (1,477 lines - overloaded)
    └── meeting_validator.py
```

**Problems:**
- `infocore/processing/` contained extraction, orchestration, and intelligence
- conductor.py had rate limiting, adapter factory, and orchestration mixed
- Unclear imports: `from infocore.processing.pdf_extractor import PdfExtractor`
- No logical grouping by purpose

---

## New Structure (After)

```
engagic/
├── vendors/            # v<tab> - Fetch from civic tech vendors
│   ├── adapters/       # All 6 vendor adapters
│   ├── factory.py      # get_adapter() - 58 lines [NEW]
│   ├── rate_limiter.py # Vendor rate limiting - 45 lines [EXTRACTED]
│   └── validator.py    # Meeting validation [MOVED]
│
├── parsing/            # pa<tab> - Extract structured text
│   ├── pdf.py          # PyMuPDF extraction [RENAMED from pdf_extractor.py]
│   ├── participation.py # Parse participation [RENAMED from participation_parser.py]
│   └── chunker.py      # Document chunking [MOVED]
│
├── analysis/           # a<tab> - LLM intelligence
│   ├── llm/
│   │   ├── summarizer.py    # 592 lines (cleaned) [MOVED]
│   │   └── prompts_v2.json  # JSON prompts only [MOVED]
│   └── topics/
│       ├── normalizer.py    # Topic normalization [MOVED]
│       └── taxonomy.json    # 16 canonical topics [MOVED]
│
├── pipeline/           # pi<tab> - Orchestrate the data flow
│   ├── conductor.py    # 1,133 lines (slimmed) [MOVED + CLEANED]
│   └── processor.py    # 268 lines (simplified) [NEW]
│
├── database/           # d<tab> - Persistence layer
│   └── db.py          # SQLite operations [RENAMED from unified_db.py]
│
├── server/             # s<tab> - API endpoints
│   ├── main.py        # FastAPI app [MOVED from infocore/api/]
│   └── rate_limiter.py # API rate limiting [MOVED]
│
└── config.py           # Root-level config [MOVED]
```

---

## What Changed

### Files Created
- `vendors/factory.py` (58 lines) - Extracted from conductor
- `vendors/rate_limiter.py` (45 lines) - Extracted from conductor
- `pipeline/processor.py` (268 lines) - Simplified from infocore/processing/processor.py

### Files Moved/Renamed
| Old Path | New Path | Change |
|----------|----------|--------|
| `infocore/adapters/*` | `vendors/adapters/*` | Moved |
| `jobs/meeting_validator.py` | `vendors/validator.py` | Moved |
| `infocore/processing/pdf_extractor.py` | `parsing/pdf.py` | Moved + Renamed |
| `infocore/processing/participation_parser.py` | `parsing/participation.py` | Moved + Renamed |
| `infocore/processing/chunker.py` | `parsing/chunker.py` | Moved |
| `infocore/processing/summarizer.py` | `analysis/llm/summarizer.py` | Moved |
| `infocore/processing/prompts_v2.json` | `analysis/llm/prompts_v2.json` | Moved |
| `infocore/processing/topic_normalizer.py` | `analysis/topics/normalizer.py` | Moved |
| `infocore/processing/topic_taxonomy.json` | `analysis/topics/taxonomy.json` | Moved |
| `jobs/conductor.py` | `pipeline/conductor.py` | Moved |
| `infocore/database/unified_db.py` | `database/db.py` | Moved + Renamed |
| `infocore/api/main.py` | `server/main.py` | Moved |
| `infocore/api/rate_limiter.py` | `server/rate_limiter.py` | Moved |
| `infocore/config.py` | `config.py` | Moved to root |

### Files Deleted
- `infocore/processing/prompts.json` (legacy v1)
- ~300 lines of fallback/legacy code from conductor and summarizer

---

## Line Count Changes

| File | Before | After | Change |
|------|--------|-------|--------|
| conductor.py | 1,477 | 1,133 | **-344** (extracted + cleaned) |
| summarizer.py | 617 | 592 | **-25** (deleted v1 parsing) |
| processor.py (old) | 489 | - | Replaced |
| processor.py (new) | - | 268 | **-221** (simplified) |
| factory.py (new) | - | 58 | Extracted |
| rate_limiter.py (new) | - | 45 | Extracted |
| **Total** | **2,583** | **2,096** | **-487 lines** |

---

## Import Changes

### Before (Confusing)
```python
from infocore.database import UnifiedDatabase
from infocore.processing.processor import AgendaProcessor
from infocore.processing.pdf_extractor import PdfExtractor
from infocore.processing.summarizer import GeminiSummarizer
from infocore.processing.topic_normalizer import get_normalizer
from infocore.adapters.legistar_adapter import LegistarAdapter
from infocore.config import config
```

### After (Clear)
```python
from database.db import UnifiedDatabase
from pipeline.processor import AgendaProcessor
from parsing.pdf import PdfExtractor
from analysis.llm.summarizer import GeminiSummarizer
from analysis.topics.normalizer import get_normalizer
from vendors.factory import get_adapter
from config import config
```

**Benefits:**
- Shorter paths
- Self-documenting (parsing.pdf = PDF parsing)
- Tab autocomplete friendly (v<tab>, p<tab>, a<tab>)
- Alphabetical by cluster name

---

## Migration Plan

### Phase 1: Files Copied ✅
All new files created in new structure with updated imports.

### Phase 2: Full Migration (NEXT)
1. Update all remaining imports in old `infocore/` files
2. Move old files to new locations
3. Test everything works
4. Delete old `infocore/` and `jobs/` directories

### Phase 3: VPS Deployment
1. Git commit and push
2. SSH to VPS
3. Pull changes
4. Update systemd services if needed
5. Test

---

## Mental Model

**Before:** "Where is PDF parsing?" → Maybe processing? Maybe adapters? Not sure.

**After:** "Where is PDF parsing?" → parsing/

**Purpose-based clusters:**
1. **vendors/** = Get it from external sources
2. **parsing/** = Extract structured text
3. **analysis/** = Understand it with AI
4. **pipeline/** = Coordinate the flow
5. **database/** = Store it
6. **server/** = Serve it to users

---

## Code Improvements

### Deleted Dead Code (-300 lines)
- Removed PDF item detection from conductor (130 lines)
- Removed 3 unused processing methods (132 lines)
- Removed v1 legacy parsing from summarizer (49 lines)
- Deleted prompts.json (legacy file)

### Extracted Concerns
- Rate limiter out of conductor → vendors/rate_limiter.py
- Adapter factory out of conductor → vendors/factory.py
- Simplified processor logic → pipeline/processor.py

### ONE TRUE PATH
- HTML items → Batch processing
- No items → Monolithic processing
- **No** detection, **no** fallbacks, **no** parallel systems

---

## Tab Autocomplete

Type first letters:
- `v` → vendors/
- `pa` → parsing/ (or `pi` → pipeline/)
- `a` → analysis/
- `d` → database/
- `s` → server/

All unique first letters except parsing/pipeline (need 2 chars).

---

## Next Steps

1. Full migration (update old imports, delete old dirs)
2. Deploy to VPS
3. Monitor for import errors
4. Optional: Extract response parser from summarizer (120 lines)

---

**Completed:** 2025-10-30
