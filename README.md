# Engagic

AI-powered civic engagement platform that discovers, processes, and summarizes local government meeting agendas from 500+ cities.

Live at **[engagic.org](https://engagic.org)**

## Architecture (Post-Reorganization)

**~6,900 lines Python backend** (reorganized October 2025)

### Directory Structure

```
engagic/
├── vendors/            # Fetch from civic tech vendors
│   ├── adapters/       # 6 vendor adapters (Legistar, PrimeGov, Granicus, etc.)
│   ├── factory.py      # Adapter dispatcher
│   ├── rate_limiter.py # Vendor-aware rate limiting
│   └── validator.py    # Meeting validation
│
├── parsing/            # Extract structured text
│   ├── pdf.py          # PyMuPDF extraction
│   ├── participation.py # Parse participation info
│   └── chunker.py      # Document chunking
│
├── analysis/           # LLM intelligence
│   ├── llm/            # Gemini API orchestration
│   └── topics/         # Topic normalization (16 canonical topics)
│
├── pipeline/           # Orchestrate the data flow
│   ├── conductor.py    # Sync scheduling, priority queue
│   └── processor.py    # Processing orchestration
│
├── database/           # SQLite persistence
│   └── db.py          # Unified database (cities, meetings, items, queue)
│
├── server/             # Public API
│   ├── main.py        # FastAPI app
│   └── rate_limiter.py # API rate limiting
│
└── frontend/           # SvelteKit (Cloudflare Pages)
```

### Core Components

**vendors/** - Adapters for 6 civic tech platforms (BaseAdapter pattern, 94% success rate)
- Legistar (110 cities, API-based item extraction)
- PrimeGov (64 cities, HTML agenda parsing)
- Granicus (467 cities, 200+ with HTML item extraction)
- CivicClerk, NovusAgenda, CivicPlus

**parsing/** - Text extraction from PDFs and HTML
- PyMuPDF with actual page counts
- Participation info extraction (Zoom, phone, email)

**analysis/** - LLM intelligence
- Gemini API with adaptive prompts (standard vs large items)
- JSON structured output with schema validation
- Topic normalization to 16 canonical topics

**pipeline/** - Processing orchestration
- Priority queue (recent meetings first)
- Batch API for 50% cost savings
- Item-level vs monolithic processing paths

**database/** - Single SQLite database
- Cities, meetings, agenda_items, job_queue tables
- Cache-first serving

**server/** - FastAPI public API
- Zipcode search, cache-first serving
- Rate limiting (30 req/60s per IP)

## Key Design Patterns

**The ONE TRUE PATH**:
- HTML agenda → Extract items → Batch process → Aggregate
- PDF packet only → Monolithic summary
- No detection, no fallbacks, no parallel systems

**Cache-First**: API never fetches live data. Background daemon syncs cities every 72 hours.

**Priority Queue**: Recent meetings processed first. Decouples fast scraping (seconds) from slow AI processing (10-30s).

**Item-Level Processing**: 374+ cities (58% of platform) break 500-page packets into 10-50 page items.

**Adaptive Prompts**: Standard (<100 pages) vs Large (100+ pages) prompts based on actual PDF page counts.

**Vendor-Agnostic Identifier**: `city_banana` ("paloaltoCA") used internally instead of vendor-specific slugs.

## Setup

### Prerequisites
- Python 3.13+
- Node.js 18+
- Google Gemini API key

### Backend
```bash
# Install dependencies (uses uv)
uv sync

# Set environment variables
export GEMINI_API_KEY="your-key"
export ENGAGIC_DB_DIR="/root/engagic/data"
export ENGAGIC_ADMIN_TOKEN="secure-token"

# Run API server
uvicorn server.main:app --host 0.0.0.0 --port 8000

# Run background daemon (separate terminal)
python -m pipeline.daemon
```

### Frontend
```bash
cd frontend
npm install
npm run dev  # localhost:5173
```

## API Endpoints

### Public
- `POST /api/search` - Search by zipcode, city+state, or state only
- `POST /api/process-agenda` - Get cached summary (or trigger processing)
- `GET /api/random-best-meeting` - Discovery feature
- `GET /api/stats` - Cache statistics
- `GET /api/queue-stats` - Job queue status
- `GET /api/health` - Health check with detailed metrics
- `GET /api/metrics` - Prometheus-style metrics
- `GET /api/analytics` - Usage analytics

### Admin (Bearer token required)
- `GET /api/admin/city-requests` - View requested cities
- `POST /api/admin/sync-city/{banana}` - Force city sync
- `POST /api/admin/process-meeting` - Force meeting processing

## Search Modes

**Zipcode → City**: `"94301"` → Palo Alto, CA meetings

**City + State**: `"Palo Alto, CA"` or `"Palo Alto California"` → Direct match

**State Only**: `"CA"` or `"California"` → List of covered cities with meeting counts

**Ambiguous**: `"Springfield"` → Returns multiple state options

Handles 48+ state name variations, case-insensitive, space-normalized.

## Configuration

Environment variables (see `config.py`):

```bash
ENGAGIC_DB_DIR="/root/engagic/data"
ENGAGIC_UNIFIED_DB="/root/engagic/data/engagic.db"
ENGAGIC_HOST="0.0.0.0"
ENGAGIC_PORT="8000"
ENGAGIC_RATE_LIMIT_REQUESTS="30"
ENGAGIC_RATE_LIMIT_WINDOW="60"
ENGAGIC_SYNC_INTERVAL_HOURS="72"
ENGAGIC_LOG_LEVEL="INFO"
GEMINI_API_KEY="required"
ENGAGIC_ADMIN_TOKEN="required"
```

## Import Organization

Clean, tab-autocomplete-friendly imports:

```python
# Standard library
import logging
from typing import Dict, List

# Local clusters (alphabetical)
from analysis.llm.summarizer import GeminiSummarizer
from analysis.topics.normalizer import get_normalizer
from database.db import UnifiedDatabase
from parsing.pdf import PdfExtractor
from vendors.factory import get_adapter
```

## Performance

- API response: <100ms (cache hit)
- PDF extraction: 2-5s (PyMuPDF)
- Item processing: 10-30s per item (Gemini)
- Batch processing: 50% cost savings
- Background sync: ~2 hours for 500 cities
- Memory: ~200MB API, ~500MB daemon
- Capacity: 500 cities, ~10K meetings

## Development

**Local machine**: Write code only, no testing

**VPS**: Pull changes, test and deploy there

All code uses VPS paths as defaults (`/root/engagic/`).

## Recent Improvements

**October 2025: Directory Reorganization**
- Reorganized into 6 logical clusters (vendors, parsing, analysis, pipeline, database, server)
- Tab-autocomplete friendly names
- Deleted 300+ lines of legacy code
- Extracted adapter factory and rate limiter
- Simplified processor (489 → 268 lines)
- Conductor streamlined (1,477 → 1,133 lines)
- Clean imports: `from parsing.pdf` instead of `from infocore.processing.pdf_extractor`

**October 2025: Granicus Item-Level Processing**
- Crossed majority threshold: 174 → 374+ cities with item-level processing (58% of platform)
- HTML agenda parser for Granicus (200+ cities)
- MetaViewer PDF extraction with full text
- Zero infrastructure changes, same pipeline as Legistar/PrimeGov

**January 2025:**
- Database consolidation: 3 DBs → 1 unified SQLite
- Adapter refactor with BaseAdapter
- Processor modularization: 1,797 → 415 lines (-77%)
- Item-level processing for Legistar and PrimeGov
- Priority job queue with SQLite backend

**Net: -2,017 lines eliminated**

## Roadmap

See `docs/IMPROVEMENT_PLAN.md` for full technical roadmap.

**Immediate**: Full migration
- Update all old `infocore.*` imports to new structure
- Delete old directories
- Deploy to VPS

**Q4 2025**: Intelligence layer (topic extraction ✅, tracked items, timeline view, alerts)

**Q1 2026**: Multi-tenancy (tenant API, coverage filtering, keyword matching, Redis rate limiting)

**Future**: Remaining vendor item-level processing, Rust conductor migration

## Stack

Python 3.13, FastAPI, SQLite, BeautifulSoup, PyMuPDF, Google Gemini, SvelteKit, Cloudflare Pages

## License

Open source. See LICENSE file.

---

**Last Updated:** 2025-10-30 (Post-Reorganization)
