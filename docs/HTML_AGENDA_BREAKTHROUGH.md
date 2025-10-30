# HTML Agenda Breakthrough - Item-Level Processing

**Date:** 2025-01-29
**Status:** Discovery phase, ready to implement

---

## The Insight

We've been packet-first when we should be **agenda-first + item-level**.

### The Problem with Packets

```
Current approach:
1. Download 250-page packet PDF
2. Try to summarize monolithic document
3. Memory issues, poor granularity, slow processing
```

### The Solution: HTML Agendas

**PrimeGov returns THREE document types:**
```json
{
  "documentList": [
    {"templateName": "HTML Agenda", "compileOutputType": 3},  // ← THE GOLD
    {"templateName": "Agenda", "compileOutputType": 1},       // PDF agenda
    {"templateName": "Packet", "compileOutputType": 1}        // Full packet
  ]
}
```

**HTML Agendas contain:**
- ✅ Item titles as structured headers
- ✅ Item descriptions/context
- ✅ Download buttons/links to attachments per item
- ✅ Perfect structure - no text parsing/chunking needed
- ✅ No 250-page PDFs - just download item attachments

---

## Current State by Vendor

### Legistar (Already Works!)
- ✅ API returns structured items
- ✅ `fetch_event_items()` → `fetch_matter_attachments()`
- ✅ Item-level processing already implemented in conductor
- ✅ Stores in `agenda_items` table

**Code:** `infocore/adapters/legistar_adapter.py:105-150`

### PrimeGov (HTML Available!)
- ✅ Has "HTML Agenda" document type
- ❌ Currently only fetches packet
- 🔨 **TODO:** Fetch HTML Agenda, parse structure, extract item+attachments

**Example:** Palo Alto, CA - `cityofpaloalto.primegov.com`

### CivicClerk (Check for HTML)
- ✅ Has `publishedFiles` array
- ❓ Need to check if HTML agenda type exists
- ❓ Currently only grabs "Agenda Packet" or "Agenda"

**Example:** Montpelier, VT - `montpelliervt.api.civicclerk.com`

### Granicus (Already Deep Scrapes!)
- ✅ `_extract_pdfs_from_agenda_viewer()` already exists
- ✅ Scrapes agenda viewer page for PDFs
- ❌ Doesn't connect PDFs to specific items
- 🔨 **TODO:** Parse HTML structure to map attachments to items

**Code:** `infocore/adapters/granicus_adapter.py:215-240`

### NovusAgenda (HTML Scraping)
- ❓ Need to investigate structure
- ❓ Likely has HTML agenda views

### CivicPlus (HTML Scraping)
- ❓ Need to investigate structure
- ❓ Likely has HTML agenda views

---

## The New Flow

### For API Vendors (PrimeGov, CivicClerk, Legistar)

```python
# 1. Fetch meeting metadata
meeting = adapter.fetch_meetings()

# 2. Check for HTML agenda first
html_doc = next(
    (doc for doc in meeting['documentList'] if 'HTML Agenda' in doc['templateName']),
    None
)

if html_doc:
    # 3. Fetch HTML agenda
    html_url = adapter._build_html_agenda_url(html_doc)
    soup = adapter._fetch_html(html_url)

    # 4. Parse structure → items
    items = []
    for section in soup.find_all('div', class='agenda-item'):  # Class names TBD
        item = {
            'sequence': parse_sequence(section),
            'title': section.find('h3').text,  # Structure TBD
            'description': section.find('.description').text,
            'attachments': [
                {'name': a.text, 'url': urljoin(base_url, a['href'])}
                for a in section.find_all('a', class='attachment')  # Class TBD
            ]
        }
        items.append(item)

    # 5. Process per-item with attachments
    for item in items:
        # Combine description + attachment text
        text = item['description']
        for att in item['attachments']:
            pdf_text = extract_pdf(att['url'])
            text += f"\n\n[Attachment: {att['name']}]\n{pdf_text}"

        # Summarize combined text
        summary = summarizer.summarize_item(text)

        # Store in agenda_items table
        db.store_agenda_item(
            meeting_id=meeting['id'],
            sequence=item['sequence'],
            title=item['title'],
            summary=summary,
            attachments=item['attachments']
        )

else:
    # Fallback: Use packet or use chunker on Agenda PDF
    pass
```

### For HTML Scrapers (Granicus, NovusAgenda, CivicPlus)

```python
# Already fetching HTML pages - just need to parse structure

# Current Granicus:
pdfs = _extract_pdfs_from_agenda_viewer(url)  # ['a.pdf', 'b.pdf', 'c.pdf']
# Problem: Don't know which PDF belongs to which item

# New Granicus:
items = _parse_agenda_structure(soup)
# [
#   {
#     'title': 'Item 1 - Zoning Amendment',
#     'description': 'Discussion of...',
#     'attachments': [
#       {'name': 'Staff Report', 'url': 'a.pdf'},
#     ]
#   },
#   {
#     'title': 'Item 2 - Budget Approval',
#     'description': 'Vote on...',
#     'attachments': [
#       {'name': 'Budget Document', 'url': 'b.pdf'},
#       {'name': 'Analysis', 'url': 'c.pdf'}
#     ]
#   }
# ]
```

---

## Fallback Strategy

Not all meetings will have HTML agendas. Fallback chain:

1. **Try HTML Agenda** - Best, structured items
2. **Try Agenda PDF + Chunker** - Good, chunker extracts items from PDF
3. **Try Packet PDF** - Worst, monolithic summary

```python
def fetch_agenda_items(meeting):
    # Try HTML first
    html_doc = find_html_agenda(meeting)
    if html_doc:
        return parse_html_structure(html_doc)

    # Try Agenda PDF with chunker
    agenda_doc = find_agenda_pdf(meeting)
    if agenda_doc:
        text = extract_pdf(agenda_doc)
        return chunker.chunk_by_structure(text)

    # Fall back to packet
    packet_doc = find_packet(meeting)
    if packet_doc:
        text = extract_pdf(packet_doc)
        return [{'title': 'Full Meeting', 'text': text}]  # Single monolithic item

    return []
```

---

## Implementation Plan

### Phase 1: Proof of Concept (PrimeGov)
1. Fetch HTML Agenda for Palo Alto meeting
2. Inspect actual HTML structure (class names, tags, hierarchy)
3. Write parser to extract items
4. Test per-item processing
5. Compare to Legistar quality

**Script to write:** `scripts/probe_html_agenda.py`

### Phase 2: Update Adapters
1. **PrimeGovAdapter**: Add `fetch_html_agenda()`, `parse_html_structure()`
2. **CivicClerkAdapter**: Check for HTML, add if exists
3. **GranicusAdapter**: Connect PDF extraction to item structure
4. **NovusAgendaAdapter**: Investigate HTML structure
5. **CivicPlusAdapter**: Investigate HTML structure

### Phase 3: Update Conductor
- Already handles item-level processing (Legistar proof)
- Just need adapters to return items in correct format
- Code at: `infra/conductor.py:879-900` (batch item processing)

### Phase 4: Migrate Database
- Prefer items over packets in all queries
- Meeting-level summaries = aggregated item summaries
- Packet processing becomes fallback, not default

---

## Benefits

### Memory
- Process 10-page chunks, not 250-page monsters
- No more OOM kills on VPS

### Granularity
- Per-item summaries and topics
- Better search ("find zoning items")
- Better alerts ("notify me about budget items")

### Quality
- Item context + attachments = better summaries
- No loss of detail in monolithic summaries

### Failure Isolation
- One item fails → others succeed
- Currently: One PDF fails → whole meeting fails

### Performance
- Smaller chunks = faster processing
- Parallel item processing possible
- Legistar already does this successfully

---

## Success Criteria

- [ ] HTML agenda parsing works for PrimeGov
- [ ] Item-level processing for 3+ vendors
- [ ] Topic extraction per-item (aggregated to meeting)
- [ ] Memory usage stays under 600MB during processing
- [ ] 80%+ of meetings have item-level granularity
- [ ] Meeting summaries = aggregated item summaries

---

## Open Questions

1. **HTML structure varies by vendor?**
   - Need to inspect actual HTML from each vendor
   - May need vendor-specific parsers
   - Or find common patterns (likely: divs/sections with classes)

2. **What about non-HTML agendas?**
   - Chunker fallback works (already implemented)
   - PDF agenda parsing is reliable enough

3. **How to handle supplemental packets?**
   - Some meetings have agenda + later supplemental
   - Need to track which items updated
   - Database schema already supports this

4. **Rate limiting on attachment downloads?**
   - Currently: 1 packet per meeting
   - New: N attachments per meeting
   - Need to respect vendor rate limits

---

## Next Steps (On VPS)

1. **Probe HTML agendas:**
   ```bash
   python scripts/probe_html_agenda.py primegov cityofpaloalto
   python scripts/probe_html_agenda.py granicus cambridge
   python scripts/probe_html_agenda.py civicclerk montpelliervt
   ```

2. **Document actual HTML structures**
   - Save example HTML to `docs/vendor_html_examples/`
   - Identify common patterns

3. **Write parsers**
   - Start with PrimeGov (cleanest API)
   - Test with multiple cities
   - Verify item+attachment mapping

4. **Update conductor**
   - Prefer items over packets
   - Batch process items (already exists for Legistar)
   - Store in agenda_items table

---

## Code References

**Already working (Legistar):**
- Adapter: `infocore/adapters/legistar_adapter.py:105-150`
- Conductor: `infra/conductor.py:879-900`
- Database: `infocore/database/unified_db.py` (`agenda_items` table)

**Needs updating:**
- Other adapters: `infocore/adapters/primegov_adapter.py`, etc.
- Conductor: Prefer items over packets in `_sync_city()`

**Chunker (fallback):**
- `infocore/processing/chunker.py:25-100`
- Already extracts items from PDF text
- Works as fallback when HTML unavailable

---

**This is the path to item-level granularity for all vendors, not just Legistar.**
