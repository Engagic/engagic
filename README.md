# Engagic

AI-powered civic engagement platform that discovers, processes, and summarizes local government meeting agendas from 500+ cities.

Live at **[engagic.org](https://engagic.org)**

## Architecture

**7,618 lines Python backend**

- `infocore/api/main.py` - FastAPI server, cache-first serving, multi-modal search
- `infocore/database/unified_db.py` - Single SQLite database, city/meeting/agenda_items
- `infra/conductor.py` - Priority job queue, sync scheduling, rate limiting
- `infocore/adapters/` - 6 vendor adapters with BaseAdapter pattern (94% success rate)
- `infocore/processing/processor.py` - High-level orchestration (refactored: 1,797 → 415 lines)
- `infocore/processing/summarizer.py` - Gemini API integration
- `infocore/processing/pdf_extractor.py` - PyMuPDF text extraction
- `infocore/processing/chunker.py` - Document parsing and boundary detection
- `infocore/adapters/html_agenda_parser.py` - HTML agenda parsing (PrimeGov/Granicus)
- `frontend/` - SvelteKit (Cloudflare Pages)

## Key Design Patterns

**Cache-First**: API never fetches live data. Background daemon syncs cities every 72 hours.

**Priority Queue**: Recent meetings processed first. Decouples fast scraping (seconds) from slow AI processing (10-30s).

**Item-Level Processing**: Breaks 500-page packets into 10-50 page items for better failure isolation and granular topic extraction. Working for 374+ cities (58% of platform): Legistar (API), PrimeGov (HTML agendas), Granicus (HTML agendas + MetaViewer PDFs).

**Vendor-Agnostic Identifier**: `city_banana` ("paloaltoCA") used internally instead of vendor-specific slugs.

**Fail-Fast**: Single tier (PyMuPDF + Gemini) for free processing. Premium tiers archived for future paid customers.

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
export ENGAGIC_DB_DIR="/root/engagic/data"  # VPS path
export ENGAGIC_ADMIN_TOKEN="secure-token"

# Run API server
uvicorn infocore.api.main:app --host 0.0.0.0 --port 8000

# Run background daemon (separate terminal)
python -m infra.daemon
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

Environment variables (see `infocore/processing/config.py`):

```bash
ENGAGIC_DB_DIR="/root/engagic/data"
ENGAGIC_UNIFIED_DB="/root/engagic/data/engagic.db"
ENGAGIC_HOST="0.0.0.0"
ENGAGIC_PORT="8000"
ENGAGIC_RATE_LIMIT_REQUESTS="30"
ENGAGIC_RATE_LIMIT_WINDOW="60"
ENGAGIC_SYNC_INTERVAL_HOURS="72"
ENGAGIC_PROCESSING_INTERVAL_HOURS="2"
ENGAGIC_LOG_LEVEL="INFO"
GEMINI_API_KEY="required"
ENGAGIC_ADMIN_TOKEN="required"
```

## Adapters

Supported vendors (BaseAdapter pattern):
- **Legistar** (110 cities, item-level via API)
- **PrimeGov** (64 cities, item-level via HTML agendas)
- **Granicus** (467 cities, 200+ with item-level via HTML agendas)
- CivicClerk (16 cities)
- NovusAgenda
- CivicPlus

Each adapter: 68-242 lines. Shared logic in BaseAdapter (265 lines).
HTML agenda parser: `html_agenda_parser.py` (shared by PrimeGov/Granicus).

## Performance

- API response: <100ms (cache hit)
- PDF extraction: 2-5s (PyMuPDF)
- Meeting processing: 10-30s (Gemini)
- Background sync: ~2 hours for 500 cities
- Memory: ~200MB API, ~500MB daemon
- Capacity: 500 cities, ~10K meetings

## Development

**Local machine**: Write code only, no testing

**VPS**: Pull changes, test and deploy there

All code uses VPS paths as defaults (`/root/engagic/`).

## Recent Improvements

**October 2025: Granicus Item-Level Processing**
- Crossed majority threshold: 174 → 374+ cities with item-level processing (58% of platform)
- HTML agenda parser for Granicus (200+ cities)
- MetaViewer PDF extraction with full text (15K+ chars per document)
- Zero infrastructure changes, same pipeline as Legistar/PrimeGov

**January 2025:**
- Database consolidation: 3 DBs → 1 unified SQLite (-1,549 lines)
- Adapter refactor with BaseAdapter (-339 lines)
- Processor modularization: 1,797 → 415 lines (-77%)
- Item-level processing for Legistar and PrimeGov
- Priority job queue with SQLite backend

Net: -1,725 lines eliminated

## Roadmap

See `docs/IMPROVEMENT_PLAN.md` for full technical roadmap.

**Q4 2025**: Intelligence layer foundations (topic extraction, tracked items, timeline view, basic alerts)

**Q1 2026**: Multi-tenancy (tenant API, coverage filtering, keyword matching, Redis rate limiting)

**Future**: CivicClerk/NovusAgenda/CivicPlus item-level processing, Rust conductor migration

## License

Open source. See LICENSE file.

## Stack

Python 3.13, FastAPI, SQLite, BeautifulSoup, PyMuPDF, Google Gemini, SvelteKit, Cloudflare Pages
