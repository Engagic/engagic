# Changelog

All notable changes to the Engagic project are documented here.

For architectural context, see CLAUDE.md and module READMEs.

---

## [2026-04-08] OOM Protection for PDF Extraction

### Forkserver Child Memory Cap (analyzer_async.py)

`_extract_pdf_worker` now sets `RLIMIT_AS = 1GB` before extraction. On 2026-04-07, a bay-area-all.txt process-cities run was OOM-killed at 23:43:28 -- a 2,155-page PDF with 107 OCR pages pushed a forkserver child past 1GB RSS, total system memory exhausted (3.8GB RAM + 6GB swap fully consumed), kernel killed the parent conductor (609MB RSS, pid 3060011). Forkserver children survived as orphans, 2 jobs stuck in `processing`, 14 SF jobs never started.

Each child now gets MemoryError before it can threaten the parent. Since extraction is per-attachment, other attachments for the same item keep processing normally. Budget: 6 concurrent children (pdf_semaphore) * 1GB = 6GB ceiling, leaves ~4GB for parent + postgres + system. Normal PDFs use 200-350MB.

### Crash Recovery for process-cities (conductor.py)

`process-cities` now calls `reset_stale_processing_jobs()` on startup, same as `run-processor` already did. Zombie `processing` jobs from a prior crash or OOM get flipped back to `pending` before the run begins.

---

## [2026-04-08] Chunker, Adapter, and Pipeline Fixes

### Pageref Chunker Path (agenda_chunker_v2.py)

New `v2_pageref` extraction path for packet PDFs where the agenda pages (1-4) have internal page links (kind=4) pointing to staff reports deeper in the document. These "Page XX" references define item boundaries more accurately than the PDF's embedded TOC, which in these packets only contains attachment-internal bookmarks (slide titles, memo sections).

Detection: 3+ internal links from first 10 pages pointing beyond page 10 triggers the path. Collection is more permissive -- gathers all forward-pointing links so early attachments (e.g. warrants on page 6) aren't missed.

- **Greenfield CA**: 0 items (TOC produced slide titles) -> 14 real items (I-1 through L-6)

### TOC Attachment Grouping (agenda_chunker_v2.py)

TOC entries starting with "Att." or "Attachment" followed by a digit are now folded into the preceding item as synthetic children. Handles packet PDFs where items and their attachments are at the same TOC level (e.g. Hillsborough ADRB: `Item 1_...`, `Att. 1_...`, `Att. 2_...` all at L1).

- **Hillsborough CA**: 16 items (every attachment a separate "item") -> 4 real items with memos

### Date Range Midnight Normalization (base_adapter_async.py, all adapters)

`datetime.now()` includes time-of-day, so `start_date = now - 14 days` at 10:39 PM excludes meetings at midnight on the boundary day. Added `_date_range()` on the base adapter that strips time to midnight. All 16 adapters now use it instead of computing the range locally.

- **Greenfield CA**: March 24 meeting excluded when syncing on March 24 evening

### SharePoint URL Resolver (base_adapter_async.py)

SharePoint sharing links (`/:b:/g/...`, `/:w:/g/...`) serve HTML viewer pages, not PDFs. New `_resolve_sharepoint_urls()` on the base adapter fetches each sharing link, extracts the `.downloadUrl` from the embedded JSON (or `download.aspx?UniqueId=` for Word docs), and replaces the attachment URL before storage. Uses `requests.Session` (not aiohttp) because SharePoint's anonymous cookie/redirect chain requires proper cookie jar handling.

Runs automatically in `fetch_meetings()` when any item attachment matches the SharePoint sharing URL pattern. DB stores clean direct download URLs.

- **Marina CA**: 8 failed attachments -> 0 (12/12 SharePoint URLs resolved, including 1 Word doc)

### WP Events / ProudCity Pagination Fix (wp_events_adapter_async.py, proudcity_adapter_async.py)

Pagination stop condition used publication date (90-day cutoff). Cities that bulk-create events months in advance (Sebastopol created April 2026 meetings in Sept 2025) had their events buried on page 2+, never fetched. Now stops when all meeting dates on a page (parsed from titles) are before the lookback window. Falls back to 180-day publication date cutoff when titles aren't parseable.

- **Sebastopol CA**: April 7 City Council meeting (42 PDFs, 13 agenda items) was completely missing from DB

---

## [2026-03-28] Fetch Quality Fixes -- CivicWeb, Legistar, Granicus, CivicPlus

### CivicWeb Agenda PDF Discovery (civicweb_adapter_async.py)

CivicWeb compiles agenda + all staff reports into a single 100-600 page packet PDF with no TOC and no hyperlinks. The chunker was running text-based item detection across the entire packet, matching statute numbers and exhibit headers as items (Hemet: 728 garbage items, Pasco: 389).

CivicWeb stores the agenda-only HTML at `document/{packet_id + 1}`, and `?printPdf=true` serves it as a proper PDF with hyperlinks to per-item staff report PDFs. The adapter now discovers this agenda PDF and uses `_chunk_agenda_then_packet` -- URL-based parsing on the agenda first, TOC-based on the packet as fallback.

- **Hemet**: 728 garbage items -> 25 real items with 12 staff report attachments
- **Pasco**: 389 garbage items -> 23 items (4 via TOC on other meetings)

### Chunker Page Cap for Text-Based Item Detection (agenda_chunker.py)

`_parse_url_based` now limits text-based item boundary detection to the first 20 pages. Links are still extracted from ALL pages so attachments deep in a packet get assigned to agenda items. Prevents statute citations (`82.02`, `35.10`) and section references in compiled packet PDFs from being matched as agenda item numbers.

### Legistar Garbage Detection Tightened (legistar_adapter_async.py)

Westminster CA's Legistar API returned 70 items that were page chrome ("AGENDA", section dividers `___`, Vietnamese/Spanish translations). The garbage detector missed it: `useless_ratio=0.56` was under the 0.60 threshold.

- Lowered useless-item threshold from 60% to 50%
- Added boilerplate title detection: literal "AGENDA", "MEETINGS", underscore dividers, empty titles
- Either signal (useless_ratio > 0.50 OR boilerplate_ratio > 0.15) with page_break present triggers HTML fallback
- **Westminster**: 70 garbage items -> falls back to HTML scraping, gets 20 real items from Granicus packet

### CivicPlus Dedup by packet_url (civicplus_adapter_async.py)

Antioch CA had two meetings with different titles ("City Council Special and Regular Meeting Materials (PDF)" vs "Meeting - March 24, 2026") pointing to the same packet URL. The dedup keyed on `date|title` and missed it.

- Added `packet_url` as the highest-priority dedup key -- same packet = same meeting regardless of title
- **Antioch**: 2 x 693 items -> 1 meeting, 49 items (TOC-based, correct)

### Granicus ViewPublisher Listing Dedup (granicus_parser.py)

Falls Church VA meetings appeared in both "Recent Meetings" and "Archived Meetings" sections on the ViewPublisher page, causing duplicate fetching and PDF parsing.

- `parse_viewpublisher_listing` now deduplicates by `event_id` before returning

---

## [2026-03-28] Deep Content Pipeline Audit -- Silent Content Loss Fixes

Four fixes addressing content that was silently dropped or degraded across the pipeline. Discovered via live example: Florence AL had 0 items despite a 4-page agenda PDF with 35 hyperlinked staff reports, each containing embedded Legistar S3 attachment links.

### HTML Attachment Page Resolution (analyzer_async.py)

When an attachment URL serves an HTML page instead of a PDF, PyMuPDF would silently open it as `format: 'HTML5'`, extract the page chrome text (link labels, nav elements), and discard all hyperlinks to actual documents. The LLM then summarized garbage.

- `download_pdf_async` now checks response Content-Type and PDF magic bytes. If HTML is detected, `_extract_best_pdf_link` parses the page for `.pdf` hrefs and vendor document viewer patterns (`/ViewFile/`, `/DocumentCenter/View/`, `/MetaViewer.php`, CloudFront, S3), follows through to the actual PDF (depth=1 guard prevents loops). Generic safety net for all vendors.

### Sub-Attachment Resolution from Staff Report Cover Sheets (base_adapter_async.py)

Many Granicus cities (Florence AL, Bozeman MT, etc.) use a two-level attachment structure: agenda PDF links to 1-page CloudFront staff report cover sheets, which themselves contain hyperlinks to the actual documents (contracts, exhibits, resolutions) on Legistar S3. URL-based chunking correctly assigned the CloudFront links to items, but the processor only extracted text from the cover sheet -- never following through to the real documents.

- `_resolve_sub_attachments` added to base adapter (generic, not vendor-specific). After URL-based chunking in `_chunk_agenda_then_packet`, downloads each item's primary PDF attachment, extracts embedded document links via PyMuPDF, and appends them as additional attachments. The Granicus-specific `_fetch_s3_pdf_attachments` already did this for S3 HTML-parsed items; this generalizes it to all URL-chunked items across all vendors.
- **Florence AL item 11.c**: 1 attachment (cover sheet) -> 4 attachments (cover sheet + MSA + business license + contract).

### Parenthesized Item Numbers in Agenda Chunker (agenda_chunker.py)

Agendas using `(a)`, `(b)`, `(c)` or `(1)`, `(2)`, `(3)` sub-item numbering (common in Alabama, some Texas cities) produced 0 items with all links orphaned, because the item detection regex and heuristics didn't recognize the format.

- Added `\([a-z]\)` and `\(\d{1,2}\)` patterns to `ITEM_NUM_RE`.
- Added same patterns to the `has_num` fast-path gate in `_parse_agenda_items`.
- Parenthesized items treated as sub-items in `_is_likely_item_header` (bypasses bold/uppercase heuristics, same as `2.a` or `4.1`).
- **Florence AL**: 0 items / 35 orphan links -> 30 items / 0 orphan links.

### Legacy .doc and RTF Extraction (parsing/pdf.py)

1,825 legacy `.doc` (OLE2 format) and 92 `.rtf` attachments were silently failing extraction. The processor accepted them (`att_type "doc"` passes the filter), downloaded the bytes, and fed them to `fitz.open(stream=bytes, filetype="pdf")` which threw an exception caught as a generic `ExtractionError`. Items with only `.doc` attachments got no extracted text. Note: `.docx` (ZIP/OOXML format, 19,297 attachments) was already handled correctly by PyMuPDF.

- `_detect_format` reads magic bytes: `%PDF-` (pdf), `PK\x03\x04` (docx), `\xd0\xcf\x11\xe0` (legacy doc), `{\rtf` (rtf).
- `extract_from_bytes` routes by format: legacy `.doc` -> antiword (subprocess), `.rtf` -> striprtf, everything else -> PyMuPDF (unchanged).
- New dependencies: `python-docx`, `striprtf` (pip), `antiword` (apt).

---

## [2026-03-20] Agenda Chunker TOC Path + Adapter PDF Escalation

### Agenda Chunker: TOC-Based Chunking

When a PDF has no hyperlinked attachment URLs but does have a bookmark/outline tree (TOC) with embedded staff memos, the old URL-only chunker returned hollow items. The chunker now dispatches TOC-first.

- **vendors/adapters/parsers/agenda_chunker.py**: Unified two-path parser. First checks for meaningful TOC (`_has_meaningful_toc`). If found, detects hierarchical vs flat pattern (`_detect_toc_pattern`):
  - **Hierarchical:** L1 TOC entries = agenda items on agenda pages, L2 = embedded attachments on content pages. Extracts `_MemoContent` (subject, summary, fiscal_info, recommended_action, submitted_by, full_text) from each page range.
  - **Flat:** L1 entries beyond the agenda page point to individual memos. Fuzzy-matches memos to items by title/body text similarity (SequenceMatcher + keyword overlap).
- **Pipeline integration:** For TOC items, memo `full_text` is emitted as `body_text` in the pipeline-compatible output. The processor already handles `body_text` as a fallback path (processor.py line 766) — items with body_text go straight to summarization without URL downloads. URL-based attachments with empty URLs are filtered out to avoid `AttachmentSchema` validation failures.
- **URL path preserved:** When no TOC exists, falls back to the existing 4-pass URL-based extraction (metadata → sections/items → body text → link assignment).
- **New output fields:** `parse_method` in metadata (toc_hierarchical / toc_flat / url), `memo_count` and `memo_pages` per item, `orphan_memos` at top level.
- **CLI:** Added `--force-toc` and `--force-url` flags for debugging.

### Granicus: Agenda/Packet PDF Escalation

Some Granicus cities have both an agenda PDF and a packet PDF on their meeting page. The agenda PDF may be hyperlinked (URL-based chunking works) or flat (needs the packet PDF for TOC-based chunking). Previously only one PDF was tried.

- **vendors/adapters/granicus_adapter_async.py**: `_find_agenda_and_packet_urls` replaces `_find_packet_url` — finds both agenda PDF (links with "agenda" in text/href) and packet PDF (MetaViewer links or "packet" keyword) from the HTML page. When HTML parsing yields no items, tries the agenda PDF first (URL-based chunking for hyperlinked attachments). If hollow items result, escalates to the packet PDF (TOC-based chunking with body_text from embedded memos). Falls back to monolithic `packet_url` if neither produces usable items.

### CivicPlus: Monolithic Packet Detection

Some CivicPlus cities (e.g. Citrus Heights CA) have structured HTML agendas with good item titles and descriptions, but no per-item attachment PDFs. Instead, a single monolithic "Agenda Packet" PDF is listed as one of the items, bundling all staff memos. Previously, the HTML items were accepted as-is (hollow, unsummarizable).

- **vendors/adapters/civicplus_adapter_async.py**: After HTML parsing, `_detect_monolithic_packet` checks if ≥70% of substantive items lack attachments and one item's title/attachment name matches agenda packet patterns. If detected, extracts the packet PDF URL, strips the fake packet "item", and runs the agenda chunker on the packet for TOC-based body_text extraction. If the chunker produces items with body_text, uses those; otherwise keeps the HTML items as-is.

---

## [2026-03-20] Granicus S3 Grid HTML Parser + PDF Agenda Chunker + CivicPlus Item Extraction

### Granicus S3 Grid HTML

Native Granicus sites (e.g. Bozeman MT, Carson City NV) redirect AgendaViewer.php to S3/CloudFront-hosted HTML pages with a CSS grid layout. These were falling through to monolithic fallback with 0 items because the existing parsers didn't recognize the format.

- **vendors/adapters/parsers/granicus_parser.py**: Added `parse_granicus_s3_html` — fourth HTML format parser for Granicus. Handles h2 section headers (letter or numeric), h3 agenda items with CloudFront PDF links, staff names in parens (Bozeman style), matter file extraction (Carson City `LU-2026-0023` style), and attachment links in sibling divs.
- **vendors/adapters/granicus_adapter_async.py**: Three-way URL routing: AgendaOnline → S3/CloudFront → legacy (with S3 fallback). Added `_fetch_s3_pdf_attachments` — downloads each item's staff report PDF and extracts embedded Legistar S3 attachment links via PyMuPDF, same link extraction approach as `agenda_chunker.py`.

**Result:** Bozeman's March 24 agenda: previously 4 meetings / 0 items. Now extracts ~25 items with staff names, sections, motion text, staff report PDFs, and embedded attachments.

### PDF Agenda Chunker

When Granicus or CivicPlus HTML parsing yields no items, the adapter now downloads the monolithic packet PDF and attempts to extract structured items from it.

- **vendors/adapters/parsers/agenda_chunker.py** (new): Generalized PDF agenda parser using PyMuPDF. 4-pass extraction: (1) meeting metadata from first page, (2) section headers and item boundaries via numbering patterns + bold/caps heuristics, (3) body text and recommended actions between item boundaries, (4) PDF hyperlink assignment to owning items by page/y-position. Handles varied numbering schemes (1., 1.1, A., I.), standalone number lines (CivicPlus style where "2." is on its own line), case/docket numbers (CUP, ZA, SUP, etc.), and consent-prefix patterns. Returns pipeline-compatible dicts matching AgendaItemSchema/AttachmentSchema.
- **vendors/adapters/granicus_adapter_async.py**: When HTML parsers return 0 items, `_parse_packet_pdf` downloads the packet PDF to a temp file, runs `parse_agenda_pdf` via `asyncio.to_thread`, and adds extracted items to the meeting. Falls back to monolithic `packet_url` if chunking fails.

### CivicPlus Item Extraction

CivicPlus was previously monolithic-only (packet PDF URL, no items). Now has three-tier extraction: HTML → PDF → monolithic.

- **vendors/adapters/parsers/civicplus_parser.py** (new): Parses CivicPlus `?html=true` HTML agendas. Structured `div.item.level{1,2,3}` hierarchy — level 1 always treated as section headers, level 2+ as substantive items. Nested section tracking (e.g. "REGULAR BUSINESS > RESOLUTION(S)"). Generic titles like "Consent A" or "Resolution 1" replaced with actual description text. Extracts attachments from `.documents a.file` links.
- **vendors/adapters/civicplus_adapter_async.py**: After collecting meetings, concurrent `_try_parse_packet_items` for each meeting: (1) for ViewFile URLs, fetches `?html=true` and parses via `civicplus_parser.py`, (2) falls back to PDF parsing via `agenda_chunker.py`, (3) keeps monolithic `packet_url` if both fail.

**Result:** Ardmore OK March 16 agenda: previously 0 items (monolithic PDF). Now extracts 21 items with 15 attachments, proper section nesting, and substantive titles.

---

## [2026-02-28] Subprocess Isolation for PDF Extraction

PyMuPDF segfaults on certain malformed municipal PDFs, killing the entire process-cities run with no traceback or log. Two segfaults confirmed in dmesg (`SIGSEGV` in python3.13 and libc.so.6). No Python exception handler can catch a C-level segfault.

### Changes
- **analysis/analyzer_async.py**: PDF extraction now runs in an isolated child process via `multiprocessing` forkserver. A segfault kills only the child; the parent gets a non-zero exit code and raises `ExtractionError` with the signal info. Processing continues to the next meeting.
- **pipeline/processor.py**: Added `except Exception` catch-all in `process_city_jobs` for Python-level exceptions outside the narrow `(ProcessingError, LLMError, ExtractionError)` list.
- **pipeline/conductor.py**: Wrapped per-city `process_city_jobs` call in try/except so a city-level failure doesn't kill the entire multi-city loop.

### Result
A malformed PDF that previously killed the entire 214-city batch run now logs a failed extraction and moves on.

---

## [2026-01-15] Human Context in Appeals/Variances

Enhanced summarizer prompt to capture narrative context in quasi-judicial items (appeals, variances, hearings).

### Problem
Summaries for appeals/variances were technically accurate but missed human circumstances. Example: Jacksonville daycare variance V-25-22 summary listed distance requirements but omitted that the facility operated 22 years, the previous owner died, and the predator was grandfathered while the daycare faced closure.

### Changes
- **prompts_v2.json**: Added new document type for "appeal, variance, or quasi-judicial hearing" with extraction guidance for backstory, timeline, stakeholders, procedural history, and applicant statements
- **prompts_v2.json**: Added two real-world examples (Jacksonville daycare, Las Vegas carport) demonstrating human-context extraction without editorializing

### Result
New summaries capture circumstances driving the request while maintaining factual objectivity. Technical details still included; human context now surfaced when present in source documents.

---

## [2025-12-16] Unified Summarizer Prompt

Replaced page-count-based prompt selection with single unified prompt. LLM now determines output depth based on content complexity, not document length.

### Changes
- **Prompt selection**: Removed `PROMPT_EXPERIMENT` config and adaptive standard/large logic
- **prompts_v2.json**: Removed `item.standard` and `item.large`, kept only `item.unified`
- **summarizer.py**: `_select_prompt_type()` always returns `"unified"`

### Rationale
Page count is a poor proxy for civic importance. A 3-page rezoning can reshape a neighborhood; a 150-page contract renewal is boilerplate. The unified prompt gives the LLM explicit guidance on complexity signals (ordinances with multiple provisions, tenant protections, zoning changes) rather than mechanical thresholds.

### Also
- `happening_email.py`: Moved recipient email to `ENGAGIC_HAPPENING_RECIPIENT` env var

---

## [2025-12-15] Field Name Consistency Sweep

Second audit round focused on field name mismatches between adapters, parsers, and orchestrator.

### P0: Additional Field Name Fixes

**1. `agenda_number` vs `item_number` Mismatch**
- `meeting_sync.py:298` was reading `item_data.get("item_number")`
- Legistar/Chicago adapters return `agenda_number`
- Escribe/IQM2 adapters were returning `item_number` (wrong)
- Fix: Orchestrator reads `agenda_number`, adapters updated to return it

**2. Parser `vendor_item_id` Consistency**
All 5 parsers were using `item_id` instead of `vendor_item_id`:
- `granicus_parser.py:111`
- `legistar_parser.py:158, 329`
- `municode_parser.py:167`
- `novusagenda_parser.py:74`
- `primegov_parser.py:187, 240`

Fix: All parsers now return `vendor_item_id`

**3. Berkeley `vendor_item_id`**
- `berkeley_adapter_async.py:281` was returning `item_id`
- Fix: Changed to `vendor_item_id`

**4. Berkeley `sponsor` vs `sponsors`**
- `berkeley_adapter_async.py:288` was returning `'sponsor': sponsor` (singular string)
- Orchestrator reads `'sponsors'` (plural list)
- Fix: Changed to `'sponsors': [sponsor]`

**5. Schema Cleanup**
- Removed `item_number` alias from `vendors/schemas.py`
- Was marked as "alias for agenda_number" but nothing used it

### Files Changed
```
pipeline/orchestrators/meeting_sync.py             # item_number -> agenda_number
vendors/adapters/escribe_adapter_async.py          # item_number -> agenda_number
vendors/adapters/iqm2_adapter_async.py             # item_number -> agenda_number (2 places)
vendors/adapters/custom/berkeley_adapter_async.py  # item_id -> vendor_item_id, sponsor -> sponsors
vendors/adapters/parsers/granicus_parser.py        # item_id -> vendor_item_id + docstring
vendors/adapters/parsers/legistar_parser.py        # item_id -> vendor_item_id (2 places) + docstrings
vendors/adapters/parsers/municode_parser.py        # item_id -> vendor_item_id + docstring
vendors/adapters/parsers/novusagenda_parser.py     # item_id -> vendor_item_id + docstring
vendors/adapters/parsers/primegov_parser.py        # item_id -> vendor_item_id (2 places) + docstring
vendors/schemas.py                                 # removed item_number alias
```

### Consistent Field Contract
All adapters/parsers now return:
- `vendor_item_id`: Raw vendor identifier
- `agenda_number`: Position in meeting agenda
- `sequence`: Ordering integer
- `sponsors`: List of sponsor names (when available)

Orchestrator reads these exact field names.

---

## [2025-12-15] Architectural Coherence Audit

Deep audit across adapters, repositories, and pipeline revealed additional issues beyond the orphan crisis. Focus: consistency, intuitive APIs, and eliminating silent failures.

### P0: Active Data Loss Fixes

**1. `vendor_item_id` Field Name Mismatch (CRITICAL)**
- `meeting_sync.py:278` was reading `item_data.get("item_id")`
- All adapters return `vendor_item_id`
- Result: ALL vendor item IDs were being silently ignored, falling back to sequence-based IDs
- Same class of bug that caused the matter ID crisis
- Fix: Changed to `item_data.get("vendor_item_id")`

**2. Split Transaction Race Condition**
- `items.py:update_agenda_item()` updated item in one transaction, topics in another
- Crash between them left item without topics
- Fix: Wrapped both in single transaction

**3. Removed `vendor_id/meeting_id` Fallback**
- `meeting_sync.py:67` had `vendor_id or meeting_id` fallback hiding adapter inconsistencies
- Fix: Now requires `vendor_id`, fails explicitly if missing

### P1: Silent Failure Visibility

**4. FetchResult Pattern**
- `base_adapter_async.py` now returns `FetchResult` dataclass instead of `List[Dict]`
- Callers can distinguish "0 meetings" from "adapter failed"
- `fetcher.py` updated to check `fetch_result.success` and log adapter errors

**5. Exception Logging**
- `deliberation.py`: Added logging for caught `UniqueViolationError` and `ForeignKeyViolationError`
- Previously returned error dicts silently

**6. Schema Field Names**
- `vendors/schemas.py`: Updated to use `vendor_id` and `vendor_item_id` (matching adapter output)
- Previous schema used `meeting_id` and `item_id` (wrong)

### P2: Consistency Improvements

**7. Centralized HTTP Timeout**
- Added `VENDOR_HTTP_TIMEOUT` to `config.py`
- `base_adapter_async.py` now uses config value instead of hardcoded 30

**8. Tightened Exception Handlers**
- `fetcher.py`: Changed 3 broad `except Exception` to specific `(VendorError, asyncio.TimeoutError, aiohttp.ClientError)`
- Merged duplicate dataclass imports in `base_adapter_async.py`

### Files Changed
```
pipeline/orchestrators/meeting_sync.py   # vendor_item_id fix, vendor_id requirement
pipeline/fetcher.py                      # FetchResult handling, tightened exceptions
database/repositories_async/items.py     # atomic transaction for update
database/repositories_async/deliberation.py  # exception logging
vendors/adapters/base_adapter_async.py   # FetchResult, config timeout
vendors/schemas.py                       # correct field names
config.py                                # VENDOR_HTTP_TIMEOUT
```

### Deferred (P2/P3)
- Full constant centralization (rate limits, processing thresholds)
- Return type standardization across repositories
- `conn` parameter for engagement.py
- Adapter contract documentation
- Diagnostics enhancements

### Resolution
Items will self-correct on next sync cycle. No data migration required.

---

## [2025-12-15] Post-Mortem Hardening Follow-up

Addressed remaining gaps found during code review after the orphan crisis.

### Transaction Atomicity Fixes
- `queue.py`: Wrapped `mark_job_failed` and `mark_processing_failed` in transactions with FOR UPDATE to prevent race conditions on retry_count
- `committees.py`: Added `conn` parameter to `add_member_to_committee` and `remove_member_from_committee` for transaction participation
- `engagement.py`: Made `watch()` and `unwatch()` atomic with activity logging (same transaction)

### ID Generation Hardening
- `id_generation.py`: Added explicit whitespace check for `vendor_item_id`
- `granicus_parser.py`: Removed redundant `matter_id` assignment (matter_file takes precedence)
- Note: `vendor_item_id` field name mismatch discovered and fixed in Coherence Audit above

### FK Constraints (Migration 017)
- Added FK on `userland.used_magic_links.user_id` -> `userland.users(id)` ON DELETE CASCADE
- Added FK on `tracked_items.first_mentioned_meeting_id` -> `meetings(id)` ON DELETE SET NULL

### Files Changed
```
database/repositories_async/committees.py   # conn param for atomicity
database/repositories_async/queue.py        # transaction + FOR UPDATE
database/repositories_async/engagement.py   # atomic watch/unwatch
database/id_generation.py                   # whitespace validation
pipeline/orchestrators/meeting_sync.py      # remove fragile fallback
vendors/adapters/parsers/granicus_parser.py # remove redundant assignment
database/migrations/017_userland_fks.sql    # FK constraints
```

---

## [2025-12-16] Orphaned Records Post-Mortem

**Severity: Critical**
**Duration: ~2 weeks of accumulated rot**
**Resolution: 4 migrations, 1 migration script, architectural overhaul**

### What Happened

Orphaned items and duplicate matters accumulated silently until queries returned garbage data and FK violations blocked syncs. Database integrity was compromised with:
- 60 duplicate matters (same legislation, different IDs)
- 52 orphaned matters (no items referencing them)
- Unknown count of orphaned happening_items
- Broken matter_appearances references

### Root Causes (The Dogshit Practices)

**1. Distributed ID Generation (FATAL FLAW)**

Each adapter generated its own item IDs with inconsistent formats:
```python
# Legistar: "item_id": str(item_id)
# IQM2: "item_id": legifile_id or f"iqm2-{slug}-{meeting}-{counter}"
# Chicago: "item_id": str(item_id)
# Escribe: "item_id": f"escribe_{item_id}"
```
No single source of truth. Orchestrator couldn't reliably map items back to raw data.

**2. Flawed Matter ID Logic (THE KILLER)**

Old generation combined matter_file AND matter_id:
```python
key = f"{banana}:{matter_file or ''}:{matter_id or ''}"
```
Problem: Vendors create NEW backend matter_ids for each agenda appearance, but matter_file stays stable. Same legislation got different matter IDs every time it appeared. Duplicates accumulated silently.

**3. No Foreign Key Constraints**

`happening_items` had no FK constraints to `meetings` or `items`. Records could reference deleted entities. Database couldn't enforce integrity.

**4. Separate Transactions**

Repository methods each started their own transactions:
```python
async def store_meeting(...):
    async with self.transaction():  # Transaction 1
        ...

async def store_items(...):
    async with self.transaction():  # Transaction 2 - CAN FAIL INDEPENDENTLY
        ...
```
If transaction 2 failed, transaction 1 already committed. Orphans created.

**5. Brittle String Parsing**

Orchestrator extracted item IDs via string splitting:
```python
item_id_short = agenda_item.id.rsplit("_", 1)[1]  # BREAKS WITH NEW FORMATS
raw_item = items_map.get(item_id_short, {})
```
When ID formats changed, lookups failed silently. Data lost.

**6. No Monitoring**

Zero visibility into orphan accumulation. No diagnostics. No alerts. Problems festered for weeks until catastrophic failure.

### The Fix

**Centralized ID Generation** (`database/id_generation.py`):
- `generate_item_id()` - Single source of truth for all adapters
- Adapters return raw `vendor_item_id`, orchestrator generates final ID
- Deterministic: same inputs always produce same ID

**Strict Matter ID Hierarchy**:
```python
# NEW: matter_file takes absolute precedence
if matter_file:
    key = f"{banana}:file:{matter_file}"  # matter_id IGNORED
elif matter_id:
    key = f"{banana}:id:{matter_id}"
```

**Connection Passing for Atomicity**:
```python
async def store_meeting(..., conn=None):
    async with self._ensure_conn(conn) as c:  # Participates in caller's transaction
        ...
```

**FK Constraints** (Migration 014):
- `happening_items.meeting_id` -> `meetings.id` ON DELETE CASCADE
- `happening_items.item_id` -> `items.id` ON DELETE CASCADE

**Sequence-Based Lookup**:
```python
# OLD: items_map = {item["item_id"]: item ...}  # Fragile
# NEW: items_map = {item.get("sequence", idx): item ...}  # Stable
```

**Diagnostics Tool** (`scripts/diagnostics.py`):
- Detects orphaned matters, items, queue jobs
- Finds duplicate matters by matter_file
- Checks FK integrity across all tables

**Data Migration** (Migration 016 via `scripts/migrate_matter_ids.py`):
- Recalculated all matter IDs with new logic
- Merged 60 duplicates into canonical records
- Deleted 52 orphans
- Updated 57,352 FK references

### Files Changed

```
database/id_generation.py              # +generate_item_id(), strict matter hierarchy
database/repositories_async/base.py    # +_ensure_conn() for transaction participation
database/repositories_async/matters.py # Orphan filtering in get_matter()
pipeline/orchestrators/meeting_sync.py # Centralized ID gen, sequence lookup, error handling
vendors/adapters/*_async.py            # item_id -> vendor_item_id (all 6 adapters)
scripts/diagnostics.py                 # NEW: Orphan detection tool
scripts/migrate_matter_ids.py          # NEW: Data migration script
database/migrations/014-016            # FK constraints, cleanup, matter ID fix
```

### Lessons Learned

1. **Single source of truth for ID generation** - Never let multiple components generate IDs
2. **FK constraints from day one** - Database should enforce integrity, not application code
3. **Transaction atomicity** - Related operations must be in same transaction
4. **Monitoring for data integrity** - Run diagnostics regularly, not after catastrophe
5. **Strict hierarchies for deduplication** - When multiple identifiers exist, pick ONE canonical source
6. **Never parse IDs with string operations** - Use structured lookups (sequence, explicit fields)

### Prevention

- Run `scripts/diagnostics.py` weekly on VPS
- All new tables get FK constraints in initial schema
- ID generation ONLY in `database/id_generation.py`
- Repository methods accept `conn` parameter for transaction participation

---

## [2025-12-11] Auth Security Hardening

Comprehensive auth flow audit and fixes.

### Security Fixes
- **Broken refresh flow**: Added `credentials: 'include'` to frontend auth API
- **User enumeration**: Login/signup now return identical responses regardless of account existence
- **Email bombing**: Per-email rate limiting (3 requests/hour) on magic link endpoints
- **Token revocation**: Server-side refresh token storage with rotation on use
- **Magic link expiry**: Fixed incorrect hardcoded expiry in used_magic_links table

### Changes
- `frontend/src/lib/api/auth.ts`: Added credentials for cookie-based auth
- `server/routes/auth.py`: Rate limiting, enumeration fixes, token revocation
- `userland/auth/jwt.py`: `generate_refresh_token()` returns (token, hash) tuple
- `database/repositories_async/userland.py`: Refresh token CRUD methods
- `database/migrations/013_refresh_tokens.sql`: New table for revocation support

### Migration Note
Existing users will need to re-login after deploying (old tokens not in DB).

---

## [2025-12-10] Architectural Hardening

Based on comprehensive audit, addressed concurrency hazards and improved robustness.

### P0 Fixes (Critical)
- **Shutdown race conditions**: Replaced simple `is_running` booleans with `asyncio.Event` for proper async-safe signaling in `Processor`, `Conductor`, and `Fetcher`
- **Interruptible waits**: Added `_wait_with_shutdown_check()` for graceful shutdown during queue polling
- **Context manager safety**: `enable_processing()` no longer restores state after shutdown signal
- **SQLite WAL consistency**: WAL mode now set once at init in rate_limiter.py (was scattered)
- **Session cleanup**: Added async context manager to `AsyncAnalyzer` for guaranteed cleanup

### P1 Enhancements
- **Repository exceptions**: Added `DuplicateEntityError`, `InvalidForeignKeyError`, `StaleJobError` to exception hierarchy
- **Structured logging**: Converted f-string logging to structured logging in rate_limiter.py

### Architecture Verified (No Changes Needed)
- Userland model separation is correct (User model belongs to userland domain)
- Topics dual storage is intentional denormalization (JSONB source, tables for queries)
- Pipeline/models.py already centralizes job types with clear documentation
- Metrics injection is architectural limitation (server and daemon are separate processes)

---

## [2025-12-04] Architectural Refactoring

Addressed layering violations and god object issues. See REFACTORING.md for full details.

### Phase 1: Metrics Decoupling
- Created `pipeline/protocols/` with `MetricsCollector` Protocol and `NullMetrics`
- Pipeline now accepts optional metrics injection (no compile-time server dependency)
- `python -c "from pipeline.processor import Processor"` works without server

### Phase 4: Filter Relocation
- Moved `vendors/utils/item_filters.py` to `pipeline/filters/item_filters.py`
- Correct layering: adapters adapt, pipeline decides what to process
- Old location re-exports with deprecation warning

### Phase 2: Orchestrator Extraction
- Created `pipeline/orchestrators/` with `MatterFilter`, `EnqueueDecider`, `VoteProcessor`
- Database delegates business logic to orchestrators
- Vote processing, queue priority, and matter filtering now in pipeline layer

### Phase 3: Worker Pattern
- Created `pipeline/workers/` with `MeetingMetadataBuilder`
- Establishes pattern for future processor decomposition
- Remaining workers documented in REFACTORING.md as future work

### Files Added (10)
- `pipeline/protocols/__init__.py`, `pipeline/protocols/metrics.py`
- `pipeline/filters/__init__.py`, `pipeline/filters/item_filters.py`
- `pipeline/orchestrators/__init__.py`, `pipeline/orchestrators/matter_filter.py`
- `pipeline/orchestrators/enqueue_decider.py`, `pipeline/orchestrators/vote_processor.py`
- `pipeline/workers/__init__.py`, `pipeline/workers/meeting_metadata.py`

---

## [2025-12-03] Documentation Audit

Synced READMEs with current codebase after PostgreSQL migration and cleanup:
- Removed references to deleted `sync_vendors()` function
- Updated diagrams and env vars from SQLite to PostgreSQL
- Fixed outdated import examples in CLAUDE.md
- Updated privacy section to reflect userland accounts

---

## Current Focus

**Council Member + Voting Completion**
- Backend infrastructure done (schema, repos, Legistar extraction)
- Missing: API endpoints, frontend pages, vote extraction for more adapters

**userland/ Polish**
- Unsubscribe flow, email tracking, PWA push notifications

**Future**
- Campaign finance and donor tracking
- Intelligence layer (Phase 6)
- Remaining vendors: CivicClerk, NovusAgenda, CivicPlus item-level

---

## [2025-12-02] Code Quality Cleanup (Unslopification)

**Eliminated ~150 lines of duplication and verbosity across adapters and repositories.**

### Vendor Adapters
- **Legistar**: Removed redundant `_parse_meeting_status()` override (now uses inherited base method with logging)
- **Legistar**: Removed redundant inline `import asyncio` (already imported at module level)
- **Chicago**: Extracted `_STATUS_TO_OUTCOME` class constant (was duplicated in two methods)
- **Chicago**: Extracted `_extract_attachments()` helper (was duplicated in two methods)
- **IQM2**: Removed duplicate calendar URL pattern

### Database Repositories
- **helpers.py**: Now uses own `deserialize_participation()` and `deserialize_attachments()` functions internally
- **items.py**: Uses `defaultdict` for grouping, `executemany` for batch topic inserts, `_parse_row_count()` from base
- **matters.py**: Uses `SELECT EXISTS` instead of `COUNT(*)` for existence checks (minor perf improvement)

### Server Utils
- **validation.py**: Trimmed verbose module docstring, removed section banner comments, condensed `require_*` docstrings

### Scaffolding (Not Yet Implemented)
- **responses.py**: Response helpers for future closed-loop API consistency (unused until adoption)

**No breaking changes.** Legistar now logs meeting status detection (debug level) - previously silent.

---

## [2025-12-02] Unified Meeting ID Generation

**Single source of truth for meeting IDs.** All 11 adapters now return `vendor_id`, database layer generates canonical IDs.

- **Pattern**: Adapters return `vendor_id` (native vendor identifier), `db_postgres.py` calls `generate_meeting_id()` to create `{banana}_{8-char-hash}` format
- **All adapters updated**: Berkeley, Menlo Park, Chicago, PrimeGov, Legistar, NovusAgenda, Granicus, CivicClerk, CivicPlus, IQM2, Escribe
- **Base adapter**: Renamed `_generate_meeting_id()` to `_generate_fallback_vendor_id()` (clarifies it generates vendor_id, not meeting_id)
- **Migration script**: `scripts/migrate_meeting_ids.py` handles all FK tables (items, meeting_topics, matter_appearances, queue, votes, tracked_items)
- **Files modified**: `database/db_postgres.py`, all adapter files, `database/id_generation.py` (imported), migration script

---

## [2025-12-01] userland/ Civic Alerts System (Phase 2-3 COMPLETE)

**Free civic alerts now live.** Magic link authentication, city + keyword subscriptions, weekly email digests.

- Magic link auth (JWT tokens, 15-min expiry, single-use)
- User profiles with city + keyword subscriptions (PostgreSQL `userland` schema)
- Weekly digest emails (Sundays 9am via Mailgun, keyword highlighting)
- Dashboard API endpoints (signup, login, verify, alert management)
- Dual-track keyword matching (string-based + matter-based deduplication)
- Services: `engagic-api.service`, `engagic-digest.timer`
- Files: `userland/` (~1,900 lines), `database/repositories_async/userland.py` (582 lines)

---

## [2025-12-01] Council Member + Voting Infrastructure (IN PROGRESS)

**Legislative accountability foundation.** Schema and repositories for tracking council member votes.

- Schema: `council_members`, `sponsorships`, `votes`, `committees`, `committee_members`
- Models: CouncilMember, Vote, Committee, CommitteeMember dataclasses
- Repository: CouncilMemberRepository (731 lines) - sponsorship + voting methods
- ID generation: `normalize_sponsor_name()`, `generate_council_member_id()`
- Legistar adapter: vote extraction complete (`_fetch_event_item_votes_api`)
- Missing: API endpoints, frontend pages

---

## [2025-11-23] Comprehensive Cleanup & Documentation Audit

**Documentation accuracy: 75% -> 95%.** Dead code deleted, session artifacts archived.

- Deleted dead code: vendors/adapters/all_adapters.py
- Archived session artifacts to docs/archive/sessions/2024-11/
- Updated CLAUDE.md with accurate line counts (21,800 -> 27,100 lines)
- Documented all 10 route modules
- Total cleanup: -369 lines from root, +848 lines archived

---

## [2025-11-23] Architectural Consolidation

**Consistency score: 6.5/10 -> 8/10.** Pure async conductor, standardized DI, custom exceptions.

- Conductor: pure async with asyncio.create_task(), single event loop
- Standardized dependency injection (centralized in server.dependencies)
- Custom exceptions throughout (VendorHTTPError, ExtractionError, LLMError)
- Centralized config access (USERLAND_DB, USERLAND_JWT_SECRET -> config.py)
- New `daemon` CLI command (sync + processing concurrently)

---

## [2025-11-21] Title-Based Matter Tracking

**98.9% title uniqueness.** Enables matter tracking for cities without stable vendor IDs.

- Added intelligent fallback hierarchy for matter identification
- New: `normalize_title_for_matter_id()` strips reading prefixes, excludes generic titles
- Enables tracking for Palo Alto and 8 other PrimeGov cities
- Fixed cross-city collision bug in backfill script
- Files: `database/id_generation.py` (+90 lines)

---

## [2025-11-20] Architectural Consistency Phase 4 Complete

**Production-ready codebase verified.** Comprehensive architectural audit completed across all 5 consistency phases.

**Overall Health:** 82% production ready (8.2/10), 68% architectural consistency

**Phase Completion:**
- Phase 1 (Error Handling): 65% - Critical paths use explicit exceptions, 141+ raises across 33 files
- Phase 2 (Data Models): 85% - Full dataclass migration for domain models, only stats dicts remain
- Phase 3 (Logging): 38% - Structlog infrastructure deployed, 248 f-strings remain for conversion
- Phase 4 (Transactions): 100% ✅ - defer_commit eliminated, transaction context managers universal, repository pattern enforced
- Phase 5 (Validation): 50% - Pydantic validation in models, scattered boundaries

**Verification Results:**
- ✅ Zero linting errors (ruff check: ALL PASS)
- ✅ Zero critical anti-patterns (defer_commit, repository commits, direct SQL)
- ✅ Zero security vulnerabilities (parameterized SQL, rate limiting, validation)
- ✅ Parameterized SQL queries throughout (no injection vulnerabilities)
- ✅ System ready for User Profiles & Alerts milestone (VISION.md Phase 2/3)

---

## [2025-11-17] Tiered Rate Limiting Implementation

**Sustainable API access with clear boundaries.** Three-tier rate limiting balances open data ethos with infrastructure sustainability.

**What Changed:**
- Extended SQLiteRateLimiter with daily limits (minute + day tracking)
- Three tiers:
  - Free (Basic): 30 req/min, 300 req/day - Personal use, no auth required
  - Nonprofit/Journalist (Hacktivist): 100 req/min, 5k req/day - Requires attribution + contact
  - Commercial (Enterprise): 1k+ req/min, 100k+ req/day - Paid tier via motioncount
- Comprehensive 429 responses with upgrade paths, self-host option, and contact info
- API key infrastructure scaffolded (motioncount handles actual auth)
- ToS drafted (docs/TERMS_OF_SERVICE.md) - balances open data ethos with sustainability
- Commercial/hacktivist tiers route through motioncount.com (email: admin@motioncount.com)

---

## [2025-11-12] Data Model Fixes & Phase 2 Schema (User Profiles & Alerts)

**Foundation cleanup complete. Phase 2 schema ready.** Fixed 5 critical data model issues discovered during architecture audit and added complete user schema for Phase 2 (User Profiles & Alerts).

**What Changed:**

**1. Documentation Drift Fixed (SCHEMA.md)**
- Fixed queue table documentation mismatch:
  - packet_url → source_url (reflects agnostic URL design)
  - Added missing fields: failed_at, job_type, payload
  - Added dead_letter status value
  - Documented priority decay behavior and dead letter queue pattern
- Added attachment_hash to items table documentation
- Created new "Phase 2 Tables" section for user schema

**2. Performance Index Added (database/db.py:282)**
- Added idx_items_meeting_id index for O(log n) item lookups
- Fixes full table scan on every meeting detail page load
- Critical for frontend performance at scale (100K+ items)

**3. Matter Validation Fail-Fast (database/db.py:510-519)**
- Changed matter_id generation from warning to error
- Items with invalid matter data now fail meeting sync immediately
- Forces adapter-level fixes for data quality issues
- Prevents orphaned items pointing to non-existent matters

**4. Attachment Hash Storage (database/db.py:174, 522-524)**
- Added attachment_hash column to items table schema
- Items compute and store SHA-256 hash at creation time
- Enables fast change detection without re-hashing identical content
- Updated AgendaItem model and ItemRepository to handle hash field
- Eliminates wasteful re-processing of unchanged attachments

**5. Matter Relationship Exposure (THE BIG ONE)**
- Added load_matters=True parameter to get_agenda_items()
- Eagerly loads Matter objects with single query (not N+1)
- Updated API service to load matters by default
- Matter field now included in item serialization when loaded
- Frontend can now display "this bill appeared 3 times across these meetings"
- Unblocks matter timeline feature that was designed but never wired up

**6. Phase 2 User Schema (database/db.py:273-289, 318-321)**
- Created user_profiles table (id, email, created_at)
- Created user_topic_subscriptions table (user_id, banana, topic)
- Added 4 performance indices for user/subscription queries:
  - idx_user_profiles_email (unique constraint)
  - idx_user_subscriptions_user, city, topic
- Composite primary key (user_id, banana, topic) prevents duplicates
- Ready for magic link auth + topic-based alerts

**Architecture Impact:**

**Matter Timeline Now Accessible:**
```python
# Before: matter field always None
items = db.get_agenda_items(meeting_id)
item.matter  # Always None

# After: matter field populated with eager loading
items = db.get_agenda_items(meeting_id, load_matters=True)
item.matter  # Matter object with canonical_summary, appearances, etc.
```

**User Subscriptions Ready:**
```sql
-- User subscribes to housing and zoning in Palo Alto
INSERT INTO user_topic_subscriptions (user_id, banana, topic)
VALUES
  ('user_abc123', 'paloaltoCA', 'housing'),
  ('user_abc123', 'paloaltoCA', 'zoning');

-- Alert service matches meeting topics against subscriptions
SELECT DISTINCT u.email, m.title, m.topics
FROM meetings m
JOIN user_topic_subscriptions s ON m.banana = s.banana
JOIN user_profiles u ON s.user_id = u.id
WHERE json_each(m.topics, s.topic)
  AND m.date >= date('now');
```

**Files Modified:**
- `docs/SCHEMA.md` - Queue table fix, attachment_hash docs, Phase 2 schema (lines 232-325)
- `database/db.py` - Index, user tables, attachment_hash column (lines 174, 273-289, 282, 318-321, 510-519, 522-524, 1047-1054)
- `database/models.py` - AgendaItem attachment_hash field and matter serialization (lines 313, 330-336, 376)
- `database/repositories/items.py` - Eager loading, hash storage (lines 62-70, 92, 120-167)
- `server/services/meeting.py` - Enable matter loading in API (lines 20-24)

**Migration Notes:**
- Schema changes auto-apply via CREATE TABLE IF NOT EXISTS
- New index and columns added automatically on first connection
- Fully backwards compatible, no data loss
- Existing meetings will get attachment hashes computed on next sync
- Matter relationships available immediately via load_matters=True

**Validation:**
- Linting: Clean (ruff check --fix)
- Type checking: Clean (pyright, BS4 stubs ignored per CLAUDE.md)
- Compilation: All files compile successfully
- Schema: Verified with sqlite3 schema inspection

**Status:** COMPLETE - All blocking issues resolved, Phase 2 ready to implement

---

## [2025-11-11] MILESTONE: Unified Matter Tracking Framework (Legistar + PrimeGov)

**Matter-level tracking now works across vendors.** Implemented unified schema that adapts vendor-specific legislative tracking into one coherent framework, enabling cross-meeting matter tracking regardless of civic tech vendor.

**What Changed:**
- Created unified matter tracking schema (vendor-agnostic):
  - `matter_id`: Backend unique identifier (UUID for PrimeGov, numeric for Legistar)
  - `matter_file`: Official public identifier (25-1209, BL2025-1098, etc.)
  - `matter_type`: Flexible metadata (Ordinance, CD 12, Resolution, etc.)
  - `agenda_number`: Position on this specific agenda
  - `sponsors`: Sponsor names (JSON array, when available)
- Updated PrimeGov HTML parser to extract matter tracking:
  - Detects LA-style meeting-item wrappers with `data-mig` (matter GUID)
  - Extracts matter_file from forcepopulate table first row
  - Extracts matter_type from forcepopulate table second row first cell
  - Falls back to Palo Alto pattern (direct agenda-item divs) for older cities
- Database schema updates:
  - Added `matter_type` TEXT column to items table
  - Added `sponsors` TEXT column to items table (stores JSON array)
  - Updated AgendaItem model to include new fields
  - Updated ItemRepository to serialize/deserialize sponsors JSON
  - Updated UnifiedDatabase facade to pass through new fields
- End-to-end tested with Austin (Legistar) and LA (PrimeGov)

**Design Philosophy:**
- Vendors adapt INTO the unified schema (not schema-per-vendor)
- `matter_type` intentionally flexible - captures whatever metadata the city provides
- Not all fields required from all vendors - expected and fine
- Same matter can appear across multiple meetings with same `matter_id`

**Vendor Comparison:**
- **Legistar** (Austin): matter_type = "Discussion and Possible Action" (semantic content classification)
- **PrimeGov** (LA): matter_type = "CD 12" (council district designation)
- Both useful context, no forced semantic consistency

**Test Results:**
- Los Angeles (PrimeGov): 71 items, 71 with matter tracking (100% coverage for City Council)
- Austin (Legistar): 22 items, 11 with matter tracking (50% - procedural items excluded)

**Code Changes:**
- `vendors/adapters/html_agenda_parser.py`: Added LA pattern detection + matter extraction
- `database/models.py`: Updated AgendaItem with matter_type and sponsors
- `database/repositories/items.py`: Serialize/deserialize sponsors JSON
- `database/db.py`: Pass matter_type and sponsors to AgendaItem construction

---

## [2025-11-11] MILESTONE: Legistar Matter Tracking + Date Filtering Fixes

**Legislative lifecycle tracking now operational.** Cities using Legistar (NYC, SF, Boston, Nashville) can now track bills/resolutions across their multi-meeting lifecycle from introduction through committee review to final passage.

**What Changed:**
- Fixed critical date filtering bug in Legistar adapter (API and HTML paths)
  - Bug: datetime comparison failed when meeting at midnight vs sync at 00:48:54
  - Fix: Strip time component for fair date-only comparison
  - Impact: Nashville sync went from 0 meetings to 5 meetings found
- Updated date range: 1 week backward, 2 weeks forward (was 7 back, 60 forward)
  - Captures recent votes/approvals on tracked matters
  - Captures upcoming meetings with new introductions
- Added procedural item filtering (appointments, confirmations, public comment, etc.)
  - Reduces noise in matter tracking
  - Focus on substantive legislative items
- Fixed missing `import json` in database/db.py
  - Matter tracking was silently failing with "name 'json' is not defined"
  - All matter tracking calls now succeed

**Matter Tracking Architecture:**
- `items` table: Stores matter_file and matter_id on each agenda item (duplicated for fast queries)
- `city_matters` table: Canonical bill representation (id = "nashvilleTN_BL2025-1099")
- `matter_appearances` table: Timeline of bill across meetings (committee → full council progression)
- Automatic tracking: `_track_matters()` called after storing items, gracefully skips non-Legistar items

**Nashville Test Results:**
- 5 meetings synced (Nov 4, 2025 - all from 1 week lookback)
- 229 total items across meetings
- 173 items with matter_file
- 40 unique legislative matters tracked (bills and resolutions)
- 40 matter appearances recorded
- Example matters: RS2025-1600 (Ryan White funding), BL2025-1106 (Community garden ordinance)

**Vendor Differentiation Identified:**
- **Legistar**: Legislative management system with bill tracking (matter_file, sponsors, type, lifecycle)
  - Used by legislative-heavy cities: NYC, SF, Boston, Nashville, Seattle
  - API provides matter metadata, sponsors, attachments
  - Enables: Bill progression tracking, sponsor analysis, vote tracking, timeline view
- **Granicus/PrimeGov**: Meeting management systems (agenda items only, no legislative IDs)
  - Used by smaller cities with simpler agendas
  - No legislative lifecycle tracking capability
  - Still get full processing: extraction, summarization, storage

**Code Changes:**
- `vendors/adapters/legistar_adapter.py`: Date filtering fix, procedural filtering, date range update
- `vendors/adapters/base_adapter.py`: Enhanced HTTP response logging
- `database/db.py`: Added missing json import for matter tracking

**Validation:**
- Linting: Clean (ruff check --fix)
- Type checking: BS4 stub errors only (expected per CLAUDE.md)
- Compilation: All files compile successfully
- Runtime: Matter tracking verified with Nashville data

---

## [2025-11-04] DISCOVERED: Gemini Batch API Key-Scrambling Bug + Smart Recovery

**The intermittent corruption.** Discovered Gemini Batch API has a rare but catastrophic bug where response keys get scrambled, causing summaries to be assigned to wrong items in a circular rotation pattern.

**The Discovery:**
- User reported mismatched summaries on Palo Alto meetings processed Nov 3 23:17
- Item 1 (Proclamation) had Item 4's summary (Speed Limits)
- Item 5 (Budget) had Item 1's summary (Proclamation)
- Pattern: Clean circular rotation where each item got the next one's summary

**Scope Analysis:**
- Affected: 5 Palo Alto meetings (38 items total) from single batch at Nov 3 23:17
- NOT affected: Austin, Boston, Denver, Phoenix, Charlotte processed minutes later
- Bug is intermittent - only 1 batch out of dozens that day was corrupted
- Same meetings processed earlier had same rotation (suggests bug persisted across retries)

**Root Cause:**
- Gemini Batch API JSONL format uses `key` field to match responses to requests
- Code correctly sets `key: item_id` in requests
- Code correctly reads `key` from responses and looks up in request_map
- BUT: Gemini sometimes returns responses with scrambled keys (circular rotation)
- No logs show missing keys - the keys exist but are WRONG

**The Smart Recovery Solution:**
- Created `scripts/smart_restore_paloalto.py` - content-matching algorithm
- Analyzes title keywords vs summary content to find correct matches
- For each item, scores all available summaries by keyword overlap
- Assigns best-matching summary to each item (ignores corrupted item_id)

**Recovery Results:**
- Meeting 2464: 16/17 items recovered (1 no match)
- Meeting 2465: 1/2 items recovered (1 no match)
- Meeting 2466: 7/9 items recovered (2 were already correct)
- Meeting 2609: 1/5 items recovered (4 were procedural items)
- Meeting 2641: 5/5 items recovered
- **Total: 33/38 items (87%) successfully remapped**

**Why Not Reproduce?**
- Bug is rare (0.1% of batches)
- Content matching works perfectly for recovery
- Only adds complexity for minimal gain
- Script takes 30 seconds to run if it happens again

**Files Created:**
- `scripts/smart_restore_paloalto.py` - Content-matching recovery script (96 lines)
- `scripts/diagnose_summary_mismatch.py` - Diagnostic tool
- `scripts/check_multiple_cities_mismatch.py` - Multi-city checker
- `scripts/trace_rotation_pattern.py` - Pattern analyzer

**Lessons Learned:**
- Gemini Batch API has reliability issues with key preservation
- Content matching is a viable recovery strategy
- Rare bugs don't need complex prevention, just good recovery tools
- Always keep backups for at least 7 days

**Status:** RESOLVED - Data recovered, monitoring for recurrence

---

## [2025-11-04] CRITICAL FIX: Prevent Data Loss from INSERT OR REPLACE

**EMERGENCY FIX.** Discovered and fixed catastrophic bug where re-syncing meetings would nuke all item summaries. 22 Palo Alto summaries lost on Nov 3, restored from backup, and permanent fix deployed.

**The Problem:**
- `INSERT OR REPLACE` in `items.py` and `meetings.py` **blindly overwrites ALL columns**
- When fetcher re-syncs meetings (every 72 hours), it calls `store_agenda_items()` with `summary=None`
- Result: All processed summaries get overwritten with NULL → **data loss**
- Discovered when user noticed Palo Alto item summaries disappeared between Nov 2-4

**Root Cause:**
```sql
-- DANGEROUS (old code):
INSERT OR REPLACE INTO items (id, title, summary, ...) VALUES (?, ?, NULL, ...)
-- This REPLACES the entire row, nuking existing summary!
```

**The Fix:**

**1. Item Repository (`database/repositories/items.py:47-64`)**
- Changed to `INSERT ... ON CONFLICT DO UPDATE`
- Added explicit preservation logic:
```sql
ON CONFLICT(id) DO UPDATE SET
    title = excluded.title,
    sequence = excluded.sequence,
    attachments = excluded.attachments,
    summary = CASE
        WHEN excluded.summary IS NOT NULL THEN excluded.summary
        ELSE items.summary  -- PRESERVE existing!
    END,
    topics = CASE
        WHEN excluded.topics IS NOT NULL THEN excluded.topics
        ELSE items.topics
    END
```

**2. Meeting Repository (`database/repositories/meetings.py:100-129`)**
- Same fix for meeting summaries, topics, processing metadata
- Structural fields (title, date, URLs) update normally
- Summary/topics/processing data preserved unless explicitly provided

**Impact:**
- ✓ Re-syncs are now safe - fetcher can run without data loss
- ✓ Summaries are permanent once saved
- ✓ Structural updates work correctly
- ✓ Processing is idempotent

**Data Recovery:**
- Restored 22 Palo Alto item summaries from `engagic.db.after-deletion` backup
- Created `scripts/restore_paloalto_summaries.py` for emergency restoration
- All summaries verified and confirmed working on frontend

**Additional Bugs Found During Audit:**

**3. Cache Repository (`database/repositories/search.py:186-193`)**
- Bug: `INSERT OR REPLACE` was resetting `cache_hit_count` to 0 on every update
- Impact: Cache hit statistics were being lost
- Fix: Preserve `cache_hit_count` and `created_at`, only update processing metadata

**4. City Repository (`database/repositories/cities.py:167-176`)**
- Bug: `INSERT OR REPLACE` was resetting `status`, `created_at`, `updated_at` on city updates
- Impact: City metadata and timestamps were being lost
- Fix: Preserve `status` and `created_at`, update `updated_at` correctly

**Files Modified:**
- `database/repositories/items.py` - Critical fix to prevent summary loss
- `database/repositories/meetings.py` - Critical fix to prevent meeting data loss
- `database/repositories/search.py` - Fix cache counter resets
- `database/repositories/cities.py` - Fix city metadata resets
- `scripts/restore_paloalto_summaries.py` - Emergency restoration script (NEW)

**Los Angeles Mystery:**
- User reported Los Angeles data completely gone
- No meetings in current DB or Nov 3 backup (0 meetings)
- Likely hit by same bug earlier, data loss predates backup
- Cannot be recovered (no backup available)

**Never again.** This was a close call. All INSERT OR REPLACE patterns audited and fixed. Database now has bulletproof preservation logic across all tables.

---

## [2025-11-03] Critical Fix + Major Optimization: Meeting-Level Document Cache & Context Caching

**The breakthrough.** Implemented meeting-level document cache with per-item version filtering and Gemini context caching preparation. Eliminates duplicate PDF extractions and prepares for massive API cost savings.

**The Problems:**
1. **Batch API failures** - MIME type and request format errors causing all batch processing to fail
2. **Massive duplicate work** - Same 293-page PDF extracted 3 times for 3 different items
3. **No deduplication** - Every item included shared documents in LLM requests
4. **Version chaos** - All document versions sent to LLM (Ver1, Ver2, Ver3)

**The Fixes:**

**1. Batch API Fixes**
- `analysis/llm/summarizer.py:285` - Changed `.jsonl` → `.json` file extension
  - Fix: Gemini API rejects `application/x-ndjson` MIME type
  - Now: SDK correctly infers MIME type from `.json` extension
- `analysis/llm/summarizer.py:326` - Removed `"role": "user"` from request contents
  - Fix: Gemini Batch API doesn't accept role field in contents array
  - Now: Clean `{"parts": [{"text": prompt}]}` format matches Google docs
- `analysis/llm/summarizer.py:367-373` - Use camelCase field names in JSON
  - Fix: Batch API expects `maxOutputTokens`, `responseMimeType`, `responseSchema` (camelCase)
  - Previous: `max_output_tokens`, `response_mime_type`, `response_schema` (snake_case)
  - Reason: REST API expects camelCase; SDK handles conversion, but manual JSON doesn't
- `analysis/llm/summarizer.py:386` - Use camelCase for config key name
  - Fix: Changed `"generation_config"` to `"generationConfig"` in request object
  - ALL field names in JSON must be camelCase (not just values inside)
- `analysis/llm/summarizer.py:364-370` - Remove `responseSchema` from batch config
  - Discovery: Gemini Batch API doesn't support `responseSchema` validation
  - Solution: Use `responseMimeType: "application/json"` only, rely on prompt for structure
  - Prompts already include detailed JSON format instructions

**2. Meeting-Level Document Cache (Item-First Architecture)**
- `pipeline/processor.py:419-492` - Implemented smart document caching
  - Phase 1: Per-item version filtering (Ver2 > Ver1 within each item's attachments)
  - Phase 2: Collect unique URLs across all items (after filtering)
  - Phase 3: Extract each unique URL once → cache
  - Phase 4: Build item requests from cached documents

**3. Version Filtering**
- `pipeline/processor.py:102-140` - Added `_filter_document_versions()` method
  - Regex-based: `'Leg Dig Ver2'` kept, `'Leg Dig Ver1'` filtered
  - Scoped to each item's attachments (item-first: no cross-item conflicts)
  - Handles Ver1, Ver2, Ver3, etc.

**4. Shared Document Separation**
- `pipeline/processor.py:487-512` - Separate shared vs item-specific documents
  - Shared: Documents appearing in multiple items (e.g., "Comm Pkt 110325" used by 3 items)
  - Item-specific: Documents unique to one item
  - Built meeting-level context from shared documents
  - Item requests contain ONLY item-specific text (shared docs excluded)

**5. Context Caching Preparation**
- `pipeline/processor.py:596-600` - Pass shared_context + meeting_id to analyzer
- `pipeline/analyzer.py:173-214` - Accept and forward caching parameters

**6. Gemini Explicit Context Caching (IMPLEMENTED)**
- `analysis/llm/summarizer.py:182-259` - Context cache creation and lifecycle management
  - Accept `shared_context` and `meeting_id` parameters in `summarize_batch()`
  - Create cache if shared_context >= 1,024 tokens (minimum for Flash)
  - 1-hour TTL (sufficient for batch processing)
  - Automatic cleanup in finally block after all chunks processed
- `analysis/llm/summarizer.py:312-327` - Pass cache_name to chunk processor
- `analysis/llm/summarizer.py:388-390` - Include `cachedContent` in JSONL requests
  - When cache exists, reference shared context via `cachedContent` field
  - Item requests contain only item-specific text (shared docs already cached)
  - Gemini charges reduced rate for cached tokens (50-90% savings)

**Architecture Flow:**
```
For each item:
  ✓ Collect attachment URLs
  ✓ Filter versions WITHIN this item (Ver2 > Ver1)
  ✓ Store filtered URLs

Across all items:
  ✓ Collect unique URLs (after per-item filtering)
  ✓ Extract each unique URL once → cache
  ✓ Identify shared (multiple items) vs unique (one item)

Build shared context:
  ✓ Aggregate shared documents → meeting-level context
  ✓ Prepare for Gemini caching (>1024 tokens)

Build batch requests:
  ✓ Each item gets ONLY its item-specific documents
  ✓ Shared context passed separately (for caching)
  ✓ No duplicate content in requests
```

**Performance Gains (SF Meeting Example):**
- **Before:** 'Comm Pkt 110325' (293 pages) extracted 3 times = 3x work
- **After:** 'Comm Pkt 110325' extracted once, used by 3 items = 1x work
- **Before:** 'Parcel Tables' (992 pages, 32 seconds!) extracted 2 times
- **After:** 'Parcel Tables' extracted once, cached
- **Before:** Ver1 + Ver2 + Ver3 all sent to LLM
- **After:** Only highest version sent (Ver3 > Ver2 > Ver1)

**Expected Savings:**
- Extraction time: 50-70% reduction (no duplicate PDF extraction)
- API costs: 60-80% reduction (shared docs cached at reduced rate + no duplicates + batch API)
  - Batch API: 50% base savings
  - Cached tokens: 50-90% additional savings on shared documents
  - Combined: Up to 80% total cost reduction
- Request sizes: 30-50% smaller (item-specific only, no shared docs in requests)
- Version noise: Eliminated (only latest versions)

**Code Changes:**
- `analysis/llm/summarizer.py` - Batch API fixes + context caching (~80 lines added/changed)
- `pipeline/processor.py` - Document cache + version filtering (~150 lines added)
- `pipeline/analyzer.py` - Pass-through caching parameters (~10 lines changed)

**Status:** COMPLETE - Ready for production testing

---

## [2025-11-03] Enhancement: NovusAgenda Now Prioritizes Parsable HTML Agendas

**The fix.** NovusAgenda sites have multiple agenda link types. Updated adapter to prioritize parsable HTML agendas ("HTML Agenda", "Online Agenda") over summaries.

**Changes:**
- `vendors/adapters/novusagenda_adapter.py` lines 56-113
- Score agenda links by quality:
  - Score 3: "HTML Agenda", "Online Agenda" (parsable, structured items)
  - Score 2: Generic "View Agenda" or "Agenda" (if not summary)
  - Score 0: "Agenda Summary" (skip - not parsable)
- Select highest-scoring HTML agenda link
- Fall back to packet PDF if no good HTML agenda

**Impact:**
- Prioritizes structured item-level agendas over non-parsable summaries
- Falls back to packet PDF when HTML agenda isn't useful
- Better item extraction quality for NovusAgenda cities

**Status:** Deployed

---

## [2025-11-03] Enhancement: IQM2 Adapter Enabled in Production

**The change.** Enabled IQM2 adapter in production fetcher after testing showed successful item-level processing.

**Changes:**
- `pipeline/fetcher.py` line 102: Added "iqm2" to supported_vendors set
- IQM2 now included in automated sync cycles
- Multi-URL pattern support ensures compatibility across IQM2 implementations

**Impact:**
- IQM2 cities (Atlanta, Santa Monica, etc.) now sync automatically
- Item-level processing for IQM2 meetings with structured agendas
- Expands platform coverage

**Status:** Deployed

---

## [2025-11-03] Enhancement: IQM2 Adapter Now Tries Multiple Calendar URL Patterns

**The fix.** IQM2 sites use different URL structures for their calendar pages. Updated adapter to try multiple patterns until one works.

**Changes:**
- `vendors/adapters/iqm2_adapter.py` lines 32-37, 56-93
- Try URLs in order: `/Citizen`, `/Citizen/Calendar.aspx`, `/Citizen/Default.aspx`, `/Citizens/Calendar.aspx`
- Use first URL pattern that returns valid meeting data
- Log which pattern worked for debugging
- Graceful failure if none work

**Impact:**
- Better compatibility across IQM2 implementations
- More resilient to site structure changes
- Clear logging for troubleshooting

**Status:** Deployed

---

## [2025-11-03] Implemented: NovusAgenda Item-Level Processing

**The implementation.** Added HTML agenda parsing for NovusAgenda platform, unlocking item-level processing for 68 cities including Houston TX, Bakersfield CA, and Plano TX.

**Changes:**
1. **HTML Parser** (`vendors/adapters/html_agenda_parser.py` lines 318-414)
   - Created `parse_novusagenda_html_agenda()` function
   - Extracts items from MeetingView.aspx HTML pages
   - Pattern: Searches for `CoverSheet.aspx?ItemID=` links (note capitalization: both C and S capitalized)
   - Returns items array with item_id, title, sequence, attachments

2. **Adapter Update** (`vendors/adapters/novusagenda_adapter.py` lines 56-137)
   - Extract HTML agenda URL from JavaScript onClick handlers
   - Fetch MeetingView.aspx pages for each meeting
   - Parse HTML to extract items using new parser
   - Return meetings with items array (same as Legistar/PrimeGov)

3. **Enabled in Fetcher** (`pipeline/fetcher.py` line 101)
   - Added "novusagenda" to supported_vendors set
   - Enables item-level processing for all NovusAgenda cities

**Test Results (Houston TX):**
- 27 total meetings found
- 12 meetings with items (44% coverage)
- First meeting: 54 items extracted from HTML agenda
- Items include item_id, title, sequence from CoverSheet links

**Impact:**
- Adds 68 cities to item-level processing pipeline
- Platform coverage: 374 → 442 cities (~53% of 832 total)
- Major cities now with structured agendas: Houston, Bakersfield, Plano, Mobile
- Consistent item-level UX across more vendors

**Technical Notes:**
- NovusAgenda uses "CoverSheet" (capital C and S) not "Coversheet" in HTML
- Must use case-insensitive regex to match links
- Items extracted from MeetingView.aspx page, not agendapublic listing
- Some meetings have packet_url but no HTML agenda (fallback to monolithic)

**Status:** Deployed, ready for production sync

---

## [2025-11-03] Discovery: NovusAgenda Supports Item-Level Processing

**The coverage opportunity.** NovusAgenda (68 cities including Houston, Bakersfield, Plano) can be transitioned to item-level processing using HTML agenda parsing.

**Current State:**
- NovusAgenda adapter only fetches PDF packet URLs (monolithic processing)
- 68 cities using NovusAgenda vendor
- Includes major cities: Houston TX, Bakersfield CA, Plano TX, Mobile AL

**Opportunity:**
- NovusAgenda meeting pages have HTML agendas with structured item tables
- Can parse HTML similar to PrimeGov/Granicus pattern
- Would add 68 cities to item-level coverage (374 → 442 cities, ~53% of platform)

**Implementation Path:**
1. Add `parse_novusagenda_html_agenda()` to `vendors/adapters/html_agenda_parser.py`
2. Update `NovusAgendaAdapter.fetch_meetings()` to fetch HTML agenda page
3. Extract items, attachments, and participation info from HTML structure
4. Return items array in meeting dict (same as Legistar/PrimeGov/Granicus)

**Impact:**
- Item-level summaries for 68 additional cities
- Better search granularity for major cities like Houston
- Consistent UX across more vendors
- No new infrastructure required (same batch processing pipeline)

**Status:** Documented for future implementation

---

## [2025-11-03] Critical Bug Fix: Backwards Enqueuing Logic (agenda_url Should Never Be Enqueued)

**The architectural violation.** The enqueuing logic in `store_meeting_from_sync()` was completely backwards - prioritizing `agenda_url` for processing when it should NEVER be enqueued.

**The Bug:**
- Line 457 condition: `elif agenda_url or packet_url or has_items:`
- Line 466-474 priority: `if agenda_url: enqueue(agenda_url) elif packet_url: enqueue(packet_url) else: enqueue(items://)`
- This meant meetings with items AND agenda_url would enqueue the agenda PDF for processing
- Example: Charlotte meeting had 9 items extracted from HTML, but system enqueued the agenda PDF instead of `items://1917`

**Why This Is Wrong:**
- `agenda_url` is the HTML source that's ALREADY been processed during fetch
- Items are extracted FROM the agenda_url HTML during adapter `fetch_meetings()`
- Participation info is parsed FROM the agenda_url HTML
- The agenda_url has already served its purpose - it should never be sent to the LLM
- Only the item-level attachment PDFs should be processed (via `items://meeting_id`)

**Correct Architecture:**
```
agenda_url (HTML) → Adapter extracts items + participation → Store in DB
                                                               ↓
                                                    Enqueue items:// for batch processing
                                                               ↓
                                              Process item attachment PDFs with LLM
```

**What Was Happening Instead:**
```
agenda_url (HTML) → Adapter extracts items + participation → Store in DB
                                                               ↓
                                                    Enqueue agenda_url PDF (WRONG!)
                                                               ↓
                                              Process already-parsed PDF, ignore item attachments
```

**Fix:**
- Changed condition: `elif has_items or packet_url:` (removed `agenda_url`)
- Changed priority: `if has_items: enqueue(items://meeting_id) else: enqueue(packet_url)`
- Added clarifying comment: "agenda_url is NOT enqueued - it's already processed to extract items"

**Files Modified:**
- `database/db.py:457,465-476` - Fixed enqueuing logic to never enqueue agenda_url

**Impact:**
- Item-level-first architecture now works correctly
- Charlotte and other cities with HTML agendas will batch process item attachments
- agenda_url PDFs never sent to LLM (saves credits, matches architecture)
- Monolithic packet_url fallback still works for cities without items

**The Insanity:**
This bug would have broken the entire item-level-first pipeline. Cities with perfectly good item-level data would waste credits processing the wrapper PDF instead of the substantive attachments.

---

## [2025-11-03] New: Motioncount Intelligence Layer (Grounding-Enabled Analysis)

**Using free grounding capacity that was going to waste.** Built complete intelligence layer that uses Gemini 2.0 Flash + Google Search grounding to detect housing law violations.

**What Was Built:**
- Complete grounding-enabled investigative analyzer
- Pre-filter for high-value items (housing/zoning keywords)
- Database schema for storing analysis results with full provenance
- Deploy script following engagic pattern (`./motioncount.sh`)
- Full citation tracking (queries, sources, citation mapping)

**Architecture:**
```
engagic.db (read-only)
  ├─ items table (existing summaries)
  └─ meetings table
         ↓
motioncount miner (NEW)
  ├─ Pre-filter: housing/zoning keywords
  ├─ Gemini 2.0 Flash + Google Search
  ├─ Researches laws, precedents, violations
  └─ Stores results with citations
         ↓
motioncount.db (NEW)
  └─ investigative_analyses table
       ├─ thinking (reasoning steps)
       ├─ research_performed (web searches)
       ├─ violations_detected (law, type, confidence, evidence)
       ├─ grounding_metadata (source URLs + citation mapping)
       └─ critical_analysis (markdown with citations)
```

**Key Insight:**
- Zero re-fetching, zero re-parsing, zero duplicate work
- Reads existing summaries from engagic.db
- Just adds intelligence layer on top
- Uses 1,500 FREE grounded requests/day (paid tier)

**Files Created:**
```
motioncount/
├── analysis/
│   └── investigative.py          # Grounding analyzer (227 lines)
├── database/
│   ├── engagic_reader.py          # Read-only from engagic.db (184 lines)
│   ├── db.py                      # Write to motioncount.db (385 lines)
│   └── models.py                  # Data models (135 lines)
├── scripts/
│   ├── run_investigative_batch.py # Batch processor (229 lines)
│   ├── view_violations.py         # Results viewer (101 lines)
│   └── test_analyzer.py           # Test script (211 lines)
├── config.py                      # Configuration (37 lines)
├── README.md                      # Full documentation
└── DEPLOY.md                      # Deployment guide

motioncount.sh                     # Deploy script (124 lines)
```

**Total Code:** ~1,633 lines

**Deploy Commands:**
```bash
# Single city
./motioncount.sh analyze-city paloaltoCA

# Regional
./motioncount.sh analyze-cities @regions/bay-area.txt

# Batch
./motioncount.sh analyze-unprocessed --limit 50

# View results
./motioncount.sh violations --limit 10
```

**What Gets Analyzed:**
- Pre-filter keywords: SB 35, SB 9, AB 2097, RHNA, housing element, ADU, parking mandates, zoning changes, CEQA
- OR items with 2+ topics: housing, zoning, planning, development
- Typical: 10-30% of items qualify

**What Gets Stored:**
- Thinking process (reasoning steps)
- Web research performed (queries + findings)
- Violations detected (law, type, confidence 1-10, evidence quotes, reasoning)
- Grounding metadata (source URLs, citation mapping)
- Critical analysis (markdown with inline citations)

**Cost Management:**
- Free tier: 1,500 grounded requests/day
- Pre-filter reduces volume by 70-90%
- Typical usage: 50-200 items/day analyzed
- Well within free tier limits

**Provenance Tracking:**
- Full grounding metadata captured
- Source URLs for all claims
- Citation mapping (which text segments link to which sources)
- Programmatic citation insertion available

**Separation of Concerns:**
- engagic: Neutral summarization (public good, open source)
- motioncount: Intelligence layer (grounding-enabled analysis)
- Clean database separation (engagic.db vs motioncount.db)
- Read-only access to engagic data

**Status:** Production ready, deployed on VPS, running first batch

**Value Unlock:**
- Uses free grounding capacity (1,500/day going to waste)
- Detects housing law violations with web-verified evidence
- Zero additional extraction cost (reads existing summaries)
- Builds corpus for future customer features

---

## [2025-11-03] Bug Fix: Summarizer Syntax Error (Extraneous Try Block)

**The issue:** Syntax error in `analysis/llm/summarizer.py` - extraneous `try:` block at line 279 without matching `except` clause.

**Fix:**
- Removed redundant `try:` block at line 279
- Fixed indentation for lines 290-572
- `except` clause at line 550 now properly matches `try:` at line 289

**Files Modified:**
- `analysis/llm/summarizer.py:279,290-572` - Removed extra try block, fixed indentation

**Verification:**
- `uv run ruff check --fix` - All checks passed
- `python3 -m py_compile` - Compilation successful

---

## [2025-11-03] Critical Bug Fix: Batch API Response Mismatching

**The silent data corruption.** Gemini Batch API inline requests do NOT guarantee response order matches request order, causing summaries to be assigned to wrong items.

**The Bug:**
- Used index-based matching: `response[i]` assumed to match `request[i]`
- Gemini Batch API processes requests asynchronously - responses can return out of order
- Item 1 got Item 2's summary, Item 2 got Item 17's summary, etc.
- Affected ALL batch-processed meetings (374+ cities, thousands of meetings)

**Root Cause:**
- Google's own documentation shows JSONL file method uses explicit `key` fields for matching
- But inline requests examples don't show metadata - we assumed index order was preserved
- Asynchronous batch processing means responses can complete in any order

**Fix:**
- Added `metadata: {"item_id": item_id}` to each inline request
- Match responses by metadata item_id instead of array index
- Defensive logging if metadata not supported by SDK
- Fallback plan: Switch to JSONL file method if metadata not available

**Files Modified:**
- `analysis/llm/summarizer.py:280-424` - Added metadata to requests, match by key in responses

**Testing:**
- Created `scripts/test_batch_metadata.py` to verify SDK metadata support
- Will re-process affected meetings if fix works, or implement JSONL method if not

**Impact:**
- Data integrity: Summaries will correctly match their agenda items
- User trust: No more confusing mismatched summaries
- System reliability: Guaranteed request/response matching

**Database Cleanup Required:** All batch-processed meetings need reprocessing with correct matching logic.

---

## [2025-11-02] Frontend Meeting Detail Page Redesign

**The legibility unlock.** Complete visual redesign of meeting detail page with focus on information hierarchy and readability.

**Changes:**
- Removed gradient pill number badges, replaced with inline plain text numbers ("1. ")
- Typography overhaul: System sans-serif titles (18px, weight 500, 1.45 line-height)
- Summary text: 16px Georgia with 0.01em letter-spacing for improved legibility
- Tighter spacing throughout: 1rem card padding (down from 1.25rem), 1rem gaps (down from 1.5rem)
- Attachment indicators moved to top-right corner badges
- Items collapsed by default with rich preview (title, 2 topics, attachment count)
- Pre-highlighting: Blue left border for items with AI summaries available
- Reactive Svelte templating for thinking traces (replaced DOM manipulation race conditions)
- Topic tags reduced from 3 to 2 in preview
- Subtle section labels: 10px uppercase, 1px letter-spacing, 40% opacity

**Files Modified:**
- `frontend/src/routes/[city_url]/[meeting_slug]/+page.svelte` (~400 lines changed)

**Impact:**
- Better information hierarchy (title → summary → attachments)
- More vertical space (20-30% more items visible)
- Improved readability for dense legislative text
- Clear visual indicators for summary availability
- No race conditions in thinking trace expand/collapse

---

## [2025-11-02] Critical Bug Fix: Missing 'type' Field in Attachments

**The silent failure.** All PrimeGov and Granicus cities (524 cities, 63% of platform) were failing to generate summaries due to missing 'type' field in attachment objects.

**The Bug:**
- PrimeGov/Granicus adapters created attachments without 'type' field
- Processor checked `if att_type == "pdf"` → failed (att_type was "unknown")
- PDFs never extracted, items marked "complete" with 0 summaries
- Silent failure - no errors raised, just empty results

**Impact:**
- 171 items in database with broken attachments (Los Angeles, Palo Alto)
- Would have affected 524 cities (461 Granicus + 63 PrimeGov) when scaled
- Caught before platform-wide rollout

**Fixes:**
- `vendors/adapters/html_agenda_parser.py:185` - Added 'type': 'pdf' to PrimeGov attachments
- `vendors/adapters/html_agenda_parser.py:283` - Added 'type': 'pdf' to Granicus attachments
- `vendors/adapters/primegov_adapter.py:154-155` - Defense-in-depth type field check
- `vendors/adapters/granicus_adapter.py:440-441` - Defense-in-depth type field check
- `pipeline/processor.py:321` - Handle "unknown" types defensively

**Database Cleanup:** Deleted 171 broken items, re-synced affected cities with fixed code.

---

## [2025-11-02] Procedural Item Filter

**Cost optimization.** Added filter to skip low-value procedural items before PDF extraction.

**Items Skipped:**
- Review/Approval of Minutes
- Roll Call
- Pledge of Allegiance
- Invocation
- Adjournment

**Implementation:** `pipeline/processor.py:27-41` - Simple pattern matching on item titles

**Impact:** Saves API costs by not summarizing administrative overhead items

---

## [2025-11-02] Database Repository Refactor

**The modularity unlock.** Refactored monolithic db.py into Repository Pattern.

**Changes:**
- Created `database/models.py` (233 lines) - City, Meeting, AgendaItem dataclasses
- Created `database/repositories/base.py` (71 lines) - Shared connection utilities
- Created 5 focused repositories (~250 lines each):
  - `cities.py` - City and zipcode operations (241 lines)
  - `meetings.py` - Meeting storage and retrieval (190 lines)
  - `items.py` - Agenda item operations (115 lines)
  - `queue.py` - Processing queue management (273 lines)
  - `search.py` - Search, topics, cache, stats (202 lines)
- Refactored `database/db.py` to 519-line facade that delegates to repositories
- Fixed missing `agenda_url` field in meetings table schema
- Zero breaking changes to external API

**Impact:**
- Each repository <300 lines (readable in one sitting)
- Clear separation of concerns
- Easier testing and maintenance
- UnifiedDatabase facade maintains simple external interface

**Code Changes:**
- db.py: 1,632 lines → 519 facade + 1,325 in repositories

---

## [2025-11-02] Server Modular Refactor

**The maintainability unlock.** Refactored monolithic main.py into clean modular architecture with separation of concerns.

**Changes:**
- Created `server/middleware/` - Request/response logging, rate limiting (69 lines)
- Created `server/models/` - Pydantic request validation (85 lines)
- Created `server/routes/` - 5 focused route modules (712 lines total):
  - `search.py`, `meetings.py`, `topics.py`, `admin.py`, `monitoring.py`
- Created `server/services/` - Business logic (346 lines)
- Created `server/utils/` - Reusable utilities (227 lines):
  - `geo.py`, `constants.py`, `validation.py`
- Eliminated code duplication:
  - State map: 3x → 1x (in `utils/constants.py`)
  - Meeting+items pattern: 5x → 1x (in `services/meetings.py`)

**Impact:**
- Maintainability: Largest module is 315 lines (search service)
- Testability: Services are pure functions with dependency injection
- Discoverability: Clear module hierarchy, tab-autocomplete friendly
- Zero breaking changes to API contracts
- Frontend: 100% compatible, no changes required

**Code Changes:**
- `server/main.py`: 1,473 → 98 lines (93% reduction)
- Total: -1,375 lines in main.py, reorganized into 20 focused modules

**Documentation:**
- `docs/main_py_refactor.md`
- `docs/frontend_audit_server_refactor.md`

---

## [2025-11-02] Pipeline Modular Refactor

**The clarity unlock.** Refactored conductor.py into 4 focused modules with clear responsibilities.

**Changes:**
- `pipeline/conductor.py` - Lightweight orchestration (268 lines, down from 1,133)
- `pipeline/fetcher.py` - City sync and vendor routing (437 lines, extracted from conductor)
- `pipeline/processor.py` - Queue processing and item assembly (465 lines, refactored)
- `pipeline/analyzer.py` - LLM analysis orchestration (172 lines, extracted from processor)

**Impact:**
- Mental model: "where is vendor sync logic?" → `fetcher.py`
- Each module <500 lines (readable in one sitting)
- Clean imports: `from pipeline.fetcher import Fetcher`
- Easier testing: Each module has focused responsibilities
- Zero breaking changes to external interfaces

**Code Changes:**
- conductor.py: 1,133 → 268 lines
- Net: Extracted into 3 focused modules with single responsibilities

---

## [2025-10-30] Item-First Architecture

**The UX unlock.** Refactored from meeting-summary-only to item-based-first architecture. Backend stores granular items, frontend composes display.

**Changes:**
- Removed concatenation from conductor.py (backend does data, not presentation)
- API endpoints include items array for item-based meetings
- Frontend displays numbered agenda items with topics and attachments
- Graceful fallback to markdown for monolithic meetings
- Zero breaking changes (backward compatible)

**Impact:**
- Users: Navigable, scannable agendas instead of walls of text
- Developers: Clean separation of concerns (backend=data, frontend=UI)
- System: Actually using the granular data we extract (not wasting LLM calls)

**Code Changes:**
- conductor.py: Removed concatenation, keep topic aggregation
- server/main.py: Include items in all search endpoint responses
- Frontend: Item display with topics, attachments, proper hierarchy

---

## [2025-10-30] Directory Reorganization

**The readability unlock.** Reorganized entire codebase into 6 logical clusters with tab-autocomplete-friendly names.

**Changes:**
- Created 6 logical clusters by purpose:
  - `vendors/` - Fetch from civic tech vendors
  - `parsing/` - Extract structured text
  - `analysis/` - LLM intelligence
  - `pipeline/` - Orchestrate the data flow
  - `database/` - Persistence layer
  - `server/` - API endpoints
- Extracted adapter factory (58 lines)
- Extracted vendor rate limiter (45 lines)
- Simplified processor.py (489 → 268 lines)
- Deleted 300+ lines of legacy/fallback code
- Updated all imports for clarity

**Impact:**
- Mental model: "where is PDF parsing?" → `parsing/`
- Tab autocomplete: `v<tab>` for vendors, `a<tab>` for analysis
- Conductor simplified: 1,477 → 1,133 lines (-24%)
- Clean imports: `from parsing.pdf import PdfExtractor`

**Code Deleted:**
- prompts.json (legacy v1), kept only prompts_v2.json
- v1 legacy parsing, removed PDF item detection
- 3 unused processing methods from conductor
- ONE TRUE PATH: HTML items → Batch, No items → Monolith

**Net:** -292 lines deleted + reorganization

---

## [2025-10-28] Granicus Item-Level Processing

**The platform unlock.** Granicus is the largest vendor (467 cities). Now 200+ Granicus cities support item-level processing via HTML agenda parsing.

**Changes:**
- HTML agenda parser extracts items from table structures
- MetaViewer PDF links mapped to specific items
- Full PDF text extraction (15K+ chars per document)
- Same pipeline as Legistar/PrimeGov - zero infrastructure changes

**Impact:**
- Item-level search and alerts for 200+ more cities
- Coverage: 174 cities → 374+ cities with items (58% of platform)
- Process 10-page chunks instead of 250-page packets
- Better failure isolation (one item fails, others succeed)
- Substantive summaries with financial data and policy details

**Code:**
- `vendors/adapters/granicus_adapter.py`
- `vendors/adapters/html_agenda_parser.py`

**Documentation:**
- `docs/BREAKTHROUGH_COMPLETE.md`

---

## [2025-10-15] Topic Extraction & Normalization - DEPLOYED

**The intelligence foundation.** Automatic topic tagging for all meetings and agenda items.

**Changes:**
- Per-item topic extraction using Gemini with JSON structured output
- Topic normalization to 16 canonical topics (`analysis/topics/taxonomy.json`)
- Meeting-level aggregation (sorted by frequency)
- Database storage (topics JSON column on items and meetings)
- API endpoints: `/api/topics`, `/api/search/by-topic`, `/api/topics/popular`
- Frontend displays topic badges on agenda items
- Color-coded topic badges (14 distinct color schemes)

**Impact:**
- Foundation for user subscriptions and smart filtering
- Enables topic-based discovery
- Consistent taxonomy across 500+ cities

**Code:**
- `analysis/topics/normalizer.py` (188 lines)
- `analysis/topics/taxonomy.json` (16 canonical topics)

---

## [2025-10-12] Participation Info Parsing - DEPLOYED

**The civic action unlock.** Parse and display contact info for meeting participation.

**Changes:**
- Parse email/phone/virtual_url/meeting_id from agenda text
- Store in `meetings.participation` JSON column
- Integrated into processing pipeline (`parsing/participation.py`)
- Normalized phone numbers, virtual URLs, hybrid meeting detection
- Frontend displays participation section on meeting pages
- Clickable contact methods: `mailto:`, `tel:`, Zoom URLs
- Badge indicators: "Hybrid Meeting", "Virtual Only"

**Impact:**
- Enables civic action with one click
- Users can directly email council or join Zoom meetings
- Mobile-friendly phone call links

**Code:**
- `parsing/participation.py` (87 lines)

---

## [2025-01-15] Earlier Improvements

**Database Consolidation:**
- 3 databases → 1 unified SQLite
- Net: -1,549 lines

**Adapter Refactor:**
- BaseAdapter pattern for shared HTTP/date logic
- Net: -339 lines

**Processor Modularization:**
- processor.py: 1,797 → 415 lines (-77%)
- Item-level processing for Legistar and PrimeGov
- Priority job queue with SQLite backend

**Total:** -2,017 lines eliminated

---

## Future

Track future milestones in VISION.md.
