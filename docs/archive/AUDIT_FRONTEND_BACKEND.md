# Frontend-Backend Integration Audit

**Date**: 2025-10-30
**Auditor**: Claude
**Scope**: Full integration between FastAPI backend and SvelteKit frontend

---

## Executive Summary

Found **9 critical mismatches** between backend API contracts and frontend expectations. The frontend is doing significant compensatory work for backend inconsistencies. Root cause: Backend API evolved organically without strict schema contracts.

**Impact**: Type safety violations, runtime errors, unnecessary client-side data munging.

---

## Critical Issues

### 1. TYPE MISMATCH: Search Result `type` Field

**Severity**: HIGH
**Location**: `server/main.py` (multiple locations) vs `frontend/src/lib/api/types.ts:50`

**Backend returns**:
- `"type": "city_name"` (lines 525, 538, 686, 711, 724, 762)
- `"type": "state"` (lines 617, 667)
- `"type": "zipcode"` (lines 473, 486)

**Frontend expects**:
```typescript
type: 'city' | 'zipcode';  // line 50 of types.ts
```

**Fix**: Backend should return `"city"` not `"city_name"`, and frontend types should include `"state"`.

---

### 2. FIELD NAME MISMATCH: Meeting Status

**Severity**: HIGH
**Location**: `database/db.py:88` vs `frontend/src/lib/api/types.ts:20`

**Database schema**:
```python
status: Optional[str]  # cancelled, postponed, revised, rescheduled
```

**Frontend expects**:
```typescript
meeting_status?: 'cancelled' | 'postponed' | 'revised' | 'rescheduled' | 'deferred';
```

**Issues**:
- Backend field is `status`, frontend expects `meeting_status`
- Frontend has `'deferred'` option not in backend enum
- The `to_dict()` method returns `status`, not `meeting_status`

**Fix**: Backend `to_dict()` should map `status` → `meeting_status` for API responses.

---

### 3. FRONTEND COMPENSATES: Summary Cleaning

**Severity**: MEDIUM
**Location**: `frontend/src/routes/[city_url]/[meeting_slug]/+page.svelte:85-98`

**Evidence**:
```javascript
function cleanSummary(rawSummary: string): string {
    return rawSummary
        .replace(/=== DOCUMENT \d+ ===/g, '')
        .replace(/--- SECTION \d+ SUMMARY ---/g, '')
        .replace(/Here's a concise summary of the[^:]*:/gi, '')
        .replace(/Here's a summary of the[^:]*:/gi, '')
        .replace(/Here's the key points[^:]*:/gi, '')
        .replace(/Here's a structured analysis[^:]*:/gi, '')
        .replace(/Summary of the[^:]*:/gi, '')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
}
```

**Analysis**: Frontend is removing LLM artifacts and document headers that should never be in the stored summary.

**Root cause**: Backend summarization pipeline doesn't clean LLM output before storage.

**Fix**: Move this cleaning logic to backend `analysis/llm/summarizer.py` before storing summaries.

---

### 4. CONFIGURATION ERROR: Duplicate CORS Middleware

**Severity**: MEDIUM
**Location**: `server/main.py:27-37` and `server/main.py:96-102`

**Evidence**:
```python
# Line 27
app.add_middleware(CORSMiddleware, ...)

# Line 96 (duplicate!)
app.add_middleware(CORSMiddleware, ...)
```

**Impact**: Second registration overrides first, origins config is confusing.

**Fix**: Remove duplicate, use single CORS config from `config.ALLOWED_ORIGINS`.

---

### 5. SCHEMA INCOMPLETENESS: Missing Fields in Frontend Types

**Severity**: MEDIUM
**Location**: `frontend/src/lib/api/types.ts:14-21`

**Frontend Meeting type**:
```typescript
export interface Meeting {
    banana: string;
    title: string;
    date: string;
    packet_url?: string | string[];
    summary?: string;
    meeting_status?: 'cancelled' | 'postponed' | 'revised' | 'rescheduled' | 'deferred';
}
```

**Database Meeting has**:
- `id: str` ← Missing in frontend
- `participation: Dict` ← Missing in frontend
- `topics: List[str]` ← Missing in frontend
- `processing_status: str` ← Missing in frontend
- `processing_method: str` ← Missing in frontend
- `processing_time: float` ← Missing in frontend

**Analysis**: Frontend doesn't expose topics, participation info, or processing metadata.

**Fix**: Add these fields to frontend types (topics especially needed for Phase 1 topic features).

---

### 6. SEMANTIC CONFUSION: State Search Returns `success: false`

**Severity**: LOW
**Location**: `server/main.py:664`

**Evidence**:
```python
return {
    "success": False,  # False because we're not returning meetings directly
    "message": f"Found {len(city_options)} cities in {state_full}...",
    "type": "state",
    "ambiguous": True,
    "city_options": city_options,
}
```

**Analysis**: Query succeeded (found cities), but returns `success: False`. Confusing semantics.

**Better approach**: Use discriminated union with explicit `SearchStateResult` type.

**Fix**: Return `success: true` with `ambiguous: true` and `city_options`, or create separate result type.

---

### 7. INCONSISTENT USAGE: City URL Generation

**Severity**: LOW
**Location**: `frontend/src/routes/+page.svelte:93` vs `frontend/src/routes/+page.svelte:60`

**Evidence**:
```javascript
// Line 93: Direct banana usage
const cityUrl = banana; // banana is already in the right format

// Line 60: Generated from city name
const cityUrl = generateCityUrl(result.city_name, result.state);
```

**Analysis**:
- Sometimes frontend uses `banana` directly as city URL
- Sometimes frontend generates URL from `city_name` + `state`
- This works because `banana` IS the city URL format, but it's implicit knowledge

**Fix**: Backend should explicitly return `city_url` field (or document that `banana` is the URL).

---

### 8. DATA QUALITY: Random Meeting Field Name Mismatch

**Severity**: LOW
**Location**: `server/main.py:833-836`

**Evidence**:
```python
"title": random_meeting["meeting_name"],  # Source has "meeting_name"
"date": random_meeting["meeting_date"],   # Source has "meeting_date"
```

**Analysis**: `SummaryQualityChecker` returns `meeting_name`/`meeting_date` but API contract expects `title`/`date`. Backend does correct mapping, but shows schema inconsistency.

**Fix**: Make `SummaryQualityChecker` return canonical field names (`title`, `date`).

---

### 9. MISSING VALIDATION: Topics Field Not in Frontend Types

**Severity**: MEDIUM
**Location**: Backend uses topics extensively, frontend types don't include it

**Backend**:
- Database stores `topics: List[str]` on meetings and items
- API endpoint `/api/search/by-topic` returns results with topics
- API endpoint `/api/topics` returns all topics

**Frontend**:
- `Meeting` type has no `topics` field
- No UI for displaying/filtering by topics yet

**Fix**: Add `topics?: string[]` to frontend Meeting type, build topic UI.

---

## Shortcuts That Cause Headaches

### Backend Shortcuts:

1. **No OpenAPI schema validation** - API responses not validated against schema
2. **Inconsistent date formatting** - Mix of ISO strings and "YYYY-MM-DD HH:MM AM" format
3. **LLM artifacts in stored summaries** - Headers/preambles should be cleaned before DB storage
4. **Field name inconsistency** - `status` vs `meeting_status`, `meeting_name` vs `title`
5. **Ambiguous return types** - `success: false` for successful state queries
6. **Duplicate middleware registration** - CORS configured twice

### Frontend Shortcuts:

1. **Manual summary cleaning** - Compensating for backend LLM artifacts
2. **Date parsing hacks** - `dateString.split(' ')[0]` to handle inconsistent formats
3. **Incomplete type coverage** - Missing fields that backend returns
4. **Implicit banana=URL assumption** - No explicit documentation of this contract

---

## Recommendations

### Immediate Fixes (High Priority):

1. **Fix type field**: Change all `"type": "city_name"` to `"type": "city"` in backend
2. **Fix status field**: Map `status` → `meeting_status` in `Meeting.to_dict()`
3. **Remove duplicate CORS**: Keep single middleware registration
4. **Clean summaries in backend**: Move `cleanSummary()` logic to summarizer

### Phase 2 Improvements:

5. **Add OpenAPI/Pydantic response models** - Validate API responses at runtime
6. **Standardize date format** - Always ISO 8601 strings from backend
7. **Complete frontend types** - Add topics, participation, processing fields
8. **Explicit city_url field** - Don't rely on implicit banana=URL knowledge

### Phase 3 Enhancements:

9. **Generate TypeScript types from Python models** - Use tools like `datamodel-code-generator`
10. **API contract tests** - Validate backend responses match frontend expectations
11. **Discriminated unions for search results** - Type-safe handling of different result types

---

## Files Requiring Changes

### Backend:
- `server/main.py` - Fix type field, status field, remove duplicate CORS
- `database/db.py` - Update `Meeting.to_dict()` to map `status` → `meeting_status`
- `analysis/llm/summarizer.py` - Add summary cleaning before storage
- `scripts/summary_quality_checker.py` - Return canonical field names

### Frontend:
- `frontend/src/lib/api/types.ts` - Add missing fields, fix type union
- `frontend/src/routes/[city_url]/[meeting_slug]/+page.svelte` - Remove cleanSummary() after backend fix

---

**Confidence Level**: 9/10 - Comprehensive analysis backed by code review of all integration points.
