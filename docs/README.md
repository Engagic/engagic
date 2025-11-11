# Engagic Documentation

Comprehensive documentation for the Engagic civic intelligence platform.

---

## Getting Started

### For Developers
- **[Deployment Guide](DEPLOYMENT.md)** - Deploy to production VPS, systemd setup, monitoring
- **[Vision & Roadmap](VISION.md)** - Mission, architecture philosophy, and growth phases

### For Contributors
- **Project Architecture** - See `CLAUDE.md` in project root
- **Coding Standards** - See `CLAUDE.md` for implementation rules and patterns

---

## Module Documentation (NEW)

Comprehensive folder-level documentation for core modules:

- **[Pipeline Documentation](../pipeline/README.md)** (~700 lines)
  - Processing flow orchestration (4 focused modules)
  - Item-level vs monolithic processing paths
  - Queue architecture and job types
  - Matter tracking workflow
  - Configuration and deployment

- **[Database Documentation](../database/README.md)** (~800 lines)
  - Repository Pattern architecture
  - 6 specialized repositories (cities, meetings, items, matters, queue, search)
  - Complete schema documentation
  - Data models and preservation patterns
  - Common operations and examples

- **[Server Documentation](../server/README.md)** (~850 lines)
  - Modular FastAPI architecture
  - 6 route modules + service layer + middleware
  - Complete API endpoints reference
  - Prometheus metrics and rate limiting
  - Common patterns for extending the API

---

## Core Documentation

### Architecture & Philosophy
- **[Vision](VISION.md)** - Mission statement, architectural intuition, roadmap (Phases 0-6)
  - Item-first architecture principles
  - Two parallel pipelines (item-based vs monolithic)
  - Technical principles (reliability, privacy, scalability)
  - Honest assessment of what works and what's missing

### Operations
- **[Deployment Guide](DEPLOYMENT.md)** - Production deployment on VPS
  - Initial setup (Python 3.13, uv, systemd services)
  - Nginx reverse proxy configuration
  - Monitoring and health checks
  - Memory management and troubleshooting
  - Backup strategy

---

## Features

### Deployed Features

#### Topic Extraction (Phase 1)
- **[Topic Extraction Documentation](TOPIC_EXTRACTION.md)** - Automated topic tagging
  - 16 canonical topics with normalization
  - Per-item and meeting-level aggregation
  - API endpoints: `/api/topics`, `/api/search/by-topic`, `/api/topics/popular`
  - Frontend integration complete

**Status:** DEPLOYED (October 2025)

#### Contact Info Parsing (Phase 0)
- Email, phone, Zoom link extraction from agendas
- Frontend displays participation section
- Click-to-email, click-to-call functionality
- Hybrid meeting detection

**Status:** DEPLOYED (October 2025)

---

## API Reference

- **[Server README](../server/README.md)** - Complete server module documentation
  - Modular FastAPI architecture
  - Route modules and service layer
  - Middleware and dependency injection

- **[API Documentation](API.md)** - Public API endpoint reference
  - Search endpoints (zipcode, city, topic)
  - Topic endpoints (list, search, popular)
  - System endpoints (health, stats, metrics)
  - Admin endpoints (sync, processing)
  - Rate limiting, authentication, error codes

**Quick Start:**
- Base URL: `https://api.engagic.org`
- Rate Limit: 30 requests/60 seconds per IP
- All endpoints return JSON

---

## Database

- **[Database README](../database/README.md)** - Complete module documentation
  - Repository Pattern architecture and implementation
  - Data models and common operations
  - Python code usage examples

- **[Schema Documentation](SCHEMA.md)** - Quick reference for SQL queries
  - Table schemas and column definitions
  - JSON structures (topics, participation, attachments)
  - Query examples and maintenance commands

**Technology:**
- SQLite 3.x with WAL mode
- JSON columns for flexibility
- Foreign key constraints enforced

---

## Future Vision

### SmokePAC / Campaign Finance Layer
- **[SmokePAC Documentation](SMOKEPAC.md)** - Vision for campaign finance integration
  - Connect donations to voting records
  - Track developer-councilmember relationships
  - Expose conflicts of interest
  - Separate confrontational layer from neutral Engagic core

**Status:** Future project, planning phase

---

## Historical Documentation

Completed work sessions, refactoring notes, and architectural decisions.

- **[Archive Index](archive/README.md)** - Historical documentation
  - Item-first architecture migration notes
  - Granicus breakthrough documentation
  - Performance optimization history
  - VPS migration checklists

---

## Quick Reference

### Directory Structure
```
engagic/
├── vendors/        # Adapters for 6 civic tech platforms
├── parsing/        # PDF extraction, participation info
├── analysis/       # LLM intelligence, topic normalization
├── pipeline/       # Processing orchestration
├── database/       # SQLite persistence layer
├── server/         # FastAPI public API
└── frontend/       # SvelteKit (Cloudflare Workers)
```

### Key Concepts

**city_banana** - Vendor-agnostic identifier (e.g., "paloaltoCA")
**Item-first architecture** - Backend stores granular data, frontend composes display
**Cache-first API** - Never fetches live, background daemon syncs every 72 hours
**Two pipelines** - Item-based (58% of cities) and monolithic (42% fallback)

---

## Support

**Issues:** Create GitHub issue with logs and error details
**Questions:** See `CLAUDE.md` for architectural decisions

---

**Last Updated:** November 11, 2025

**See Also:**
- [../pipeline/README.md](../pipeline/README.md) - Pipeline module documentation
- [../database/README.md](../database/README.md) - Database module documentation
- [../server/README.md](../server/README.md) - Server module documentation
- [../CLAUDE.md](../CLAUDE.md) - Project overview and coding standards
