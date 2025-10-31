# Engagic Vision

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

### Infocore (Free OSS Data Layer)
**What:** Scraping, processing, storage - the source of truth
**Users:** Civic hackers, researchers, other civic tech projects
**Access:** Direct database, open source codebase
**Principle:** Public data should be freely accessible and machine-readable

Components:
- Vendor adapters (6 platforms, 94% success rate)
- PDF processing (PyMuPDF + Gemini)
- SQLite database (cities, meetings, agenda_items, job_queue)
- Priority queue (recent meetings first)
- Item-level processing (granular summaries per agenda item)

### Userland (Consumer Features)
**What:** Profiles, alerts, digests - built ON TOP of infocore
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

## Implementation (Current Architecture)

### Core Components
- **Vendor adapters** - 6 platforms with BaseAdapter pattern (Legistar, PrimeGov, Granicus, CivicClerk, NovusAgenda, CivicPlus)
- **Processing pipeline** - Item-level processing where possible, monolithic fallback for PDF-only
- **Cache-first architecture** - API never fetches live, background daemon syncs continuously
- **Priority queue** - Recent meetings processed first
- **SQLite database** - Single unified DB (cities, meetings, items, job_queue)
- **6 logical clusters** - vendors, parsing, analysis, pipeline, database, server

### Honest Assessment

**NOT user-friendly yet:**
- ❌ No user accounts
- ❌ No email notifications
- ❌ No profile/subscription system
- ❌ Users can't "follow" cities or topics

**Highly requested:**
- "Email me when my city discusses zoning"
- "Weekly digest of meetings in my city"
- "Alert me about housing issues"
- "Mobile notifications"

**Current users:** Civic hackers, researchers who can consume raw API data. Not accessible to average citizens.

---

## Roadmap (Growth Features)

### Phase 0: Quick Wins (Immediate Value)
**Goal:** Make participation easier with contact info

**Backend Implementation (DONE):**
- ✅ Parse email/phone/virtual_url/meeting_id from agenda text
- ✅ Store in `meetings.participation` JSON column
- ✅ Integrated into processing pipeline
- ✅ Normalized phone numbers, virtual URLs, hybrid meeting detection

**Frontend Requirements (TODO):**
- Display participation section prominently on meeting detail pages
- Clickable `mailto:city@council.gov` (opens email app)
- Clickable `tel:+1-555-0100` (mobile-friendly phone calls)
- Clickable Zoom/virtual URLs
- Badge for "Hybrid Meeting" or "Virtual Only"
- Pre-filled email with meeting context: `mailto:?subject=Re: [Meeting Title]&body=Dear Council...`
- No sending on user's behalf (liability), just make it easy to participate

**Why first:** Low-hanging fruit, high user value, enables civic action

### Phase 1: Topic Extraction (Foundation) - IMMEDIATE PRIORITY
**Goal:** Automatically tag meetings and agenda items with topics

**Implementation:**
- Per-item topic extraction using Gemini
- Aggregate topics at meeting level
- Database: `meeting_topics` table with standardized taxonomy
- Classification: "zoning", "affordable housing", "police budget", "transportation", etc.
- Store topics as JSON array on both items and meetings

**Why first:** The infrastructure breakthrough just happened (374+ cities, 58% coverage, 50-80M people). Without topic extraction, all this granular data is just well-organized text. Topics unlock search, alerts, and profiles - everything else depends on this.

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
- Infocore owns the data, others consume through APIs
- Protect the source of truth (no direct DB access for integrations)
- Layer features on top, don't couple them to core
- Each layer can scale independently

---

## Success Metrics

### Infocore (Data Quality)
- [x] Multi-vendor adapter system operational
- [x] Item-level processing working (majority of supported cities)
- [x] Contact info parsing (email/phone/virtual URLs)
- [ ] Topic extraction and normalization
- [ ] AI thinking traces exposed
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
- **BaseAdapter pattern** - compounds value with each new vendor
- **city_banana identifier** - vendor-agnostic, eliminates coupling
- **Priority queue** - improves user experience (recent meetings first)
- **Item-level processing** - better summaries, granular topics, enables batch API cost savings
- **HTML agenda parsing** - reusable pattern across vendors, enables item-level processing without clean APIs
- **Processor modularization** - dramatic reduction in complexity and maintainability improvement
- **Prompts as JSON** - rapid iteration without code deployment
- **Cache-first** - instant API responses, decouples scraping from serving

### Patterns to Replicate
- Single unified method with optional parameters (`get_city()`)
- Extract shared logic to base class, keep subclasses thin
- Fail-fast with archived premium tiers for future revenue
- Hybrid architecture: Python for business logic, Rust for infrastructure (future)
- Structured logging with scannable tags (`[Cache]`, `[Tier1]`, `[Memory]`)
- Separate layers with clean interfaces (infocore → userland → integrations → tenancy)

### Remaining Challenges
- User accounts/auth system (needed for profiles)
- Email infrastructure (SendGrid? Self-hosted?)
- PWA notifications (service worker complexity)
- Topic taxonomy (standardized vs. free-form?)
- Scaling email alerts (batch processing needed)
- Bluesky/ATProto integration patterns

---

## The Path Forward

**Immediate (Q4 2025):**
1. **Topic extraction per item and meeting** - CRITICAL PATH
2. Basic user profiles (email + city + topics)
3. Email alert system

**Near-term (Q1 2026):**
4. Weekly digest emails
5. PWA push notifications
6. Public read-only API
7. AI thinking traces (optional transparency feature)

**Medium-term (Q2 2026):**
8. Bluesky/ATProto integrations
9. B2B tenancy with webhooks
10. Remaining vendor item-level processing (CivicClerk, NovusAgenda, CivicPlus)

**Long-term (2026+):**
11. 1,000+ cities covered
12. Rust conductor migration

**Philosophy:** Move slow and heal things. Build trust through transparency. Design for civilians, not insiders. Open source the data layer, monetize the services on top.

---

**"The best time to plant a tree was 20 years ago. The second best time is now."**

Let's make local government accessible to everyone.
