# Analysis Module - LLM Intelligence & Topic Extraction

**Transform raw meeting documents into actionable civic intelligence.** Async orchestration, Gemini API integration, adaptive prompting, topic normalization.

**Last Updated:** December 4, 2025

---

## Overview

The analysis module provides LLM-powered intelligence for civic meeting documents. Orchestrates Google's Gemini API to generate summaries, extract topics, and assess citizen impact from agenda items and meeting packets.

**Core Capabilities:**
- **Async orchestration:** Concurrent PDF downloads, non-blocking extraction
- **Reactive rate limiting:** Respects Gemini's `retryDelay` on 429 errors with exponential backoff
- **Adaptive summarization:** Item-level (1-5 sentences) vs comprehensive (5-10 sentences) based on document size
- **Topic extraction:** 16 canonical civic topics (housing, zoning, transportation, etc.)
- **Citizen impact assessment:** "Why should residents care?" analysis
- **Batch processing:** 50% cost savings via Gemini Batch API
- **JSON structured output:** Schema-validated responses (no parsing failures)

**Architecture Pattern:** AsyncAnalyzer (orchestration) → GeminiSummarizer (LLM + rate limiting) → TopicNormalizer (mapping)

```
analysis/
├── analyzer_async.py       # 343 lines - Async orchestration
├── llm/
│   ├── summarizer.py       # 1,203 lines - Gemini API + reactive rate limiting
│   └── prompts_v2.json     # 149 lines - Prompt templates
└── topics/
    ├── normalizer.py       # 230 lines - Topic normalization
    └── taxonomy.json       # 242 lines - 16 canonical topics

**Total:** 1,776 lines Python + 391 lines JSON = 2,167 lines
```

---

## Architecture

### AsyncAnalyzer (analysis/analyzer_async.py)

**Main orchestration layer** - coordinates async PDF downloads and LLM calls. Rate limiting is handled reactively by the summarizer.

```python
class AsyncAnalyzer:
    """
    Async LLM analysis orchestrator.

    Key Features:
    - Async PDF downloads (aiohttp, concurrent)
    - CPU-bound extraction in thread pool (non-blocking)
    - Concurrent batch processing

    Rate limiting handled reactively by summarizer via Gemini's retry instructions.
    """

    def __init__(self, api_key: Optional[str] = None, metrics: Optional[MetricsCollector] = None):
        self.metrics = metrics or NullMetrics()
        self.pdf_extractor = PdfExtractor()  # Sync extractor, wrap in asyncio.to_thread()
        self.summarizer = GeminiSummarizer(api_key=api_key, metrics=self.metrics)
        self.http_session: Optional[aiohttp.ClientSession] = None
```

**Key Methods:**

```python
async def download_pdf_async(url: str) -> bytes:
    """Download PDF asynchronously with aiohttp"""

async def extract_pdf_async(url: str) -> Dict[str, Any]:
    """
    Extract text from PDF asynchronously.
    Downloads with async HTTP, extracts in thread pool (CPU-bound).
    Returns: {success, text, page_count, ...}
    """

async def process_agenda_async(url: str) -> Tuple[str, str, Optional[Dict]]:
    """
    Process agenda using PyMuPDF + Gemini (fail-fast approach).
    Returns: (summary, method_used, participation_info)
    """

async def process_batch_items_async(
    item_requests: List[Dict[str, Any]],
    shared_context: Optional[str] = None,
    meeting_id: Optional[str] = None
) -> List[List[Dict[str, Any]]]:
    """
    Process multiple agenda items sequentially (to avoid TPM rate limits).
    Returns: [[{item_id, success, summary, topics, error?}, ...]]
    """
```

**Why async?**
- **I/O parallelism:** Download PDFs concurrently instead of sequentially
- **Non-blocking:** Event loop continues while waiting on HTTP/API responses
- **Resource efficiency:** Thread pool for CPU-bound work (PyMuPDF), async for I/O

**Usage:**
```python
analyzer = AsyncAnalyzer()
results = await analyzer.process_batch_items_async(items)
await analyzer.close()  # Cleanup HTTP session
```

---

### GeminiSummarizer (analysis/llm/summarizer.py)

**Gemini API orchestration** with model selection, adaptive prompting, reactive rate limiting, and batch processing.

```python
class GeminiSummarizer:
    """Smart LLM orchestrator - picks model, picks prompt, formats response"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        prompts_path: Optional[str] = None,
        metrics: Optional[MetricsCollector] = None
    ):
        self.metrics = metrics or NullMetrics()
        self.client = genai.Client(api_key=api_key)
        self.flash_model_name = "gemini-2.5-flash"
        self.flash_lite_model_name = "gemini-2.5-flash-lite"

        # Load prompts from JSON (v2 only)
        self.prompts = json.load(open(prompts_path or "analysis/llm/prompts_v2.json"))
```

**Reactive Rate Limiting:**

Instead of proactive token bucket limiting, we trust Gemini to tell us when to retry. The `_call_with_retry()` method parses `retryDelay` from 429 responses:

```python
def _call_with_retry(self, model_name: str, prompt: str, config, max_retries: int = 3):
    """
    Call Gemini API with automatic retry on 429 rate limits.

    Gemini returns retryDelay in 429 responses - we parse and respect it.
    Fallback: exponential backoff (30s, 60s, 90s) if no retryDelay provided.
    """
    for attempt in range(max_retries):
        try:
            return self.client.models.generate_content(model=model_name, contents=prompt, config=config)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                # Parse retryDelay from Gemini's error response
                retry_match = re.search(r'"retryDelay":\s*"(\d+)s"', str(e))
                delay = int(retry_match.group(1)) + 1 if retry_match else 30 * (attempt + 1)
                time.sleep(delay)
                continue
            raise
```

**Model Selection:**

| Model | Speed | Quality | Cost (per 1M tokens) | Use Case |
|-------|-------|---------|----------------------|----------|
| Flash-2.5 | Fast (2-5s) | Good | $0.075 input, $0.30 output | Standard items, batch processing |
| Flash-2.5-Lite | Very fast (1-2s) | Acceptable | $0.0375 input, $0.15 output | Simple items (<50 pages, <200K chars) |

**Adaptive Prompt Selection:**

```python
def summarize_item(item_title: str, text: str, page_count: Optional[int] = None) -> Tuple[str, List[str]]:
    """
    Summarize agenda item with adaptive prompting.

    Prompt selection:
    - Standard items (<100 pages): focused prompt, 1-5 sentence summary
    - Large items (100+ pages): comprehensive prompt, 5-10 sentence summary

    Model selection:
    - Flash-Lite: <50 pages AND <200K chars
    - Flash: Everything else

    Returns: (summary_markdown, topics_list)
    """
    if page_count >= 100:
        prompt_type = "large"
        model = self.flash_model_name  # Always Flash for large items
    else:
        prompt_type = "standard"
        model = self.flash_lite_model_name if self._is_simple(text, page_count) else self.flash_model_name

    prompt = self._get_prompt("item", prompt_type, title=item_title, text=text)
    response = self.client.models.generate_content(model=model, contents=prompt, config=config)

    return self._parse_item_response(response.text)
```

**Batch Processing (50% Cost Savings):**

```python
def summarize_batch(
    item_requests: List[Dict[str, Any]],
    shared_context: Optional[str] = None,
    meeting_id: Optional[str] = None
):
    """
    Process multiple items using Gemini Batch API.

    Generator yields results per chunk:
    - 5 items per chunk (respects TPM quota)
    - 120-second delays between chunks (allows quota refill)
    - Exponential backoff on 429 errors

    Yields: List of results per chunk
    """
    # Create cache for shared context (if token count >= 1024)
    cache_name = None
    if shared_context and len(shared_context) // 4 >= 1024:
        cache = self.client.caches.create(model=self.flash_model_name, contents=[shared_context])
        cache_name = cache.name

    # Process chunks with delay between each
    for chunk in chunks:
        chunk_results = self._process_batch_chunk(chunk, cache_name, shared_context)
        yield chunk_results
        time.sleep(120)  # 120s delay for quota refill
```

---

## Prompts Architecture (prompts_v2.json)

**JSON-structured prompts** with schema-validated responses and adaptive complexity.

**Structure:**
```json
{
  "item": {
    "standard": {
      "description": "For individual agenda items - JSON structured output",
      "variables": ["title", "text"],
      "output_format": "json",
      "response_schema": { ... },
      "system_instruction": "You are an expert at analyzing city council agenda items...",
      "template": "Analyze this city council agenda item...\n\n# Item Title\n\"{title}\"\n..."
    },
    "large": {
      "description": "For complex/lengthy agenda items (100+ pages) - enhanced analysis",
      "variables": ["title", "text"],
      "output_format": "json",
      "response_schema": { ... },
      "system_instruction": "You are an expert at analyzing complex city council items...",
      "template": "Analyze this complex city council agenda item...\n..."
    }
  },
  "meeting": {
    "short_agenda": {
      "description": "FALLBACK: For full meeting packets ≤30 pages when item-level processing unavailable",
      "variables": ["text"],
      "template": "This is a city council meeting agenda. Provide a clear, concise summary..."
    },
    "comprehensive": {
      "description": "FALLBACK: For large/complex agendas >30 pages when item-level processing unavailable",
      "variables": ["text"],
      "template": "Analyze this city council meeting agenda and provide comprehensive summary..."
    }
  }
}
```

**Response Schema (item prompts):**
```json
{
  "type": "object",
  "properties": {
    "summary_markdown": {
      "type": "string",
      "description": "Main summary in markdown format (1-5 or 5-10 sentences)"
    },
    "citizen_impact_markdown": {
      "type": "string",
      "description": "How this affects residents (1 or 2-3 sentences)"
    },
    "topics": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["housing", "zoning", "transportation", "budget", "public_safety",
                 "environment", "parks", "utilities", "economic_development",
                 "education", "health", "planning", "permits", "contracts",
                 "appointments", "other"]
      },
      "minItems": 1,
      "maxItems": 3
    },
    "confidence": {
      "type": "string",
      "enum": ["high", "medium", "low"]
    }
  },
  "required": ["summary_markdown", "citizen_impact_markdown", "topics", "confidence"]
}
```

**Why JSON prompts?**
- **Version control:** Track prompt changes in git
- **Schema enforcement:** Gemini validates response against schema (no parsing errors)
- **A/B testing:** Easy to swap prompts and compare quality
- **Documentation:** Self-documenting with descriptions and variable lists

**Prompt Guidelines (from templates):**

**Standard items:**
- 1-5 sentences (simple appointments: 1-2, complex developments: 4-5)
- Include dollar amounts, addresses, dates, ordinance numbers
- Use **bold** for key numbers and names
- Plain language, no jargon

**Large items:**
- 5-10 sentences with markdown sections
- Break into ## Financial, ## Timeline, ## Impact if needed
- Include ALL dollar amounts, addresses, dates
- Use lists for multiple components
- Cross-reference documents for consistency

**Meeting summaries (fallback only):**
- Plain markdown text (no JSON)
- List all agenda items with descriptions
- Include all financial details
- Preserve exact dollar amounts and addresses
- Note public participation opportunities

---

## Topic Normalization (analysis/topics/normalizer.py)

**Maps raw LLM topics → 16 canonical topics** for consistent frontend display and filtering.

### Canonical Topics (taxonomy.json)

16 categories covering civic government:

```python
CANONICAL_TOPICS = [
    "housing",              # Housing & Development
    "zoning",               # Zoning & Land Use
    "transportation",       # Transportation & Traffic
    "budget",               # Budget & Finance
    "public_safety",        # Public Safety
    "environment",          # Environment & Sustainability
    "parks",                # Parks & Recreation
    "utilities",            # Utilities & Infrastructure
    "economic_development", # Economic Development
    "education",            # Education & Schools
    "health",               # Public Health
    "planning",             # City Planning
    "permits",              # Permits & Licensing
    "contracts",            # Contracts & Procurement
    "appointments",         # Appointments & Personnel
    "other"                 # Other
]
```

**Synonym Mapping:**
```json
{
  "housing": {
    "canonical": "housing",
    "display_name": "Housing & Development",
    "synonyms": [
      "affordable housing",
      "housing affordability",
      "low-income housing",
      "workforce housing",
      "residential development",
      "homeless services",
      "homelessness"
    ]
  },
  "zoning": {
    "canonical": "zoning",
    "display_name": "Zoning & Land Use",
    "synonyms": [
      "rezoning",
      "zoning changes",
      "land use",
      "conditional use permit",
      "variance",
      "general plan"
    ]
  },
  ...
}
```

### Normalizer Logic

```python
class TopicNormalizer:
    """Normalizes extracted topics to canonical taxonomy"""

    def normalize(topics: List[str]) -> List[str]:
        """
        Normalize raw topics to canonical forms.

        Process:
        1. Direct match: "housing" → "housing"
        2. Synonym match: "affordable housing" → "housing"
        3. Word-boundary partial match: "affordable housing plan" → "housing"
        4. No match: log to unknown_topics.log for taxonomy expansion

        Returns: Sorted list of canonical topics (deduplicated)
        """
        canonical_topics = set()

        for topic in topics:
            topic_lower = topic.strip().lower()

            # Direct match
            if topic_lower in self._synonym_map:
                canonical_topics.add(self._synonym_map[topic_lower])
            # Word-boundary-aware partial match
            elif matched := self._find_word_match(topic_lower):
                canonical_topics.add(matched)
            else:
                # Track unknown topics for taxonomy improvement
                self._track_unknown_topic(topic_lower)

        return sorted(list(canonical_topics))

    def _contains_word(text: str, word: str) -> bool:
        """
        Check if word appears as complete word(s) in text.
        Prevents false positives like "park" matching "parking".
        Uses regex word boundaries: r'\bword\b'
        """
```

**Usage:**
```python
from analysis.topics.normalizer import get_normalizer

normalizer = get_normalizer()
raw_topics = ["Affordable Housing", "bike lanes", "budget"]
canonical = normalizer.normalize(raw_topics)
# Returns: ["budget", "housing", "transportation"]
```

**Why normalize topics?**
- **Consistent filtering:** Frontend can filter by "housing" reliably across all cities
- **User-friendly labels:** "Housing & Development" vs raw "affordable housing units"
- **Analytics:** Aggregate "how often does housing appear?" across all cities
- **Taxonomy evolution:** Unknown topics logged to `{DB_DIR}/unknown_topics.log` for review

**Unknown Topic Tracking:**
- Logs to `{DB_DIR}/unknown_topics.log` when no match found
- Review periodically to expand taxonomy
- Example: If "cannabis" appears 50 times, add to taxonomy

---

## Cost Optimization Strategies

### 1. Model Selection

- **Flash-Lite (50%):** Simple items <50 pages, <200K chars → 50% cost savings
- **Flash (default):** Standard items, all batch processing
- **Never Pro:** Not cost-justified for agenda items

### 2. Adaptive Prompting

```python
# Standard item: shorter prompt, shorter output
if page_count < 100:
    prompt = SHORT_PROMPT      # ~500 tokens
    max_output = 2048          # 1-5 sentences

# Large item: longer prompt, detailed output
else:
    prompt = LONG_PROMPT       # ~1000 tokens
    max_output = 8192          # 5-10 sentences
```

**Savings:** Reduces output tokens by 50-70% for standard items

### 3. Batch Processing

- **50% cost reduction** for batch API
- **Process overnight:** 100 items = $0.50 instead of $1.00
- **Trade-off:** 5-15 minute latency (acceptable for background processing)

### 4. Context Caching

```python
# Create cache for shared meeting context (>1024 tokens)
if len(shared_context) // 4 >= 1024:
    cache = client.caches.create(
        model=flash_model_name,
        contents=[shared_context],
        ttl="3600s"  # 1 hour
    )
    # Reuse cache across all items in meeting
```

**Savings:** Cached tokens cost 10% of normal input tokens

**Monthly cost estimate (500 cities, ~10K items/month):**
- Real-time Flash: $150/month
- Batch Flash: $75/month
- Batch Flash + caching: $60/month
- **Total savings: $90/month ($1,080/year)**

---

## Error Handling

**Common failure modes and recovery strategies:**

### 1. Rate Limiting (429 / RESOURCE_EXHAUSTED)

Handled reactively via `_call_with_retry()`:
- Parses `retryDelay` from Gemini's 429 error response
- Fallback: exponential backoff (30s, 60s, 90s)
- Batch processing: 5 items per chunk with 120s delays between chunks

```python
def _call_with_retry(self, model_name: str, prompt: str, config, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            return self.client.models.generate_content(...)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                # Parse retryDelay or use exponential backoff
                delay = parse_retry_delay(e) or 30 * (attempt + 1)
                time.sleep(delay)
                continue
            raise
```

### 2. Content Filtering (Safety blocks)
```python
try:
    response = client.generate_content(prompt)
except ContentFilterError as e:
    logger.warning("content filtered", item_id=item_id, reason=str(e))
    return {
        "summary": "[Content unavailable due to safety filters]",
        "topics": ["other"],
        "confidence": "low"
    }
```

### 3. Schema Validation Failure
- With `response_schema`, Gemini enforces JSON structure
- If malformed JSON: retry with explicit error message in prompt
- Track finish_reason: if "MAX_TOKENS", increase max_output_tokens

### 4. PDF Extraction Failures
```python
async def extract_pdf_async(url: str) -> Dict[str, Any]:
    """Extract text from PDF with error handling"""
    try:
        pdf_bytes = await self.download_pdf_async(url)
        result = await asyncio.to_thread(self.pdf_extractor.extract_from_bytes, pdf_bytes)

        if not result.get("success"):
            raise ExtractionError(f"PDF extraction failed: {result.get('error')}")

        return result
    except (ExtractionError, aiohttp.ClientError) as e:
        logger.error("pdf processing failed", url=url, error=str(e))
        raise
```

---

## Quality Metrics

**Target metrics:**

| Metric | Target | Notes |
|--------|--------|-------|
| Summary accuracy | >90% | Human reviewers rate 4+/5 = accurate |
| Topic precision | >85% | Match against human-labeled ground truth |
| Confidence calibration | >0.85 | Model confidence correlates with accuracy |
| JSON parse success | 100% | Schema enforcement ensures this |

**Definitions:**
- **Summary accuracy:** Human reviewers rate summaries on 5-point scale, 4+ = accurate
- **Topic precision:** % of extracted topics that match human-labeled ground truth
- **Confidence calibration:** Correlation between model confidence ("high"/"medium"/"low") and human accuracy ratings
- **JSON parse success:** % of responses that parse without errors (schema enforcement ensures 100%)

---

## Testing

**Topic normalization testing:**

```python
from analysis.topics.normalizer import get_normalizer

normalizer = get_normalizer()
raw = ["Affordable Housing", "bike lanes", "budget"]
normalized = normalizer.normalize(raw)

assert "housing" in normalized
assert "transportation" in normalized
assert "budget" in normalized
```

**Adaptive prompt selection:**

```python
# Standard item (<100 pages)
prompt_type = "large" if 50 >= 100 else "standard"
assert prompt_type == "standard"

# Large item (100+ pages)
prompt_type = "large" if 150 >= 100 else "standard"
assert prompt_type == "large"
```

**Live API testing:**

```python
# Test live Gemini API
summarizer = GeminiSummarizer(api_key=os.getenv("GEMINI_API_KEY"))

summary, topics = summarizer.summarize_item(
    item_title="Zoning Variance Request",
    text="The applicant requests a variance to allow...",
    page_count=5
)

assert len(summary) > 0
assert len(topics) > 0
```

---

## Future Work

**Model improvements:**
- [ ] Test Gemini-2.5 Flash Thinking (experimental extended thinking mode)
- [ ] A/B test Flash vs Flash-Lite on accuracy (validate cost savings)
- [ ] Fine-tuning: Train custom model on civic-specific language (requires 1000+ examples)

**Prompt engineering:**
- [ ] Chain-of-thought prompting (explicit step-by-step reasoning)
- [ ] Few-shot examples (include 2-3 example summaries in prompt for consistency)
- [ ] Prompt versioning infrastructure (track changes, measure quality regression)

**Topic extraction:**
- [ ] Expand to 20 topics (add "climate", "immigration", "cannabis", "housing")
- [ ] Multi-label confidence scores (probability per topic instead of binary)
- [ ] Topic hierarchy (parent-child relationships: "housing" → "affordable housing", "senior housing")

**Cost optimization:**
- [ ] Embedding-based deduplication (cache embeddings for repeated text)
- [ ] Summarize-then-expand: Quick summary first, expand only if user clicks
- [ ] Local models: Run Llama-3 locally for simple items (<10 pages), Gemini for complex

**Async improvements:**
- [ ] Connection pooling for HTTP session (single session across all tasks)
- [ ] Structured concurrency (task groups for better error handling)

---

**See Also:**
- [pipeline/README.md](../pipeline/README.md) - How analysis integrates with processing
- [database/README.md](../database/README.md) - How summaries are stored
- [VISION.md](../docs/VISION.md) - Roadmap for intelligence features (Phase 6)

**Last Updated:** 2025-12-04 (Documentation accuracy audit)
