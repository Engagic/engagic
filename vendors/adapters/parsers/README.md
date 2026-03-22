# Agenda Chunker

`agenda_chunker.py` extracts structured agenda items from municipal meeting PDFs. It works across vendors (Granicus, Legistar, CivicPlus, CivicClerk, etc.) by operating on the PDF itself rather than any vendor-specific API.

## How it works

The chunker has two extraction paths, chosen automatically based on PDF structure:

```
PDF opened with PyMuPDF
        │
        ▼
Has meaningful TOC? ──yes──► TOC-based parsing
(bookmarks spanning              │
 multiple pages)                  ├── Hierarchical?
        │                         │   L1 = items on agenda pages
        no                        │   L2 = embedded memos on later pages
        │                         │   → toc_hierarchical
        ▼                         │
URL-based parsing                 └── Flat?
(hyperlinked attachments              L1 entries point to distinct pages
 assigned to nearest item)            → toc_flat
→ url                                     │
                                          └── Text parsing found 0 items?
                                              → Build items directly from
                                                TOC entries (fallback)
```

### TOC Hierarchical (`toc_hierarchical`)

For PDFs where the bookmark tree has two levels: L1 entries are agenda items clustered on the first few pages, and L2 entries are embedded staff memos/reports on subsequent pages. The chunker:

1. Identifies the "agenda page cluster" (pages where L1 bookmarks point)
2. Parses item numbers and titles from L1 bookmark text (e.g. `D.4\t03-26-2026 Type B Site Plan`)
3. For each L2 child, extracts the memo page range and pulls structured fields: SUBJECT, SUMMARY, FISCAL INFORMATION, RECOMMENDED ACTION, Submitted by
4. Assigns memo `full_text` as the item's `body_text` for downstream summarization

Common with: Cedar Park TX, cities using Granicus packet PDFs with bookmark outlines.

### TOC Flat (`toc_flat`)

For PDFs where L1 entries each point to a distinct page (no L1/L2 hierarchy). The chunker:

1. Determines which pages are the "agenda" vs. content pages
2. Runs text-based item detection on the agenda pages (same logic as URL path)
3. Extracts memo content from each TOC entry beyond the agenda
4. Fuzzy-matches memos to items using `SequenceMatcher` + keyword overlap (threshold: 0.25)
5. Unmatched memos go to `orphan_memos`

If text-based item detection finds nothing on the agenda pages, the chunker falls back to building items directly from TOC L1 entries (`_build_items_from_toc_entries`), treating each entry as an item and sub-entries as attachments.

Common with: cities that produce packet PDFs with flat bookmark lists (e.g. `01a Claims and Payroll`, `03 AB Cross Connection Control`).

### URL-based (`url`)

For PDFs with no bookmark tree but with hyperlinked attachment URLs embedded in the text. The chunker:

1. Extracts all text lines with font metadata (bold, size, position)
2. Extracts all URI links from every page
3. Detects agenda items via `_is_likely_item_header` heuristics
4. Assigns each attachment URL to the nearest preceding item by page/y-position
5. Unassigned links go to `orphan_links`

Common with: Legistar-generated agendas, Santa Monica, Nashville, many others.

## Item detection

The core item detection (`_is_likely_item_header`) recognizes:

| Pattern | Examples |
|---------|----------|
| Dotted sub-items | `4.3`, `6.1.2`, `1.2.3.4` |
| Numbered items | `1.`, `2.`, `12.` |
| Lettered items | `A.`, `B.`, `a.`, `b.` |
| Roman numerals | `I.`, `II.`, `IV.` |

Heuristics to distinguish items from non-items:
- Sub-items (containing `.`) are always treated as items
- Standalone numbers require being inside a known agenda section (CONSENT, PUBLIC HEARINGS, etc.) and having a title on the next line(s)
- Case numbers (`CUP-2024-001`, `ZA 25-001`) and consent prefixes (`CONSENT FOR APPROVAL`) are strong item signals
- Bold text or mostly-uppercase text with a number prefix is treated as an item

## Section detection

~40 patterns for common municipal section headers: CONSENT CALENDAR, PUBLIC HEARINGS, ADJOURNMENT, etc. Matched via regex against bold/uppercase lines. Items inherit the current section.

## Output format

```python
from vendors.adapters.parsers.agenda_chunker import parse_agenda_pdf

result = parse_agenda_pdf("path/to/agenda.pdf")
```

Returns:

```python
{
    "items": [
        {
            "vendor_item_id": "4.3",
            "title": "Approve Agreement with ...",
            "sequence": 1,
            "agenda_number": "4.3",
            "body_text": "...",          # memo full_text (TOC) or coversheet (URL)
            "matter_file": "2024-001",   # extracted if present, else absent
            "attachments": [
                {"name": "Staff Report", "url": "https://...", "type": "pdf"}
            ],
            "metadata": {
                "section": "CONSENT CALENDAR",
                "recommended_action": "Adopt Resolution No. ...",
                "parse_method": "toc_hierarchical",
                "page_start": 3,
                "page_end": 5,
                "memo_count": 1,         # TOC path only
                "memo_pages": 3          # TOC path only
            }
        }
    ],
    "metadata": {
        "body_name": "City Council",
        "meeting_date": "March 26, 2026",
        "meeting_type": "Regular Meeting",
        "page_count": 42,
        "parse_method": "toc_hierarchical"
    },
    "orphan_links": [...],   # links not assigned to any item
    "orphan_memos": [...]    # memos not matched to any item
}
```

## CLI

```bash
# Human-readable output
python -m vendors.adapters.parsers.agenda_chunker path/to/agenda.pdf

# JSON output
python -m vendors.adapters.parsers.agenda_chunker path/to/agenda.pdf --json

# Items only
python -m vendors.adapters.parsers.agenda_chunker path/to/agenda.pdf --json --items-only

# Force a specific parse method
python -m vendors.adapters.parsers.agenda_chunker path/to/agenda.pdf --force-toc
python -m vendors.adapters.parsers.agenda_chunker path/to/agenda.pdf --force-url
```

## Who calls it

- **Granicus adapter** (`granicus_adapter_async.py`): Falls back to `parse_agenda_pdf` when HTML parsing yields no items. Tries agenda PDF first (may have hyperlinked attachments), then packet PDF.
- **CivicPlus adapter** (`civicplus_adapter_async.py`): Three-tier priority: (1) HTML agenda, (2) if HTML items lack attachments and a monolithic packet PDF is detected, runs the chunker on the packet, (3) PDF chunker as final fallback.

Both adapters download the PDF to a temp file and call `parse_agenda_pdf` via `asyncio.to_thread`.

## Template file

`agenda_chunker_template.py` in the project root is the standalone/canonical version used for prototyping new patterns. When new cases are encountered, the template is updated first, then changes are ported into this production version (adapted for pipeline return formats, logging, and private naming conventions).
