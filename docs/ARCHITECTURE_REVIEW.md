# Architecture Review

**Date:** 2025-12-02
**Scope:** ~29,000 line Python backend
**Verdict:** Production-quality. Issues are incremental, not fundamental.

---

## What Works

1. **Module separation** - Clean boundaries: vendors/, parsing/, analysis/, pipeline/, database/, server/
2. **Matters-first deduplication** - Process legislative items once, reuse canonical summaries
3. **Two-pipeline architecture** - Item-level (58%) vs monolithic fallback (42%)
4. **Exception hierarchy** - `_retryable` property for smart retry logic
5. **Generator-based batch processing** - Incremental saves prevent crash data loss
6. **Document caching** - Same PDF extracted once per meeting

---

## High-Leverage Fixes

### 1. Adapter Result Types
**Priority:** HIGH
**Effort:** 3-4 days
**Problem:** Adapters return `[]` on failure - indistinguishable from "no meetings"

```python
# Current - information loss
async def fetch_meetings(self) -> List[Dict]:
    try:
        return await self._fetch()
    except Exception:
        return []  # Was it empty or did it fail?

# Fix - return result type with status
@dataclass
class FetchResult:
    meetings: List[MeetingSchema]
    status: Literal["success", "partial", "failed"]
    error: Optional[str] = None
```

**Files:** `vendors/schemas.py`, `vendors/adapters/*.py`, `pipeline/fetcher.py`

---

### 2. Single Topic Storage
**Priority:** HIGH
**Effort:** 1 week
**Problem:** Topics stored in BOTH JSONB column AND normalized tables

```sql
-- items table has:
topics TEXT,  -- JSONB array
-- AND:
CREATE TABLE item_topics (item_id, topic);  -- Normalized
```

**Fix:** Keep normalized tables only, deprecate JSONB columns
- Phase 1: Stop writing to JSONB
- Phase 2: Migrate reads to normalized tables
- Phase 3: Drop JSONB columns

**Files:** `database/repositories_async/items.py`, `meetings.py`, `matters.py`

---

### 3. Abstract Adapter Interface
**Priority:** MEDIUM
**Effort:** 2-3 days
**Problem:** No enforced contract - relies on runtime `NotImplementedError`

```python
from abc import ABC, abstractmethod

class AdapterProtocol(ABC):
    @abstractmethod
    async def fetch_meetings(self, days_back: int, days_forward: int) -> FetchResult:
        """Fetch meetings from vendor platform."""

    @property
    @abstractmethod
    def vendor_name(self) -> str:
        """Return vendor identifier."""
```

**Files:** `vendors/adapters/base_adapter_async.py`

---

### 4. Alembic Migrations
**Priority:** MEDIUM
**Effort:** 3-4 days
**Problem:** Manual SQL files in `/migrations/`, no version tracking

```bash
pip install alembic
alembic init alembic
alembic revision --autogenerate -m "Initial schema"
```

**Files:** New `alembic/` directory

---

### 5. Move Metrics to Shared Module
**Priority:** LOW
**Effort:** 1 hour
**Problem:** `vendors/adapters/base_adapter_async.py` imports `server.metrics` (upward dependency)

**Fix:** Create `shared/metrics.py`, move metrics there

**Files:** `shared/metrics.py` (new), `server/metrics.py`, `vendors/adapters/base_adapter_async.py`

---

## Bugs Fixed

### Race Condition on appearance_count
**Location:** `database/repositories_async/matters.py`
**Fixed:** 2025-12-02

```python
# Was: No atomicity guarantee
await conn.execute("UPDATE ... SET appearance_count = appearance_count + 1 ...")

# Fixed: Use RETURNING for atomic increment
new_count = await conn.fetchval(
    "UPDATE ... SET appearance_count = appearance_count + 1 ... RETURNING appearance_count",
    ...
)
```

---

## Deferred

- **Event-driven queue (Redis)** - Current DB polling works fine at scale
- **OpenTelemetry** - Current metrics sufficient
- **Config-driven adapters** - Custom code handles edge cases well
