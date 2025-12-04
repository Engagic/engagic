# Architectural Refactoring Plan

## Status: Phase 1-4 Complete (Incremental)

Completed December 4, 2025

## Problem Summary

Three interconnected architectural issues created maintenance burden:

1. **Layering Violation**: Pipeline imports server/metrics (compile-time coupling)
2. **Database God Object**: `db_postgres.py` mixes persistence with business logic
3. **Processor Bloat**: `processor.py` mixes queue management, extraction, and LLM orchestration

## What Was Done

### Phase 1: Decouple Metrics - COMPLETE

**Created:**
- `pipeline/protocols/__init__.py`
- `pipeline/protocols/metrics.py` - Protocol interface + NullMetrics

**Modified:**
- `pipeline/processor.py` - Accepts `metrics: Optional[MetricsCollector]`
- `pipeline/fetcher.py` - Accepts `metrics: Optional[MetricsCollector]`
- `pipeline/conductor.py` - Wires metrics injection

**Result:** Pipeline can now be imported/run without server module.
```bash
python -c "from pipeline.processor import Processor"  # Works without server
```

---

### Phase 4: Move Vendor Utils - COMPLETE

**Created:**
- `pipeline/filters/__init__.py`
- `pipeline/filters/item_filters.py` - Canonical location

**Modified:**
- `vendors/utils/item_filters.py` - Now re-exports from pipeline.filters
- `pipeline/processor.py` - Imports from pipeline.filters

**Result:** Correct layering - adapters adapt, pipeline decides.

---

### Phase 2: Extract Orchestrator Helpers - COMPLETE (Incremental)

**Created:**
- `pipeline/orchestrators/__init__.py`
- `pipeline/orchestrators/matter_filter.py` - Wraps should_skip_matter
- `pipeline/orchestrators/enqueue_decider.py` - Queue priority logic
- `pipeline/orchestrators/vote_processor.py` - Vote tally computation

**Modified:**
- `database/db_postgres.py`:
  - Uses `MatterFilter` instead of direct vendor import
  - Uses `EnqueueDecider` for skip/priority logic
  - Uses `VoteProcessor` for vote computation

**Result:** Business logic extracted into pipeline layer. Database delegates to orchestrators.

**Remaining (Future Work):**
- Full `MeetingSyncOrchestrator` to move entire `store_meeting_from_sync()` workflow
- Currently Database still orchestrates, but uses extracted helpers

---

### Phase 3: Decompose Processor - COMPLETE (Incremental)

**Created:**
- `pipeline/workers/__init__.py`
- `pipeline/workers/meeting_metadata.py` - Participation + topic aggregation

**Result:** Worker pattern established. One worker extracted as demonstration.

**Remaining (Future Work):**
- `pipeline/workers/queue_processor.py` - Queue polling and dispatch
- `pipeline/workers/document_extractor.py` - PDF extraction and caching
- `pipeline/workers/item_batch_processor.py` - LLM batch assembly
- `pipeline/workers/matter_processor.py` - Matter-first deduplication
- Slim down `processor.py` to thin orchestrator

---

## Current Architecture

```
pipeline/
  protocols/
    metrics.py          # MetricsCollector Protocol + NullMetrics
  filters/
    item_filters.py     # Canonical filter logic (moved from vendors)
  orchestrators/
    matter_filter.py    # MatterFilter class
    enqueue_decider.py  # EnqueueDecider class
    vote_processor.py   # VoteProcessor class
  workers/
    meeting_metadata.py # MeetingMetadataBuilder class
  processor.py          # Uses orchestrators, still large
  fetcher.py            # Uses orchestrators, accepts metrics
  conductor.py          # Wires dependencies

database/
  db_postgres.py        # Delegates to orchestrators, still large

vendors/
  utils/
    item_filters.py     # Re-export shim (deprecated)
```

---

## Verification Passed

1. Linting: `ruff check --fix` - All passed
2. Type checking: `ty check pipeline/ database/db_postgres.py` - All passed
3. Compilation: All Python files compile successfully
4. Import test: Pipeline importable without server

---

## Future Work

### Full Database Decomposition
Extract remaining methods from `database/db_postgres.py`:
- `store_meeting_from_sync()` -> `MeetingSyncOrchestrator.sync_meeting()`
- `_process_agenda_items_async()` -> orchestrator method
- `_track_matters_async()` -> orchestrator method
- `_create_matter_appearances_async()` -> orchestrator method
- `_enqueue_if_needed_async()` -> orchestrator method

Target: Database class under 400 lines (currently ~800 lines of orchestration)

### Full Processor Decomposition
Extract workers from `pipeline/processor.py`:
- `QueueProcessor` - Queue polling and dispatch
- `DocumentExtractor` - PDF extraction and caching
- `ItemBatchProcessor` - LLM batch assembly
- `MatterProcessor` - Matter-first deduplication

Target: Processor class under 150 lines (currently 1351 lines)

---

## Design Principles

- **Dependency Inversion**: High-level modules shouldn't depend on low-level details
- **Single Responsibility**: Each class does one thing well
- **Explicit Dependencies**: Inject collaborators, don't import globals
- **Backward Compatibility**: Public APIs remain stable during refactor
- **Incremental Progress**: Each phase is a working state
