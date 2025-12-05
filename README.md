# Engagic

AI-powered civic engagement platform that discovers, processes, and summarizes local government meeting agendas from 500+ cities.

Live at **[engagic.org](https://engagic.org)**

---

## What It Does

Engagic fetches city council meeting agendas from civic tech platforms (Legistar, PrimeGov, Granicus, etc.), extracts structured data, and uses LLMs to generate summaries that civilians can understand.

**Key capabilities:**
- **Item-level processing:** 86% of cities get structured agenda items (not just PDF blobs)
- **Matters-first architecture:** Legislative items tracked across meetings with deduplication
- **Council member profiles:** Elected officials tracked with normalized names, sponsorship history
- **Committee tracking:** Legislative bodies with rosters and member assignments
- **Voting records:** Individual votes per member per matter, tallies, outcomes across meetings
- **Topic extraction:** 16 canonical civic topics for filtering and alerts
- **Participation info:** Email, phone, Zoom links for civic action
- **Deliberation:** Opinion clustering for structured public input on legislative matters

---

## Architecture

```
                        Frontend (SvelteKit)
                              |
                              v
                        Server (FastAPI)
                              |
              +---------------+---------------+
              |               |               |
              v               v               v
         Database        Pipeline         Analysis
        (PostgreSQL)   (Orchestration)     (LLM)
              |               |               |
              +-------+-------+               |
                      |                       |
                      v                       v
                  Vendors  <-----------------+
               (11 Adapters)
```

**~29,000 lines Python backend** organized into focused modules:

| Module | Purpose | Details |
|--------|---------|---------|
| [vendors/](vendors/README.md) | 11 civic tech platform adapters | HTML parsers, API clients, rate limiting |
| [analysis/](analysis/README.md) | LLM intelligence | Gemini API, topic extraction, adaptive prompts |
| [pipeline/](pipeline/README.md) | Processing orchestration | Sync scheduling, queue management, batch processing |
| [database/](database/README.md) | PostgreSQL repository pattern | 14 async repositories, matters tracking, userland schema |
| [server/](server/README.md) | FastAPI public API | 16 route modules (votes, committees, etc.), tiered rate limiting |
| [userland/](userland/README.md) | Civic alerts system | Magic link auth, email digests, keyword matching |
| [parsing/](parsing/README.md) | PDF extraction | PyMuPDF, OCR fallback, participation parsing |
| [deliberation/](deliberation/README.md) | Opinion clustering | PCA + k-means, consensus detection |

---

## Key Patterns

**Matters-First:** Legislative items (bills, ordinances) tracked across meetings. Process once, reuse summary. Attachment hash detects changes.

**Item-Level Processing:** HTML agendas parsed into structured items. Each item gets focused summary. Topics aggregated to meeting level.

**Cache-First API:** Server never fetches live. Background daemon syncs cities every 72 hours, processes queue continuously.

**Async PostgreSQL:** Connection pooling (asyncpg, 5-20 connections), `FOR UPDATE SKIP LOCKED` for queue processing, UPSERT for idempotent updates.

**Legislative Accountability:** Council members tracked across votes and sponsorships. Committees tracked with rosters. Vote outcomes computed per matter per meeting.

**Repository Pattern:** 14 async repositories with shared connection pool. Each repository handles one domain (cities, meetings, items, matters, queue, search, userland, council_members, committees, engagement, feedback, deliberation, helpers).

**AsyncBaseAdapter:** All 11 vendor adapters implement unified interface. Async HTTP with retry, rate limiting, date parsing. Adapters return `vendor_id`, database generates canonical IDs.

**Orchestrator Delegation:** Pipeline delegates business logic to orchestrators (MeetingSyncOrchestrator, EnqueueDecider, MatterFilter, VoteProcessor). Enables testing and separation of concerns.

---

## Processing Flow

```
Sync Loop (72h)              Processing Loop (continuous)
     |                              |
     v                              v
  Fetcher                      Processor
     |                              |
     v                              |
  Vendors (11)                      |
     |                              |
     v                              v
  Database          <----     Queue (typed jobs)
     |                              |
     |                              v
     |                         Item-Level Path (86%)
     |                              or
     |                         Monolithic Fallback (14%)
     |                              |
     |                              v
     +-------------------->    Analysis (LLM)
```

**Two Processing Paths:**
- **Item-level (86%):** Structured agenda items, per-item summaries, topic aggregation
- **Monolithic (14%):** PDF packet, comprehensive summary, single LLM call

---

## Quick Start

### Prerequisites
- Python 3.13+
- PostgreSQL 14+
- Node.js 18+
- Google Gemini API key

### Backend

```bash
# Install dependencies
uv sync

# Set environment variables
export GEMINI_API_KEY="your-key"
export POSTGRES_HOST="localhost"
export POSTGRES_DB="engagic"
export POSTGRES_USER="engagic"
export POSTGRES_PASSWORD="***"

# Run API server
uvicorn server.main:app --host 0.0.0.0 --port 8000

# Run background daemon (separate terminal)
python -m pipeline.conductor daemon
```

### Frontend

```bash
cd frontend
npm install
npm run dev  # localhost:5173
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/VISION.md](docs/VISION.md) | Mission, roadmap, architectural philosophy |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production deployment guide |
| [docs/API.md](docs/API.md) | Complete API endpoint reference |
| [docs/SCHEMA.md](docs/SCHEMA.md) | Database schema quick reference |
| [docs/MATTERS_ARCHITECTURE.md](docs/MATTERS_ARCHITECTURE.md) | Legislative matter tracking design |
| [docs/ARCHITECTURE_REVIEW.md](docs/ARCHITECTURE_REVIEW.md) | Architecture priorities |
| [docs/TERMS_OF_SERVICE.md](docs/TERMS_OF_SERVICE.md) | API rate tiers and usage policies |
| [CHANGELOG.md](CHANGELOG.md) | Version history and recent changes |

---

## Stack

Python 3.13, FastAPI, PostgreSQL, asyncpg, BeautifulSoup, PyMuPDF, Google Gemini, SvelteKit, Cloudflare Pages

---

## License

Open source. See LICENSE file.
