# pipeline/workers/

Focused processing components. Decomposed from Processor god object.

## Classes

| Class | Purpose | Status |
|-------|---------|--------|
| `MeetingMetadataBuilder` | Participation + topic aggregation | Done |
| `DocumentExtractor` | PDF extraction and caching | Planned |
| `ItemBatchProcessor` | LLM batch assembly | Planned |
| `QueueProcessor` | Queue polling and dispatch | Planned |
| `MatterProcessor` | Matter-first deduplication | Planned |

## Pattern

Processor becomes thin orchestrator delegating to workers:

```python
class Processor:
    def __init__(self, db, analyzer):
        self.metadata_builder = MeetingMetadataBuilder(analyzer)
        # ... other workers
```

## Future

Full decomposition tracked in REFACTORING.md. Target: Processor under 150 lines.
