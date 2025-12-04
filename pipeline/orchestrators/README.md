# pipeline/orchestrators/

Business logic extracted from Database. Workflow coordination across repositories.

## Classes

| Class | Purpose | Used By |
|-------|---------|---------|
| `MatterFilter` | Skip procedural matter types | `db._track_matters_async()` |
| `EnqueueDecider` | Queue priority + skip logic | `db._enqueue_if_needed_async()` |
| `VoteProcessor` | Tally votes, determine outcome | `db._track_matters_async()` |

## Pattern

Database delegates business decisions to orchestrators:

```python
# In database/db_postgres.py
matter_filter = MatterFilter()
if matter_filter.should_skip(matter_type):
    continue
```

## Future

`MeetingSyncOrchestrator` to move entire `store_meeting_from_sync()` workflow out of Database. See REFACTORING.md.
