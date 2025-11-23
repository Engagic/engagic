# Asyncpg JSONB Handling - Critical Documentation

**Date**: 2025-11-23
**Issue**: Misunderstanding of asyncpg JSONB behavior
**Impact**: Broke PostgreSQL migration, spent hours debugging

## The Discovery

**Asyncpg requires JSON STRINGS for JSONB columns, NOT native Python dicts/lists.**

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

## Correct Pattern

### Storing JSONB Data

```python
import json

# Always serialize to JSON string before passing to asyncpg
await conn.execute(
    "INSERT INTO table (jsonb_col) VALUES ($1)",
    json.dumps(data_dict) if data_dict else None
)
```

### Retrieving JSONB Data

```python
# Asyncpg returns JSONB as JSON strings, must deserialize
row = await conn.fetchrow("SELECT jsonb_col FROM table")
data_dict = json.loads(row["jsonb_col"]) if row["jsonb_col"] else None
```

### Safe Deserialization Helper

```python
def safe_json_loads(value):
    """Handle JSONB fields that might be None or already deserialized"""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value  # Already deserialized
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

## References

- asyncpg docs: https://magicstack.github.io/asyncpg/current/usage.html#type-conversion
- PostgreSQL JSONB: https://www.postgresql.org/docs/current/datatype-json.html
