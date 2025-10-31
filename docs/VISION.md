# Engagic Vision

**Last Updated:** October 30, 2025

---

## Inspiration

Local government is the most impactful layer of democracy - zoning, housing, schools, police budgets - yet the least accessible.

**The problem:**
- 250-page meeting packets released days before decisions
- Obscure vendor portals across 500+ platforms
- No way to know when issues you care about are being discussed
- Civic engagement becomes a privilege of those with time and expertise

**The opportunity:**
- AI can read and summarize these documents
- Scraping can unify fragmented data sources
- Topic extraction can match issues to citizens
- Open source can build trust in civic infrastructure

**The mission:** Make local government meetings accessible to everyone, not just political insiders.

---

## Intuition (Architecture)

Engagic is built in layers, each serving different users:

### Core Data Layer (Free OSS)
**What:** Scraping, processing, storage - the source of truth
**Users:** Civic hackers, researchers, other civic tech projects
**Access:** Direct database, open source codebase
**Principle:** Public data should be freely accessible and machine-readable

Components (6 logical clusters):
- **vendors/** - Adapters for 6 platforms (BaseAdapter pattern, 94% success rate)
- **parsing/** - PDF text extraction (PyMuPDF) and participation info
- **analysis/** - LLM intelligence (Gemini) and topic normalization (16 canonical topics)
- **pipeline/** - Processing orchestration, priority queue, sync scheduling
- **database/** - SQLite database (cities, meetings, agenda_items, job_queue)
- **server/** - FastAPI public API with cache-first serving

Architecture:
- Item-level processing for 374+ cities (58% of platform, 50-80M people)
- Two parallel pipelines: item-based (primary) and monolithic (fallback)
- Cache-first API (never fetches live, background daemon syncs every 72 hours)
- Priority queue (recent meetings first)

### Userland (Consumer Features)
**What:** Profiles, alerts, digests - built ON TOP of core data layer
**Users:** Civilians who want to engage with local government
**Access:** Web app, PWA with notifications
**Principle:** Design APIs that civilians can understand

Features (to build):
- User profiles: city + topics subscriptions
- Alert system: topic matching → notifications
- Weekly email digest: summaries of relevant meetings
- PWA notifications: iOS/Android push via service workers
- Mobile-first design

### Integrations (Third-Party Bridges)
**What:** Read-only bridges to decentralized platforms
**Users:** Communities building civic discourse tools
**Access:** Public API, read-only database views (NOT direct DB access)
**Principle:** Protect the source of truth, enable innovation

Examples:
- Bluesky: per-city boards/feeds
- ATProto: decentralized civic discourse
- Public API: filtered, rate-limited access

### Tenancy (B2B Paid Layer)
**What:** API keys, coverage filtering, webhooks
**Users:** Advocacy orgs, law firms, policy researchers
**Access:** Authenticated API with tenant-specific filtering
**Principle:** Sustainable funding enables free public tier

Features (to build):
- Tenant accounts with API keys
- Coverage filtering (only their cities)
- Keyword matching on summaries
- Usage analytics
- Webhooks (push notifications to client systems)

---

## Implementation (Current Architecture - October 2025)

### Core Components (6 Logical Clusters)
- **vendors/** - 6 platform adapters with BaseAdapter pattern (Legistar, PrimeGov, Granicus, CivicClerk, NovusAgenda, CivicPlus)
  - 94% success rate across 500+ cities
  - Rate limiting: 3-5s between vendor requests
  - Factory pattern for adapter dispatch

- **parsing/** - Text extraction and participation info
  - PyMuPDF with actual page counts
  - Participation info extraction (Zoom, phone, email)

- **analysis/** - LLM intelligence and topic normalization
  - Gemini API with adaptive prompts (standard vs large items)
  - JSON structured output with schema validation
  - 16 canonical topics with normalization

- **pipeline/** - Processing orchestration
  - Priority queue (recent meetings first, SQLite-backed)
  - Item-level processing for 374+ cities (58% of platform)
  - Two parallel pipelines: item-based (primary) and monolithic (fallback)
  - Batch API for 50% cost savings

- **database/** - Single unified SQLite
  - Cities, meetings, agenda_items, job_queue tables
  - JSON columns for topics, participation, attachments

- **server/** - FastAPI public API
  - Cache-first serving (never fetches live)
  - Background daemon syncs every 72 hours
  - Rate limiting: 30 req/60s per IP
  - Zipcode search, topic search, popular topics endpoints

### Honest Assessment

**What Works (November 2025):**
- ✅ 500+ cities, 374+ with item-level processing (58% coverage)
- ✅ Item-based frontend (navigable, scannable agendas)
- ✅ Topic extraction ready for deployment (16 canonical topics)
- ✅ Cache-first API (<100ms response times)
- ✅ Backend participation info (email/phone/Zoom)
- ✅ Priority queue, adaptive prompts, batch processing

**What's Missing (User Features):**
- ❌ Frontend participation info display (backend ready, quick win)
- ❌ Frontend topic filtering/badges (backend ready)
- ❌ User accounts/profiles
- ❌ Email notifications/alerts
- ❌ Weekly digest emails
- ❌ Mobile PWA notifications

**Highly requested:**
- "Email me when my city discusses zoning"
- "Weekly digest of meetings in my city"
- "Alert me about housing issues"
- "Show me how to participate (Zoom link, email)"

**Current users:** Civic hackers, researchers who can consume raw API data. Average citizens can browse but can't subscribe to alerts yet.

---

## Roadmap (Growth Features)

### Phase 0: Contact Info Parsing - BACKEND COMPLETE ✅
**Goal:** Make participation easier with contact info

**Status:** Backend complete, frontend implementation pending

**Backend Implementation (COMPLETE):**
- ✅ Parse email/phone/virtual_url/meeting_id from agenda text
- ✅ Store in `meetings.participation` JSON column
- ✅ Integrated into processing pipeline
- ✅ Normalized phone numbers, virtual URLs, hybrid meeting detection

**Frontend Implementation (TODO):**
- Display participation section prominently on meeting detail pages
- Clickable `mailto:city@council.gov` (opens email app)
- Clickable `tel:+1-555-0100` (mobile-friendly phone calls)
- Clickable Zoom/virtual URLs
- Badge for "Hybrid Meeting" or "Virtual Only"
- Pre-filled email with meeting context: `mailto:?subject=Re: [Meeting Title]&body=Dear Council...`
- No sending on user's behalf (liability), just make it easy to participate

**Impact:** Low-hanging fruit, high user value, enables civic action

### Phase 1: Topic Extraction (Foundation) - COMPLETE ✅
**Goal:** Automatically tag meetings and agenda items with topics

**Status:** Implementation complete, ready for deployment

**Implementation (COMPLETE):**
- ✅ Per-item topic extraction using Gemini with JSON structured output
- ✅ Topic normalization to 16 canonical topics (analysis/topics/)
- ✅ Meeting-level aggregation (sorted by frequency)
- ✅ Database storage (topics JSON column on items and meetings)
- ✅ API endpoints: /api/topics, /api/search/by-topic, /api/topics/popular
- ✅ Test suite passing (scripts/test_topic_extraction.py)

**Next Steps:**
- Deploy to VPS (pull, migrate, restart services)
- Run backfill for existing meetings (optional)
- Frontend integration for topic filtering

**Impact:** Unlocks search by topic, user subscriptions, smart filtering, and analytics. Foundation for all user-facing features.

### Phase 1.5: AI Thinking Traces (Transparency) - OPTIONAL
**Goal:** Show users how AI analyzed the meeting - build trust through transparency

**Implementation:**
- Test Gemini API for native thinking trace support (gemini-2.0-flash-thinking-exp)
- If not native, use chain-of-thought prompting
- Database schema: `thinking_trace TEXT` on meetings and agenda_items tables
- Frontend: Collapsible section "Show AI reasoning"
- Parse and store both thinking trace + summary

**Cost consideration:** Adds 30-50% more tokens (~$5-10 for 10K meetings)

**Why deferred:** Good for transparency, but not blocking. Topic extraction is the critical path.

### Phase 2: User Profiles (Core Growth)
**Goal:** Let civilians subscribe to cities and topics

**Implementation:**
- Simple profile: city + topics (no passwords yet, just email-based magic links?)
- Database: `user_profiles`, `user_subscriptions`
- Minimal onboarding: "Enter your email and city"
- Topic selection from extracted taxonomy

**Why:** Unlocks alert system and retention

### Phase 3: Alerts & Notifications
**Goal:** Notify users when relevant meetings happen

**Implementation:**
- Topic matching: compare meeting topics to user subscriptions
- Email alerts: "Your city is discussing zoning tonight"
- PWA push notifications: iOS/Android via service workers
- Weekly digest: summary of all relevant meetings

**Why:** Core user value, drives engagement

### Phase 4: Integrations (Decentralized Discourse)
**Goal:** Enable community discussion on decentralized platforms

**Implementation:**
- Public read-only API (rate limited, no auth)
- Bluesky integration: auto-create per-city boards/feeds
- ATProto bridges for decentralized civic discourse
- Database access through views, never direct

**Why:** Builds ecosystem, enables innovation, protects core

### Phase 5: B2B Tenancy (Sustainability)
**Goal:** Paid tier for organizations

**Implementation:**
- Tenant accounts with API keys
- Coverage filtering (only their cities)
- Keyword matching on summaries
- Webhooks (push notifications to client systems)
- Usage analytics

**Why:** Sustainable funding for free public tier

---

## Technical Principles

### Reliability
- Government data sources are fragile; build defensively
- Cache aggressively, invalidate intelligently
- Fail-fast processing (single tier for free, premium archived for paid)
- Make failure states informative, not cryptic

### Privacy
- Minimal data collection (search queries only, not stored)
- No user tracking beyond opt-in subscriptions
- Open source builds trust in civic applications
- IP addresses not permanently stored

### Scalability
- Start simple (SQLite) but plan for growth
- Measure first, add complexity only when metrics demand it
- Design services to be stateless for horizontal scaling
- Cost awareness: Cloud costs can kill civic projects

### Architecture
- Core data layer owns the truth, others consume through APIs
- Protect the source of truth (no direct DB access for integrations)
- Layer features on top, don't couple them to core
- Each layer can scale independently

---

## Success Metrics

### Core Data Layer (Data Quality)
- [x] Multi-vendor adapter system operational (6 platforms, BaseAdapter pattern)
- [x] Item-level processing working (374+ cities, 58% coverage)
- [x] Directory reorganization complete (6 logical clusters)
- [x] Contact info parsing (email/phone/virtual URLs)
- [x] Topic extraction and normalization (16 canonical topics, ready for deployment)
- [ ] AI thinking traces exposed (optional, deferred)
- [ ] 1,000+ cities covered

### Userland (Engagement)
- [ ] User profiles launched
- [ ] 1,000 email subscribers
- [ ] 10,000 email subscribers
- [ ] Weekly digest sent
- [ ] PWA notifications working
- [ ] 50% weekly active users

### Integrations (Ecosystem)
- [ ] Public API documented
- [ ] Bluesky integration live
- [ ] 10+ third-party apps using API
- [ ] Decentralized civic discourse boards

### Tenancy (Sustainability)
- [ ] First paying customer
- [ ] $1,000 MRR (covers infrastructure)
- [ ] $10,000 MRR (sustainable)
- [ ] Tenant webhooks working

---

## Key Learnings

### What Worked
- **BaseAdapter pattern** - compounds value with each new vendor (6 platforms, 94% success)
- **city_banana identifier** - vendor-agnostic, eliminates coupling
- **Priority queue** - improves user experience (recent meetings first)
- **Item-level processing** - better summaries, granular topics, batch API cost savings (50%)
- **HTML agenda parsing** - reusable pattern across vendors (Granicus breakthrough: +200 cities)
- **Item-first architecture** - backend stores data, frontend composes display (separation of concerns)
- **Directory reorganization** - 6 logical clusters, tab-autocomplete friendly (-292 lines)
- **Topic normalization** - AI variations → 16 canonical topics (consistent search/alerts)
- **Processor modularization** - dramatic complexity reduction (-1,549 lines across refactors)
- **Prompts as JSON** - rapid iteration without code deployment
- **Cache-first** - instant API responses, decouples scraping from serving

### Patterns to Replicate
- Single unified method with optional parameters (`get_city()`)
- Extract shared logic to base class, keep subclasses thin
- Fail-fast with archived premium tiers for future revenue
- Hybrid architecture: Python for business logic, Rust for infrastructure (future)
- Structured logging with scannable tags (`[Cache]`, `[Vendor]`, `[Topic]`)
- Separate layers with clean interfaces (data layer → userland → integrations → tenancy)
- Backend stores data, frontend composes display (separation of concerns)

### Remaining Challenges
- **User accounts/auth** - Magic links? Email-only? Social auth?
- **Email infrastructure** - SendGrid vs self-hosted (cost/deliverability trade-offs)
- **PWA notifications** - Service worker setup, iOS support limitations
- **Frontend quick wins** - Participation info display, topic badges (backend ready)
- **Alert matching logic** - Topic-based subscriptions, frequency preferences
- **Scaling email alerts** - Batch processing for 1,000+ subscribers
- **Bluesky/ATProto** - Integration patterns for decentralized civic discourse

---

## The Path Forward

**Immediate (November 2025):**
1. ✅ Topic extraction complete (deploy to VPS)
2. Frontend participation info display (quick win, backend ready)
3. Frontend topic filtering/badges
4. Basic user profiles (email + city + topics)

**Near-term (Q1 2026):**
5. Email alert system (topic matching)
6. Weekly digest emails
7. PWA push notifications
8. Public read-only API documentation

**Medium-term (Q2 2026):**
9. Bluesky/ATProto integrations
10. B2B tenancy with webhooks
11. Remaining vendor item-level processing (CivicClerk, NovusAgenda, CivicPlus)

**Long-term (2026+):**
11. 1,000+ cities covered
12. Rust conductor migration

**Philosophy:** Move slow and heal things. Build trust through transparency. Design for civilians, not insiders. Open source the data layer, monetize the services on top.

---

**"The best time to plant a tree was 20 years ago. The second best time is now."**

Let's make local government accessible to everyone.
