# Regional Processing Commands - Summary

## What Was Added

### 1. Multi-City Processing Methods (`pipeline/conductor.py`)

**New methods:**
- `sync_cities(city_bananas: List[str])` - Sync multiple cities (fetch + enqueue)
- `process_cities(city_bananas: List[str])` - Process queued jobs for multiple cities
- `sync_and_process_cities(city_bananas: List[str])` - Sync + process multiple cities
- `preview_queue(city_banana: Optional[str])` - Preview queued jobs without processing
- `extract_text_preview(meeting_id: str, output_file: Optional[str])` - Extract PDF text for manual review

**CLI arguments added:**
- `--sync-cities CITIES` - Supports comma-separated or @file
- `--process-cities CITIES` - Supports comma-separated or @file
- `--sync-and-process-cities CITIES` - Supports comma-separated or @file
- `--preview-queue [CITY]` - Show queued jobs
- `--extract-text MEETING_ID` - Extract text without processing
- `--output-file FILE` - Save extracted text to file

### 2. Deploy Script Commands (`deploy.sh`)

**New commands:**
```bash
# Multiple cities
./deploy.sh sync-cities 'paloaltoCA,oaklandCA'
./deploy.sh sync-cities @regions/bay-area.txt
./deploy.sh process-cities @regions/bay-area.txt
./deploy.sh sync-and-process-cities @regions/bay-area.txt

# Preview and inspection
./deploy.sh preview-queue
./deploy.sh preview-queue paloaltoCA
./deploy.sh extract-text MEETING_ID
./deploy.sh extract-text MEETING_ID /tmp/output.txt
```

### 3. Regional City Lists (`regions/`)

**Files created:**
- `regions/bay-area.txt` - 12 Bay Area cities
- `regions/test-small.txt` - 2 cities for quick testing
- `regions/README.md` - Documentation for region files

**File format:**
```txt
# Comments start with #
paloaltoCA
oaklandCA
berkeleyCA
```

### 4. Documentation

**New docs:**
- `docs/REGIONAL_PROCESSING.md` - Complete workflow guide
- `REGIONAL_COMMANDS_SUMMARY.md` - This file

**Updated docs:**
- `CLAUDE.md` - Updated to reflect Phase 5 modularization

## Workflows

### Quick Test (2 cities)
```bash
./deploy.sh sync-and-process-cities @regions/test-small.txt
```

### Regional Analysis (12 cities)
```bash
# Option 1: All-in-one (fast)
./deploy.sh sync-and-process-cities @regions/bay-area.txt

# Option 2: Review before processing (recommended)
./deploy.sh sync-cities @regions/bay-area.txt      # 1. Fetch + enqueue
./deploy.sh preview-queue                          # 2. See what's queued
./deploy.sh extract-text MEETING_ID /tmp/check.txt # 3. Review extraction quality
./deploy.sh process-cities @regions/bay-area.txt   # 4. Send to LLM
```

### Single City (existing commands still work)
```bash
./deploy.sh sync-city paloaltoCA
./deploy.sh sync-and-process paloaltoCA
```

## Data Flow

```
┌─────────────────────────────────────────────────────┐
│ sync-cities @regions/bay-area.txt                   │
└───────────────────┬─────────────────────────────────┘
                    │
    ┌───────────────▼────────────────┐
    │ Fetcher: sync_cities()         │
    │ - Loop through city list       │
    │ - Call vendor adapters         │
    │ - Store meetings in DB         │
    │ - Enqueue source_url (pending) │
    └───────────────┬────────────────┘
                    │
    ┌───────────────▼────────────────┐
    │ Queue Table                    │
    │ - id, packet_url, meeting_id   │
    │ - status: pending              │
    │ - priority (by date)           │
    └───────────────┬────────────────┘
                    │
    ┌───────────────▼────────────────┐
    │ preview-queue (OPTIONAL)       │
    │ - List queued jobs             │
    │ - extract-text MEETING_ID      │
    │   (downloads PDF, extracts     │
    │    text, NO LLM call)          │
    └───────────────┬────────────────┘
                    │
    ┌───────────────▼────────────────┐
    │ process-cities @regions/...    │
    │ - Processor: process_cities()  │
    │ - Loop through queue           │
    │ - Download PDF                 │
    │ - Extract text (PyMuPDF)       │
    │ - Send to Gemini LLM           │
    │ - Store summary + topics       │
    │ - Mark queue job: completed    │
    └────────────────────────────────┘
```

## Cost Estimates

| Operation | Cost | Notes |
|-----------|------|-------|
| `sync-cities` | Free | Just fetches metadata |
| `extract-text` | Free | Downloads PDF, no LLM |
| `process-cities` (2 cities) | ~$0.02-0.04 | Test set |
| `process-cities` (12 cities, ~50 meetings) | ~$0.50-1.00 | Bay Area |
| `process-cities` (500 cities, ~10K meetings) | ~$100-200 | Full platform |

## Intelligence Layer Preparation

These regional commands set up the foundation for Phase 6 (Intelligence Layer):

1. **Sync regions** → Build base summaries
2. **Manual review** → Ensure quality
3. **Intelligence analysis** → Critical narratives (future)

```bash
# Phase 6 workflow (future)
./deploy.sh sync-and-process-cities @regions/bay-area.txt  # Basic summaries
./deploy.sh analyze-meetings @regions/bay-area.txt         # Critical analysis (TODO)
./deploy.sh generate-narratives @regions/bay-area.txt      # 4-line narratives (TODO)
```

## Files Changed

1. `pipeline/conductor.py` - Added multi-city methods, preview/extract methods, CLI args
2. `deploy.sh` - Added wrapper functions and help text
3. `regions/` - Created directory with city lists
4. `docs/REGIONAL_PROCESSING.md` - Complete workflow guide
5. `CLAUDE.md` - Updated to reflect Phase 5 completion

## Testing

```bash
# Verify commands exist
uv run engagic-conductor --help

# Quick test (no API costs)
./deploy.sh sync-cities @regions/test-small.txt
./deploy.sh preview-queue

# Full test (costs ~$0.02)
./deploy.sh sync-and-process-cities @regions/test-small.txt
```

## Next Steps

1. Test regional processing with `@regions/test-small.txt`
2. Review extracted text quality with `extract-text`
3. Process Bay Area region for intelligence layer dataset
4. Build Phase 6: Intelligence Layer (researcher + judge agents)
