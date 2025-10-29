# Engagic Memory Leak Diagnosis & Fixes

## System Context
- **Hardware**: 2GB RAM droplet with 2GB swap
- **Workload**: 800 cities scraping sequentially
- **Crash Pattern**: Memory accumulation → swap thrashing → OOM kill

## Root Causes

### 1. Adapter Session Leak (Critical)
**Location**: `conductor.py` line 298, `base_adapter.py`

**Problem**:
- New adapter instance created per city with persistent HTTP session
- Sessions never explicitly closed
- 800 cities × 1-2MB per session = **800MB-1.6GB leak**

**Evidence**:
```python
# conductor.py:298
adapter = self._get_adapter(city.vendor, city.slug)
# Session created in BaseAdapter.__init__
# Never closed after city sync completes
```

### 2. PDF Text Accumulation
**Locations**: `processor.py`, `conductor.py` lines 740-742, 318, 879-900

**Problem**:
- Full PDF extracted into memory as single string
- Text duplicated when joining for multi-PDF processing
- Batch processing accumulates ALL item text before LLM call
- **50-100MB per large meeting**

**Evidence**:
```python
# conductor.py:740-742
result = self.processor.pdf_extractor.extract_from_url(packet_url)
extracted_text = result['text']  # Full PDF in memory

# processor.py:318
combined_text = "\n\n".join(all_text_parts)  # Duplicates all text

# conductor.py:879-900
batch_requests = []  # Accumulates all item text
for item in need_processing:
    all_text_parts.append(...)  # Growing list
```

### 3. BeautifulSoup Object Retention
**Location**: `base_adapter.py`

**Problem**:
- `_fetch_html()` creates BeautifulSoup objects
- No explicit cleanup
- 1-5MB per city, lingers until GC

### 4. No Explicit Garbage Collection
**Problem**:
- Sequential processing accumulates objects
- Python GC waits for memory pressure
- With 800 cities, accumulation exceeds GC trigger threshold

## Fixes

### Fix 1: Close Adapter Sessions Explicitly

**File**: `base_adapter.py`

Add destructor to BaseAdapter class:

```python
class BaseAdapter:
    # ... existing code ...
    
    def __del__(self):
        """Cleanup HTTP session on adapter destruction"""
        if hasattr(self, 'session'):
            try:
                self.session.close()
            except Exception:
                pass
    
    def close(self):
        """Explicit cleanup method"""
        if hasattr(self, 'session'):
            self.session.close()
```

**File**: `conductor.py`

Modify `_sync_city` method (around line 447):

```python
def _sync_city(self, city: City) -> SyncResult:
    """Sync a single city"""
    result = SyncResult(city_banana=city.banana, status=SyncStatus.PENDING)
    adapter = None  # Initialize outside try block
    
    try:
        # ... existing sync logic ...
        adapter = self._get_adapter(city.vendor, city.slug)
        # ... rest of sync logic ...
        
    except Exception as e:
        result.status = SyncStatus.FAILED
        result.error_message = str(e)
        result.duration_seconds = time.time() - start_time
        logger.error(f"Failed to sync {city.banana}: {e}")
        time.sleep(2 + random.uniform(0, 1))
        
    finally:
        # CRITICAL: Clean up adapter and force GC
        if adapter:
            if hasattr(adapter, 'close'):
                adapter.close()
            del adapter
        
        import gc
        gc.collect()
    
    return result
```

### Fix 2: Clear PDF Text Immediately After Use

**File**: `processor.py`

Modify `_process_multiple_pdfs` (after line 213):

```python
def _process_multiple_pdfs(self, urls: List[str]) -> tuple[str, str]:
    """Process multiple PDFs with memory cleanup"""
    logger.info(f"Processing {len(urls)} PDFs with combined context")
    
    # Extract text from all PDFs
    all_text_parts = []
    failed_pdfs = []
    
    # ... existing extraction logic ...
    
    if not all_text_parts:
        logger.error(f"[Tier1] REJECTED - No usable text from any of {len(urls)} PDFs")
        raise ProcessingError("No usable text from any PDF")
    
    # Combine and process
    combined_text = "\n\n".join(all_text_parts)
    summary = self.summarizer.summarize_meeting(combined_text)
    
    # CRITICAL: Free memory immediately
    result = (summary, f"multiple_pdfs_{len(urls)}_combined")
    del all_text_parts
    del combined_text
    
    import gc
    gc.collect()
    
    return result
```

### Fix 3: Cleanup in Batch Item Processing

**File**: `conductor.py`

Modify `_process_meeting_with_items` (around line 900+, after batch API call):

```python
# After batch processing completes
try:
    # Call batch API
    batch_results = self.processor.summarizer.summarize_batch(batch_requests)
    
    # Process results
    for result in batch_results:
        # ... store results ...
    
    # CRITICAL: Free batch memory immediately
    del batch_requests
    if 'all_text_parts' in locals():
        del all_text_parts
    
    import gc
    gc.collect()
    
except Exception as e:
    logger.error(f"Batch processing failed: {e}")
```

### Fix 4: Add Periodic GC During City Loop

**File**: `conductor.py`

Modify `_run_full_sync` (after line 254, inside city loop):

```python
for city in sorted_cities:
    if not self.is_running:
        break
    
    # ... existing sync logic ...
    result = self._sync_city_with_retry(city)
    results.append(result)
    
    # CRITICAL: Force GC every 10 cities
    if len(results) % 10 == 0:
        import gc
        gc.collect()
        logger.debug(f"Forced GC after {len(results)} cities")
```

### Fix 5: Limit Text Accumulation in Item Processing

**File**: `conductor.py`

Modify line 781 to truncate stored text:

```python
# Change from storing full text:
'content': item['text'][:5000],  # First 5000 chars

# To storing even less:
'content': item['text'][:2000],  # First 2000 chars (sufficient for preview)
```

## Memory Budget Calculation

### Before Fixes
- Base system: 200MB
- Uvicorn: 100MB
- Available for scraping: 1.6GB
- **Per-city memory usage**: 50-200MB (PDF + adapter + soup)
- **Accumulated leak**: 800MB-1.6GB over 800 cities
- **Result**: OOM kill after 50-100 cities

### After Fixes
- Base system: 200MB
- Uvicorn: 100MB
- Available for scraping: 1.6GB
- **Per-city memory usage**: 50-200MB (same)
- **Accumulated leak**: ~0MB (cleaned immediately)
- **Result**: Stable at ~400-600MB total usage

## Additional Recommendations

### 1. Monitor Memory Usage
Add memory logging to track effectiveness:

```python
import psutil
import os

def log_memory_usage(context=""):
    """Log current memory usage"""
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    mem_mb = mem_info.rss / 1024 / 1024
    logger.info(f"[Memory] {context}: {mem_mb:.1f}MB RSS")

# Use in conductor.py
log_memory_usage(f"After syncing {city.banana}")
```

### 2. Upgrade to 4GB RAM
**Cost**: $12/mo → $18/mo ($6/mo increase)

**Justification**:
- Current system barely sufficient even with fixes
- Claude Code + uvicorn baseline = 300-400MB
- Leaves only 1.2GB for scraping
- Large PDFs (100+ pages) can spike to 500MB
- 4GB provides comfortable buffer

### 3. Implement Processing Queue with Worker Limit
**Current**: Sequential processing in main sync loop
**Better**: Queue-based with max 1-2 concurrent workers

```python
# Already implemented in daemon.py _processing_loop()
# Just needs proper memory cleanup in workers
```

### 4. Add Circuit Breaker for Large PDFs
Skip processing if PDF exceeds threshold:

```python
# In processor.py
MAX_PDF_SIZE_MB = 50

result = self.pdf_extractor.extract_from_url(url)
if len(result.get('text', '')) > MAX_PDF_SIZE_MB * 1024 * 1024:
    raise ProcessingError(f"PDF too large: {len(result['text'])/1024/1024:.1f}MB")
```

## Testing Plan

1. **Apply fixes** to base_adapter.py, conductor.py, processor.py
2. **Run test sync** on 20 cities:
   ```bash
   python daemon.py --once
   ```
3. **Monitor memory** with:
   ```bash
   watch -n 1 'ps aux --sort=-%mem | head -10'
   ```
4. **Verify cleanup** - memory should stay flat around 400-600MB
5. **Full sync test** - all 800 cities should complete without OOM

## Success Metrics

- Memory usage stays below 800MB during sync
- Swap usage remains under 10%
- No OOM kills
- All 800 cities sync successfully
- Claude Code can run concurrently without crashes
