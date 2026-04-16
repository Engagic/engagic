# Agenda Chunker

Extracts structured agenda items from municipal meeting PDFs. Works across vendors
(Granicus, Legistar, CivicPlus, CivicClerk, etc.) by operating on the PDF itself
rather than any vendor-specific API.

Two implementations live side by side:

| File | Philosophy |
|---|---|
| `agenda_chunker.py` (v1) | **Root-to-leaf.** Find item headers by regex, then look for content/links below them. |
| `agenda_chunker_v2.py` (v2) | **Leaf-to-root.** Find invariant anchors (hyperlinks, TOC page boundaries, internal page-jumps) first, then walk back to discover structure. |

v2 imports v1's shared helpers (`_Attachment`, `_extract_links`, `_is_section_header`,
etc.); it's a different dispatcher over the same primitives, not a rewrite from
scratch.

## Who picks which

All adapter callers route through `base_adapter_async._parse_pdf_bytes` (or
`_parse_packet_pdf`, which wraps it). That function takes a `force_method` and
dispatches:

| `force_method` | Behavior |
|---|---|
| `"toc"` | v2 TOC path only |
| `"v2_url"` | v2 URL path only |
| `"url"` | v1 URL path. If v1 returns 0 items, falls back to v2 auto. |
| `None` (auto) | v2 auto. If v2 returns 0 items, falls back to v1 auto. |

The `"url"` fallback to v2 was added because some Granicus cities (e.g. Winter
Springs FL) use 3-digit section-prefixed item numbers (`300.`, `400.`, `500.`)
that don't match v1's item-header regex even after the regex was bumped from
`\d{1,2}\.` to `\d{1,3}\.`. V2's anchor-first approach doesn't depend on the
item number pattern and picks them up.

Higher-level helpers in `base_adapter_async`:

- **`_parse_pdf_response(response, force_method=...)`** — parse a pre-fetched PDF
  response.
- **`_parse_packet_pdf(url, force_method=...)`** — download a PDF and parse it.
- **`_chunk_agenda_then_packet(agenda_url, packet_url, ...)`** — two-step helper
  used by several adapters: tries `agenda_url` with v2_url → v1 url, then
  `packet_url` with `toc`. Also runs `_resolve_sub_attachments` on the agenda
  results to follow staff-report cover PDFs and pull out embedded exhibit links.

## V1 parse paths

Dispatch logic in `_parse_agenda_internal` (line ~1470) picks among these based
on the PDF's structure:

### `url` — URL-based
For PDFs with no useful bookmark tree but with hyperlinked attachment URLs
embedded in the agenda text.

1. Extract all text lines with font metadata (bold, size, position).
2. Extract all URI links from every page.
3. Detect agenda items via `_is_likely_item_header`.
4. Assign each attachment URL to the nearest preceding item by page / y-position.
5. Unassigned links go to `orphan_links`.

Common with: Legistar-generated agendas, most URL-anchored Granicus agendas
(Ontario CA, Nashville, Santa Monica).

### `toc_hierarchical` — 2-level TOC: items on agenda pages, memos below
L1 entries are agenda items clustered on the first few pages; L2 entries are
embedded staff memos/reports on subsequent pages.

1. Identify the "agenda page cluster" (pages where L1 bookmarks point).
2. Parse item numbers and titles from L1 bookmark text.
3. For each L2 child, extract memo page range and pull structured fields
   (SUBJECT, SUMMARY, FISCAL INFORMATION, RECOMMENDED ACTION, Submitted by).
4. Assign memo `full_text` as the item's `body_text`.

Common with: Cedar Park TX, some Granicus packets with bookmark outlines.

### `toc_flat` — flat TOC, one bookmark per page
L1 entries each point to a distinct page; no hierarchy.

1. Determine which pages are "agenda" vs. content pages.
2. Run text-based item detection on agenda pages (same logic as URL path).
3. Extract memo content from each TOC entry beyond the agenda.
4. Fuzzy-match memos to items via `SequenceMatcher` + keyword overlap
   (threshold 0.25).
5. Unmatched memos → `orphan_memos`.
6. If text detection finds nothing, fall back to `_build_items_from_toc_entries`,
   treating each entry as an item directly.

Common with: packet PDFs with flat bookmark lists like `01a Claims and Payroll`,
`03 AB Cross Connection Control`.

### `toc_deep_hierarchical` — 4-level TOC
L1 = root, L2 = sections, L3 = items, L4 = attachments.

Agenda text lives on the first few pages where L2/L3 entries cluster. L4 entries
point to attachment pages deeper in the document. Stops at the second L1 entry
(typically "Appendix") to avoid parsing the document-navigation TOC.

Common with: Escribe-generated agenda packets.

### `toc_document_bundle` — L1 = agenda + attachment bundles
First L1 covers the agenda text (1–3 pages with numbered items). Subsequent L1
entries mark attachment documents with virtual L2 filename bookmarks and real
L3+ page ranges.

1. Parse items from the agenda pages.
2. Collect L2 attachment documents and extract body text from their page ranges.
3. Match attachments to items by content similarity.

## V2 parse paths

Dispatch in `_parse_v2_internal` (line ~824):

### `v2_url` — anchor-first URL clustering
1. Collect all attachment-like links from the document.
2. Cluster links by vertical proximity (new cluster starts on page change or gap
   > 2.5× median line height).
3. For each cluster, walk backwards through text lines to find the heading above
   it. That heading becomes the item title.

No item-header regex required. Handles numbered items, 3-digit numbers, section-
prefixed numbers, and unnumbered items equally because the anchors are the
invariant, not the numbering.

### `v2_pageref` — internal page-jump boundaries
Agenda pages contain `kind=4` PDF internal-page links ("Page XX" references) that
jump deep into the packet. Each internal link's target page becomes an item
boundary.

Runs when a doc has ≥3 internal page references on the agenda pages, no
meaningful attachment URLs, and >10 pages total. The fallback when there's
neither a clean TOC nor clickable attachments.

### `v2_toc` — page-range slicing
Uses PDF bookmark page boundaries as slicing points. Each bookmark range becomes
one item; no title format requirements.

Preferred for any doc with a multi-page TOC (>10 pages + has bookmarks). The
auto-dispatch picks v2_toc over v1's TOC variants because v2 handles hierarchy
edge cases and orphan-attachment grouping more cleanly.

## Path selection logic

V2's `_detect_parse_path` (v2 line ~127) decides between its three modes:

```
has_toc = len(real_entries) >= 3 and len(distinct_pages) >= 2
has_links = first 10 pages have attachment-like URLs
has_pagerefs = first 10 pages have ≥3 internal kind=4 page links

if has_links and page_count > 10:   # large packet with URL links on agenda
    → url_then_toc if has_toc else url
if has_pagerefs and page_count > 10:
    → pageref
if has_toc:                          → toc
if has_links:                        → url
else:                                → empty
```

V1's equivalent dispatcher (`_parse_agenda_internal`) uses similar heuristics but
separates `toc_hierarchical` / `toc_flat` / `toc_deep_hierarchical` /
`toc_document_bundle` by the shape of the bookmark tree (L1/L2/L3/L4 fan-out).

## Known layouts → which chunker wins

| Layout | Example city | Best path |
|---|---|---|
| URL-anchored, 1–2 digit items | Ontario CA | v1 `url` |
| URL-anchored, 3-digit items | Winter Springs FL | v2 `v2_url` (v1 `url` falls back) |
| 2-level TOC, items/memos | Cedar Park TX | v2 `v2_toc` (v1 `toc_hierarchical` works too) |
| 4-level TOC (L1=root, L2=section, L3=item, L4=att) | Escribe packets | v1 `toc_deep_hierarchical` |
| Internal page-jump anchored | Large pagination-heavy packets | v2 `v2_pageref` |
| Flat TOC with memos | Generic packet PDFs | v1 `toc_flat` or v2 `v2_toc` |

## Known gaps

- **3-level TOC where items are at L2** (e.g. San Benito TX: L1 = section,
  L2 = item, L3 = attachment). Neither chunker handles this. V1's `toc_hierarchical`
  expects items at L1; v1's `toc_deep_hierarchical` expects items at L3. V2's
  `v2_toc` promotes L1 entries (section headers) as pseudo-items. Needs either
  a new v1 variant or a "pick the level with most entries" heuristic in v2.
- **Corrupted / mis-encoded page text.** Some PDFs have broken font CMaps that
  make `page.get_text()` return megabytes of garbage. A 200KB per-page cap in
  `parsing/pdf.py` prevents the MemoryError this used to cause, but the resulting
  truncated text is useless for summarization.
- **V2 misaligning URL-anchored agendas with strong section formatting.** Seen
  on Ontario CA before `force_method="url"` was added. V2 split items on
  stylistic boundaries instead of on agenda-number boundaries, producing 24
  misaligned items where v1 produced 16 correct ones.

## Item detection (v1)

`_is_likely_item_header` and `ITEM_NUM_RE` (line ~97) recognize:

| Pattern | Examples |
|---|---|
| Resolution/ordinance | `2026-68` |
| Dotted sub-items | `4.3`, `6.1.2`, `1.2.3.4`, `300.1` |
| Legistar sub-items | `2.a`, `3.b`, `300.a` |
| CivicPlus letter-digit | `H.1`, `F.1` |
| Parenthesized | `(1)`, `(100)`, `(a)` |
| Numbered | `1.`, `2.`, `300.` |
| Lettered | `A.`, `B.`, `a.`, `b.` |
| Roman | `I.`, `II.`, `IV.` |

Heuristics:
- Sub-items (containing `.`) are always treated as items.
- Standalone numbers require being inside a known section (CONSENT, PUBLIC
  HEARINGS, etc.) and having a title on the next line(s).
- Case numbers (`CUP-2024-001`, `ZA 25-001`) and consent prefixes
  (`CONSENT FOR APPROVAL`) are strong item signals.
- Bold or mostly-uppercase text with a number prefix is treated as an item.

V2 does not use this regex — it starts from anchors and walks back to find
whatever heading is above, whether or not it has a number.

## Section detection

~40 patterns for common municipal section headers (CONSENT CALENDAR, PUBLIC
HEARINGS, ADJOURNMENT, etc.). Matched via regex against bold/uppercase lines.
Items inherit the current section. Shared between v1 and v2 via
`_is_section_header` / `_extract_section_name`.

## Output format

Both chunkers return the same dict shape:

```python
from vendors.adapters.parsers.agenda_chunker import parse_agenda_pdf
from vendors.adapters.parsers.agenda_chunker_v2 import parse_agenda_pdf_v2

result = parse_agenda_pdf("path/to/agenda.pdf")          # or parse_agenda_pdf_v2
```

```python
{
    "items": [
        {
            "vendor_item_id": "4.3",
            "title": "Approve Agreement with ...",
            "sequence": 1,
            "agenda_number": "4.3",
            "body_text": "...",          # memo full_text (TOC) or coversheet (URL)
            "matter_file": "2024-001",   # extracted if present
            "attachments": [
                {"name": "Staff Report", "url": "https://...", "type": "pdf"}
            ],
            "metadata": {
                "section": "CONSENT CALENDAR",
                "recommended_action": "Adopt Resolution No. ...",
                "parse_method": "toc_hierarchical",  # or v2_url, v2_toc, etc.
                "page_start": 3,
                "page_end": 5,
                "memo_count": 1,
                "memo_pages": 3
            }
        }
    ],
    "metadata": {
        "body_name": "City Council",
        "meeting_date": "March 26, 2026",
        "meeting_type": "Regular Meeting",
        "page_count": 42,
        "parse_method": "toc_hierarchical"  # which path produced this result
    },
    "orphan_links": [...],   # links not assigned to any item (URL path)
    "orphan_memos": [...]    # memos not matched to any item (TOC path)
}
```

Parse-method strings used in `metadata.parse_method`:

- v1: `url`, `toc_hierarchical`, `toc_flat`, `toc_deep_hierarchical`,
  `toc_document_bundle`
- v2: `v2_url`, `v2_toc`, `v2_pageref`

## CLI

Both chunkers expose the same CLI shape:

```bash
# Human-readable output
python -m vendors.adapters.parsers.agenda_chunker path/to/agenda.pdf
python -m vendors.adapters.parsers.agenda_chunker_v2 path/to/agenda.pdf

# JSON output
python -m vendors.adapters.parsers.agenda_chunker path/to/agenda.pdf --json

# Items only
python -m vendors.adapters.parsers.agenda_chunker path/to/agenda.pdf --json --items-only

# Force a specific parse method (v1 accepts --force-toc, --force-url; v2 also
# accepts --force-pageref)
python -m vendors.adapters.parsers.agenda_chunker path/to/agenda.pdf --force-toc
python -m vendors.adapters.parsers.agenda_chunker_v2 path/to/agenda.pdf --force-url

# V2 has a --compare mode that runs both chunkers and diffs the output
python -m vendors.adapters.parsers.agenda_chunker_v2 path/to/agenda.pdf --compare
```

## Who calls it

All callers download the PDF to a temp file and invoke the chunker via
`asyncio.to_thread`. Most go through `_parse_pdf_bytes` or `_parse_packet_pdf`
on the base adapter rather than importing `parse_agenda_pdf*` directly.

- **Granicus adapter** — Falls back when HTML parsing yields no items. For the
  `AgendaViewer.php → application/pdf` redirect path, forces `"url"` (v1 with
  v2 fallback) since Granicus agenda PDFs are URL-anchored. Packet-PDF fallback
  uses auto dispatch.
- **CivicPlus adapter** — Three tiers: (1) HTML agenda, (2) if HTML items lack
  attachments and a monolithic packet PDF is detected, chunker on the packet,
  (3) chunker as final fallback.
- **CivicWeb adapter** — Runs chunker on packet PDFs (typically have TOC
  bookmarks).
- **ProudCity adapter** — Four-step fallback: HTML packet tab, HTML agenda tab,
  chunker on agenda PDF (URL), chunker on packet PDF (TOC).
- **PrimeGov adapter** — If HTML parsing yields no items, calls
  `_chunk_agenda_then_packet` on the compiled packet URL.
- **Vision Internet adapter** — Chunker on packet PDFs from calendar cells.
- **WP Events adapter** — Chunker fallback when filename-based media
  classification yields no items.
- **Ross adapter** (custom) — Chunker fallback when detail page yields no
  structured staff-report items.
- **Manual ingestion** (`scripts/ingest_manual_pdfs.py`) — Chunker on
  manually-provided PDFs for cities behind bot protection.

## Post-chunking: attachment URL resolution

After v1's URL path or v2's `v2_url` path, `base_adapter_async._resolve_sub_attachments`
optionally runs a second pass:

1. For each item's primary PDF attachment, download it.
2. Extract embedded link annotations from that PDF.
3. Filter to attachment-like URLs (S3, Legistar, CloudFront, etc.).
4. Append new URLs as additional attachments on the same item.

This resolves the common pattern where an item's only attachment is a 1–2 page
staff-report cover sheet that itself hyperlinks to the real exhibits on Legistar
S3 or similar.

## Template file

`agenda_chunker_template.py` in the project root is the standalone/canonical
prototype used when developing new patterns. When new cases are encountered,
the template is updated first, then changes are ported into the production
versions (adapted for pipeline return formats, logging, and private naming).
Template is intentionally kept as reference — it's not dead code.
