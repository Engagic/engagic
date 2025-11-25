# Asyncpg JSONB Handling - Critical Documentation

**Date**: 2025-11-23
**Updated**: 2025-11-25 (added Pydantic model support)
**Status**: AUTOMATIC CODEC WITH PYDANTIC SUPPORT

## The Migration

**We now use asyncpg's type codec for automatic JSONB serialization/deserialization.**

Previously, asyncpg required manual JSON string conversion. We've now configured automatic codec registration at connection pool initialization, eliminating all manual json.dumps()/json.loads() calls.

**November 2025 Update**: Extended encoder to handle Pydantic models automatically via `model_dump()`.

## Current Approach (Automatic Codec with Pydantic)

Connection pool is configured with JSONB codec that handles both native types AND Pydantic models:

```python
def _jsonb_encoder(obj):
    """JSONB encoder with automatic Pydantic model serialization."""
    def default(o):
        if hasattr(o, 'model_dump'):
            return o.model_dump()
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    return json.dumps(obj, default=default)


async def init_connection(conn):
    await conn.set_type_codec(
        'jsonb',
        encoder=_jsonb_encoder,  # Handles dicts AND Pydantic models
        decoder=json.loads,
        schema='pg_catalog'
    )

pool = await asyncpg.create_pool(
    dsn,
    init=init_connection,  # Registers codec on each connection
)
```

With this configuration:
- Python dicts/lists are automatically serialized to JSONB
- Pydantic models (ParticipationInfo, MatterMetadata, etc.) are automatically serialized via model_dump()

### Test Results

```python
import asyncpg
import json

conn = await asyncpg.connect(dsn)

# Create JSONB column
await conn.execute("CREATE TABLE test (data JSONB)")

# Test 1: Native Python dict
test_dict = {"foo": "bar", "num": 123}
await conn.execute("INSERT INTO test (data) VALUES ($1)", test_dict)
# ✗ ERROR: invalid input for query argument $1: {'foo': 'bar'} (expected str, got dict)

# Test 2: JSON string
test_json_string = json.dumps({"foo": "bar", "num": 123})
await conn.execute("INSERT INTO test (data) VALUES ($1)", test_json_string)
# ✓ SUCCESS!
```

## New Pattern (With Codec - November 2025)

### Storing JSONB Data

```python
# Native Python dicts/lists are automatically serialized
await conn.execute(
    "INSERT INTO table (jsonb_col) VALUES ($1)",
    data_dict  # No json.dumps() needed
)
```

### Retrieving JSONB Data

```python
# JSONB automatically deserialized to Python dicts/lists
row = await conn.fetchrow("SELECT jsonb_col FROM table")
data_dict = row["jsonb_col"]  # Already a Python dict/list
```

### Default Value Handling

```python
# Simple or operator for defaults
attachments = row["attachments"] or []
participation = row["participation"]  # Can be None
```

## Why This Matters

1. **psycopg2/psycopg3** auto-converts Python dicts → JSONB (many developers expect this)
2. **asyncpg does NOT** - requires explicit JSON string serialization
3. Error message is confusing: "expected str, got dict" (seems backwards)

## Repository Pattern

All repositories follow this pattern:

```python
class Repository:
    async def store_entity(self, entity):
        await conn.execute(
            "INSERT INTO table (jsonb_field) VALUES ($1)",
            json.dumps(entity.field) if entity.field else None  # Serialize
        )

    async def get_entity(self, id):
        row = await conn.fetchrow("SELECT jsonb_field FROM table WHERE id=$1", id)
        return Entity(
            field=safe_json_loads(row["jsonb_field"])  # Deserialize
        )
```

## Files Using JSONB

- `database/repositories_async/matters.py` - sponsors, canonical_topics, attachments, metadata
- `database/repositories_async/meetings.py` - participation
- `database/repositories_async/items.py` - attachments, sponsors, topics

All use `json.dumps()` on write, `safe_json_loads()` on read.

## Lessons Learned

1. **Don't assume** - different database drivers have different behaviors
2. **Test externalities** - verify assumptions about third-party libraries
3. **Read error messages carefully** - "expected str, got dict" was the correct message
4. **Document immediately** - this cost hours to discover, prevent future issues

## Migration Summary (November 2025)

### What Changed

**Before (Manual Serialization):**
- Required `json.dumps()` on every JSONB write (21 locations)
- Required `json.loads()` or `_deserialize_jsonb()` on every read (23 locations)
- Helper functions: `_deserialize_jsonb()` (32 lines), `safe_json_loads()` (6 lines)
- Total boilerplate: ~100 lines across 10 files

**After (Automatic Codec):**
- Added `init_connection()` function with codec registration (8 lines in db_postgres.py)
- Removed all manual json.dumps()/json.loads() calls
- Deleted helper functions entirely
- Net reduction: 37 lines of code

### Files Modified

1. **database/db_postgres.py** - Added codec registration
2. **database/repositories_async/base.py** - Deleted `_deserialize_jsonb()`
3. **database/repositories_async/items.py** - Removed 16 serialization calls
4. **database/repositories_async/meetings.py** - Removed 7 serialization calls
5. **database/repositories_async/matters.py** - Removed 13 serialization calls, deleted `safe_json_loads()`
6. **database/repositories_async/queue.py** - Removed 2 serialization calls
7. **database/repositories_async/search.py** - Removed 2 deserialization calls
8. **pipeline/models.py** - Removed defensive isinstance() check
9. **server/routes/matters.py** - Removed 5 json.loads() calls
10. **scripts/fix_jsonb_data.py** - Updated table names for PostgreSQL schema

### Benefits

- Cleaner, more Pythonic code (work with native dicts/lists)
- Reduced cognitive overhead (no manual serialization tracking)
- Fewer lines of code to maintain
- Better performance (codec handles serialization at C level)
- Eliminated error-prone manual serialization

## References

- asyncpg docs: https://magicstack.github.io/asyncpg/current/usage.html#type-conversion
- PostgreSQL JSONB: https://www.postgresql.org/docs/current/datatype-json.html
