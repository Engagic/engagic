# Regional Processing Guide

## Overview

Process multiple cities at once for regional analysis and intelligence layer testing.

## Quick Start

```bash
# Test with 2 cities
./deploy.sh sync-and-process-cities @regions/test-small.txt

# Process entire Bay Area (12 cities)
./deploy.sh sync-and-process-cities @regions/bay-area.txt
```

## Workflow Options

### Option 1: All-in-One (Fast)

Sync and process immediately (no manual review):

```bash
./deploy.sh sync-and-process-cities @regions/bay-area.txt
```

### Option 2: Review Before Processing (Recommended)

1. **Sync** - Fetch meetings from vendor APIs, enqueue for processing:
```bash
./deploy.sh sync-cities @regions/bay-area.txt
```

2. **Preview Queue** - See what's queued:
```bash
./deploy.sh preview-queue
./deploy.sh preview-queue paloaltoCA  # Specific city
```

3. **Extract Text** - Manually review PDF extraction quality:
```bash
# Get meeting ID from queue preview
./deploy.sh extract-text MEETING_ID /tmp/preview.txt
cat /tmp/preview.txt | head -100  # Inspect first 100 lines
```

4. **Process** - Send to LLM for summarization (costs API credits):
```bash
./deploy.sh process-cities @regions/bay-area.txt
```

## Data Flow

```
Sync Cities
├─> Fetch meeting metadata from vendor APIs
├─> Store in meetings table (title, date, packet_url)
└─> Enqueue packet_url in queue table (status=pending)
        │
        ▼
Preview Queue (OPTIONAL - Manual Review)
├─> List queued jobs
└─> Extract text WITHOUT sending to LLM
        │
        ▼
Process Cities
├─> Pick job from queue
├─> Download PDF from packet_url
├─> Extract text (PyMuPDF)
├─> Send to Gemini LLM
├─> Store summary + topics
└─> Mark queue job as completed
```

## File Format for Region Lists

Create files in `regions/` directory:

```txt
# Bay Area Cities
paloaltoCA
mountainviewCA
oaklandCA
# Add more cities...
```

- One city banana per line
- Comments start with `#`
- Blank lines ignored

## Use Cases

### 1. Intelligence Layer Testing

Process multiple cities to build dataset for critical analysis:

```bash
./deploy.sh sync-and-process-cities @regions/bay-area.txt
```

### 2. Regional Comparison

Compare how different cities handle similar issues:

```bash
# Process region
./deploy.sh sync-and-process-cities @regions/bay-area.txt

# Then query via API
curl -X POST http://localhost:8000/api/search/by-topic \
  -H "Content-Type: application/json" \
  -d '{"topic": "Housing", "limit": 50}'
```

### 3. Demo Preparation

Quick test with 2 cities:

```bash
./deploy.sh sync-and-process-cities @regions/test-small.txt
```

### 4. Quality Assurance

Review text extraction before burning API credits:

```bash
# Sync only
./deploy.sh sync-cities paloaltoCA

# Extract and review
./deploy.sh extract-text MEETING_ID /tmp/check.txt
less /tmp/check.txt

# If looks good, process
./deploy.sh sync-and-process paloaltoCA
```

## Cost Estimation

**Per meeting processing cost:**
- Monolithic summary (PDF-only): ~$0.02
- Item-level processing (HTML agenda): ~$0.01 (batch API, 50% savings)

**Bay Area region (12 cities, ~50 meetings):**
- Sync only: Free
- Process all: ~$0.50 - $1.00

**Full platform (500 cities, ~10K meetings):**
- Sync only: Free
- Process all: ~$100 - $200

## Commands Reference

### Single City
```bash
./deploy.sh sync-city paloaltoCA
./deploy.sh sync-and-process paloaltoCA
```

### Multiple Cities (Comma-separated)
```bash
./deploy.sh sync-cities 'paloaltoCA,oaklandCA,berkeleyCA'
./deploy.sh process-cities 'paloaltoCA,oaklandCA,berkeleyCA'
```

### Multiple Cities (File)
```bash
./deploy.sh sync-cities @regions/bay-area.txt
./deploy.sh process-cities @regions/bay-area.txt
./deploy.sh sync-and-process-cities @regions/bay-area.txt
```

### Preview and Inspection
```bash
./deploy.sh preview-queue                    # All cities
./deploy.sh preview-queue paloaltoCA         # Specific city
./deploy.sh extract-text MEETING_ID          # Print to stdout
./deploy.sh extract-text MEETING_ID output.txt  # Save to file
```

## Intelligence Layer Integration

Once meetings are processed, you can run critical analysis:

```bash
# TODO: Intelligence layer commands (Phase 6)
# ./deploy.sh analyze-meetings @regions/bay-area.txt
# ./deploy.sh generate-narratives @regions/bay-area.txt
```

## Troubleshooting

**Queue is empty after sync:**
- Check if city has vendor configured
- Check sync logs: `journalctl -u engagic-daemon -f`

**Text extraction fails:**
- Some PDFs are malformed or scanned images
- Check error in queue: `./deploy.sh preview-queue`

**Processing stuck:**
- Check analyzer is available (needs LLM API key)
- Check daemon logs: `journalctl -u engagic-daemon -f`

**High API costs:**
- Use `extract-text` to preview before processing
- Start with `test-small.txt` (2 cities)
- Batch processing uses 50% less credits for item-level
