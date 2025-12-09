# Technical Debt Register

Architectural opportunities identified but deferred. Review when modifying related code.

Last audit: 2025-12-08

---

## High Priority (Address When Touching)

### parsing/participation.py returns dicts, not models
- **File:** `parsing/participation.py`
- **Issue:** Returns `Dict[str, Any]` when `ParticipationInfo` already exists in `database/models.py`
- **Fix:** Import and return `ParticipationInfo` objects
- **Effort:** Low (wiring change)
- **Trigger:** Next time participation extraction is modified

### Server routes return raw dicts
- **Files:** `server/routes/engagement.py`, `server/routes/feedback.py`, `server/routes/matters.py`
- **Issue:** Endpoints return `{"success": True, ...}` dicts instead of Pydantic response models
- **Fix:** Add response models in `server/models/responses.py`, use in route return types
- **Effort:** Medium (5-10 new model classes)
- **Trigger:** Next API contract change or frontend type generation work

---

## Medium Priority (Note for Future)

### analysis/ lacks intermediate result types
- **Files:** `analysis/analyzer_async.py`, `analysis/topics/normalizer.py`
- **Issue:** Analysis pipeline passes dicts between stages; no `ExtractionResult`, `SummaryResult`, `TopicsResult` types
- **Fix:** Create typed result objects for pipeline stages
- **Effort:** Medium
- **Trigger:** When adding caching, retry logic, or new analysis stages

### Deliberation module domain modeling
- **Files:** `database/repositories_async/deliberation.py`, `scripts/moderate.py`
- **Issue:** New module, currently dict-heavy. No `Comment`, `Deliberation`, `ModerationDecision` domain objects with behavior
- **Fix:** Define domain types with methods (e.g., `PendingComment.approve()`)
- **Effort:** Medium
- **Trigger:** Before adding features like moderator notes, comment threading, or vote aggregation

### userland/matching returns dicts
- **Files:** `userland/matching/*.py`
- **Issue:** Matching logic returns raw dicts instead of `MatchResult` objects
- **Fix:** Create `MatchResult` type, return from matchers
- **Effort:** Low-Medium
- **Trigger:** When adding match explanation or debugging features

---

## Low Priority (Long-Term)

### parsing/pdf.py monolith (28K lines)
- **File:** `parsing/pdf.py`
- **Issue:** Single file handles extraction, OCR fallback, participation parsing, format detection. Changes require understanding the whole file.
- **Fix:** Split into `Document`, `Page`, `OCRProcessor`, `FeatureDetector` classes
- **Effort:** High (significant refactor)
- **Trigger:** When PDF extraction becomes a development bottleneck
- **Note:** Works fine currently; refactor only if modification friction becomes blocking

### Base adapter contains vendor-specific logic
- **File:** `vendors/adapters/base_adapter_async.py`
- **Issue:** SSL cert handling, header preferences live in base class rather than subclass overrides
- **Fix:** Move vendor-specific behavior to adapter subclasses
- **Effort:** Low-Medium
- **Trigger:** When adding new vendor that doesn't fit current patterns

---

## Future Architecture (Product Evolution)

### Governance model too council-centric
- **Tables:** `council_members`, `votes`, `committee_members`, `committees`
- **Issue:** Current model assumes council members are the key actors. But CA city-manager cities work differently:
  - Commissions (citizen appointees) make substantive recommendations
  - City Manager has real executive authority
  - Council ratifies (often ceremonially, unanimous consent)
- **Reality discovered:** Sunnyvale has 20+ commissions with 131 office records, but our model only captures 7 council members. Planning Commission, Arts Commission, etc. have voting members we ignore.
- **API limitation:** Many Legistar cities (Sunnyvale, San Jose) don't expose `/Votes` or `/EventItems` endpoints - vote data unavailable via API.

**What already exists:**
- `matter_appearances` tracks matter across meetings with `committee_id`, `action` (free text), `vote_outcome` (enum), `vote_tally` (jsonb)
- `committees` table with basic info
- `votes` table links individual votes to matter + meeting + council_member

**Proposed schema evolution:**

```sql
-- Generalize council_members
officials
├── id
├── city_id (banana)
├── name
├── role_type: enum('elected', 'appointed', 'staff')
├── position: text ("Council Member", "Commissioner", "City Manager", "Director")
└── term_start, term_end (nullable for staff)

-- Membership table for multi-body relationships
official_memberships
├── official_id
├── body_id
├── role: text ("Chair", "Vice Chair", "Member")
├── start_date, end_date

-- Generalize committees
bodies
├── id
├── city_id (banana)
├── name
├── body_type: enum('council', 'committee', 'commission', 'board', 'authority')
├── authority_level: enum('legislative', 'advisory', 'administrative', 'executive')
└── parent_body_id (nullable, for subcommittees)

-- Extend matter_appearances
matter_appearances (add columns)
├── action_type: enum('approval', 'recommendation', 'motion', 'consent', 'referral')
└── (migrate `action` free text to action_type enum)

-- votes unchanged, but council_member_id -> official_id
```

**Key insight:** `authority_level` distinguishes advisory (commissions recommend) from legislative (council approves). This enables tracking the governance flow:
```
Matter originates
    ↓
Commission reviews (authority_level='advisory')
    - action_type='recommendation'
    ↓
Council ratifies (authority_level='legislative')
    - action_type='approval' or 'consent'
```

**Migration path:**
1. Rename `committees` → `bodies`, add `body_type`, `authority_level`, `parent_body_id`
2. Rename `council_members` → `officials`, add `role_type`, `position`
3. Rename `committee_members` → `official_memberships`
4. Add `action_type` enum to `matter_appearances`
5. Update adapters to populate new fields
6. Update frontend to show governance flow

**Effort:** High (schema migration, adapter updates, frontend rework)
**Trigger:** When building features that need "who actually decided this" or commission-level tracking
**Note:** Core value for CA cities is summaries + matter tracking. Full governance model matters more for cities with real political dynamics. Prioritize accordingly.

---

## Architecture Strengths (Preserve These)

- **Repository pattern** in `database/` - clear separation, async pooling, typed models
- **Discriminated union jobs** in `pipeline/models.py` - type-safe job dispatch
- **Adapter pattern** in `vendors/` - clean interface, shared HTTP/rate-limit logic
- **Pydantic validation at boundaries** - `vendors/schemas.py`, `server/models/requests.py`
- **`city_banana` canonical identifier** - vendor-agnostic, well-documented

---

## Process

When you encounter friction modifying a module:
1. Check if it's listed here
2. If yes: consider whether now is the time to address it
3. If no: add it with context for future reference

Update "Last audit" date when reviewing this document.
