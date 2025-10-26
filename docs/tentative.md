# Rust Conductor Implementation Plan

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ Python Layer (FastAPI/Orchestration)                        │
├─────────────────────────────────────────────────────────────┤
│ • API endpoints                                             │
│ • Google Drive authenticated downloads                      │
│ • Format detection and routing                              │
│ • Job scheduling and status tracking                        │
│ • Response formatting                                       │
└──────────────────┬──────────────────────────────────────────┘
                   │ PyO3 FFI
┌──────────────────▼──────────────────────────────────────────┐
│ Rust Conductor (Processing Engine)                          │
├─────────────────────────────────────────────────────────────┤
│ • Async document downloads (reqwest + tokio)                │
│ • Multi-format text extraction (PDF/DOCX)                   │
│ • Semantic chunking with token limits                       │
│ • Embedding generation (optional)                           │
│ • Concurrent batch processing                               │
│ • Database writes (sqlx or diesel)                          │
└─────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### Python Layer Responsibilities

**Keep:**
- FastAPI routing and validation
- Google Drive API integration (OAuth, permissions)
- Job queue management (Celery/RQ)
- API response formatting
- Authentication/authorization
- Error handling and user feedback

**Remove:**
- PDF text extraction (move to Rust)
- DOCX processing (move to Rust)
- Chunking logic (move to Rust)
- Heavy string manipulation

### Rust Conductor Responsibilities

**Core Functions:**
1. Document downloading (async, concurrent)
2. Format detection (magic bytes, content-type)
3. Text extraction (PDF via poppler, DOCX via docx-rust/pandoc)
4. Chunking (tiktoken-rs or semantic splitter)
5. Metadata extraction (titles, dates, page numbers)
6. Database persistence

**Interface:**
```python
# Python calls Rust via PyO3
from engagic_rust import Conductor

conductor = Conductor()
result = conductor.process_documents([
    {"url": "...", "type": "pdf", "source": "primegov"},
    {"url": "...", "type": "docx", "source": "google_drive"},
])
```

## Implementation Phases

### Phase 1: Foundation (Week 1)

**Dependencies:**
```toml
[dependencies]
pyo3 = { version = "0.22", features = ["extension-module"] }
tokio = { version = "1", features = ["full", "tracing"] }
reqwest = { version = "0.11", features = ["json", "rustls-tls"] }
poppler-rs = "0.23"
docx-rust = "0.4"
tiktoken-rs = "0.5"
thiserror = "1.0"
tracing = "0.1"
tracing-subscriber = "0.3"
```

**System Dependencies (Dockerfile):**
```dockerfile
RUN apt-get update && apt-get install -y \
    libpoppler-glib-dev \
    libglib2.0-dev \
    pkg-config \
    pandoc
```

**Tasks:**
1. Set up Rust library structure with PyO3
2. Create async runtime wrapper for Python interop
3. Implement basic downloader with retry logic
4. Add PDF extraction using poppler-rs
5. Write unit tests for each component

**Deliverable:** Python can call Rust to download and extract single PDF.

### Phase 2: Multi-Format Support (Week 2)

**Tasks:**
1. Add DOCX extraction (try docx-rust, fallback to pandoc shell)
2. Implement format detection via content-type + magic bytes
3. Add Google Docs URL handling (reject with error, handled by Python)
4. Create error types for each failure mode
5. Integration tests with real PrimeGov/Legistar PDFs

**Format Detection:**
```rust
pub enum DocumentFormat {
    Pdf,
    Docx,
    GoogleDrive,  // Error case, Python handles
    Unknown,
}

fn detect_format(bytes: &[u8], content_type: Option<&str>) -> DocumentFormat {
    // Magic bytes: PDF starts with %PDF, DOCX is ZIP with specific structure
    // Fallback to Content-Type header
}
```

**Deliverable:** Rust handles PDF and DOCX extraction reliably.

### Phase 3: Chunking Engine (Week 3)

**Requirements:**
- Respect token limits (configurable, default 512 tokens)
- Preserve semantic boundaries (paragraphs, sections)
- Include metadata (page numbers, section headers)
- Handle overlap (optional, for context)

**Implementation:**
```rust
pub struct ChunkConfig {
    pub max_tokens: usize,
    pub overlap_tokens: usize,
    pub respect_paragraphs: bool,
}

pub struct Chunk {
    pub text: String,
    pub tokens: usize,
    pub metadata: ChunkMetadata,
}

pub struct ChunkMetadata {
    pub page_start: Option<usize>,
    pub page_end: Option<usize>,
    pub section_header: Option<String>,
    pub chunk_index: usize,
}
```

**Library Options:**
1. tiktoken-rs (OpenAI tokenizer, exact token counting)
2. text-splitter (semantic chunking, markdown-aware)

**Recommendation:** Start with tiktoken-rs for compatibility with LLM APIs.

**Deliverable:** 600-page PDF chunks into semantically coherent units under token limit.

### Phase 4: Async Orchestration (Week 4)

**Tasks:**
1. Convert downloader to full async (remove blocking client)
2. Implement concurrent document processing
3. Add connection pooling (limit per domain)
4. Rate limiting (avoid overwhelming PrimeGov/Legistar)
5. Progress tracking and cancellation

**Async API:**
```rust
#[pyclass]
pub struct Conductor {
    runtime: tokio::runtime::Runtime,
}

#[pymethods]
impl Conductor {
    pub fn process_batch(&self, documents: Vec<DocumentRequest>) -> PyResult<BatchResult> {
        self.runtime.block_on(async {
            let results = stream::iter(documents)
                .map(|doc| self.process_one(doc))
                .buffer_unordered(5)  // Process 5 concurrent
                .collect::<Vec<_>>()
                .await;
            
            Ok(BatchResult { results })
        })
    }
}
```

**Rate Limiting:**
```rust
use governor::{Quota, RateLimiter};
use std::collections::HashMap;

// Per-domain rate limiting
struct DomainLimiters {
    limiters: HashMap<String, RateLimiter<...>>,
}
```

**Deliverable:** Process 5 agendas concurrently without overwhelming servers.

### Phase 5: Database Integration (Week 5)

**Options:**
1. **sqlx** (async, compile-time checked queries)
2. **diesel** (sync, mature ORM)
3. **Pass to Python** (simplest, keep DB logic in one place)

**Recommendation:** Option 3 initially. Return processed chunks to Python, let existing DB logic handle persistence. Optimize later if DB writes become bottleneck.

**Deliverable:** End-to-end pipeline from URL to chunked text in database.

### Phase 6: Production Hardening (Week 6)

**Tasks:**
1. Comprehensive error handling (network timeouts, corrupt PDFs, encoding issues)
2. Observability (tracing, metrics via Prometheus)
3. Memory profiling (600-page PDFs shouldn't OOM)
4. Benchmark suite (compare to PyMuPDF baseline)
5. Circuit breaker for failing adapters
6. Graceful degradation (fallback to Python if Rust fails)

**Error Handling Strategy:**
```rust
#[derive(Error, Debug)]
pub enum ProcessingError {
    #[error("Download failed: {0}")]
    Download(#[from] DownloadError),
    
    #[error("Extraction failed: {0}")]
    Extraction(String),
    
    #[error("Unsupported format: {0}")]
    UnsupportedFormat(String),
    
    #[error("Encoding error: {0}")]
    Encoding(String),
}
```

**Deliverable:** Production-ready conductor with <1% failure rate on known document types.

## Migration Strategy

### Step 1: Parallel Deployment
- Deploy Rust conductor alongside Python extraction
- Route 10% of traffic to Rust (feature flag)
- Monitor error rates, performance, memory usage
- Compare extraction quality (diff outputs)

### Step 2: Gradual Rollout
- Increase to 50% if error rate <1%
- Monitor for edge cases (complex formatting, scanned PDFs)
- Keep Python fallback active

### Step 3: Full Migration
- Route 100% to Rust after 2 weeks stable
- Keep Python extraction code for 1 month (safety net)
- Delete Python extraction after no fallbacks triggered

### Rollback Plan
- Feature flag to instantly revert to Python
- Rust failures automatically fallback to Python
- Log all Rust failures for analysis

## Testing Strategy

### Unit Tests
- Each format extractor independently
- Chunking with various token limits
- Rate limiting under load
- Error handling for corrupt files

### Integration Tests
- Real PDFs from each adapter (PrimeGov, Legistar, etc.)
- 600-page stress test
- Concurrent processing (5+ documents)
- Network failure simulation
- Google Drive URL rejection

### Performance Tests
- Baseline: PyMuPDF on 600-page PDF
- Target: 3x faster than Python
- Memory: <2GB for 600-page PDF
- Concurrency: 5 documents without blocking

### Quality Tests
- Text extraction accuracy (compare to Python output)
- Chunk boundary quality (no mid-sentence breaks)
- Metadata preservation (page numbers, sections)

## Known Issues and Mitigations

### Issue: Identity-H Encoding (PrimeGov PDFs)
**Mitigation:** poppler-rs handles this natively. Test with real PrimeGov sample.

### Issue: Complex DOCX Formatting
**Mitigation:** docx-rust handles basic formatting. For complex docs, shell out to pandoc.

### Issue: Google Drive Authentication
**Mitigation:** Python handles Drive API. Rust rejects Drive URLs with clear error.

### Issue: Memory Usage on Large PDFs
**Mitigation:** Stream processing where possible. Profile with valgrind/heaptrack.

### Issue: PyO3 GIL Contention
**Mitigation:** Release GIL during expensive operations:
```rust
py.allow_threads(|| {
    // Long-running Rust work here
})
```

## Success Metrics

**Performance:**
- 3-5x faster than Python on 600-page PDFs
- Process 5 documents concurrently without timeout
- <2GB memory footprint per document

**Reliability:**
- <1% failure rate on known document types
- 100% of failures have actionable error messages
- Zero production outages during migration

**Quality:**
- 99.9% text extraction accuracy vs Python baseline
- No chunk boundary regressions
- All metadata preserved

## Timeline Summary

- **Week 1:** Foundation (single PDF extraction working)
- **Week 2:** Multi-format support (PDF + DOCX)
- **Week 3:** Chunking engine (semantic, token-aware)
- **Week 4:** Async orchestration (concurrent processing)
- **Week 5:** Database integration (end-to-end pipeline)
- **Week 6:** Production hardening (observability, error handling)

**Total: 6 weeks to production-ready conductor.**

## Open Questions

1. Embedding generation in Rust or Python? (Depends on model: OpenAI API stays Python, local model could be Rust)
2. Cache layer for repeated downloads? (Redis in Python or in-memory Rust?)
3. OCR fallback for scanned PDFs? (tesseract via shell, or skip)
4. Webhook notifications for job completion? (Python, not Rust concern)

## Next Actions

1. Create new Cargo workspace: `infra/conductor/`
2. Set up PyO3 bindings and basic Python import
3. Implement Phase 1 deliverable (single PDF extraction)
4. Run benchmark against PyMuPDF baseline
5. Review extracted text quality on PrimeGov sample