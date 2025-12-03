# parsing/ - PDF Extraction Module

Document parsing utilities for legislative PDF extraction. Treats PDF parsing as adversarial: assumes malformed inputs, prioritizes extraction accuracy over speed.

## Files

### pdf.py - Core PDF Extractor

Primary extraction using PyMuPDF (fitz) with OCR fallback via Tesseract.

**Key class: `PdfExtractor`**

```python
from parsing.pdf import PdfExtractor

extractor = PdfExtractor()

# Extract from URL
result = extractor.extract_from_url(pdf_url, extract_links=True)

# Extract from bytes
result = extractor.extract_from_bytes(pdf_bytes, extract_links=True)
```

**Return format:**
```python
{
    "success": bool,
    "text": str,           # Extracted text content
    "page_count": int,     # Total pages in document
    "ocr_pages": int,      # Pages that required OCR
    "links": list,         # Extracted hyperlinks (if extract_links=True)
    "error": str | None,   # Error message if failed
}
```

**Features:**
- Legislative formatting detection (strikethrough/underline)
- Strikethrough = deletions from law: outputs `[DELETED: text]`
- Underline = additions to law: outputs `[ADDED: text]`
- OCR fallback for scanned pages (Tesseract)
- Link extraction with page positioning
- Memory-safe image processing (100MP limit)

### chicago_pdf.py - Chicago Agenda Parser

Parses Chicago City Council agenda PDFs to extract record numbers.

```python
from parsing.chicago_pdf import parse_chicago_agenda_pdf

parsed = parse_chicago_agenda_pdf(pdf_text)
# Returns: {"items": [{"record_number": "O2025-0019668", "sequence": 1}, ...]}
```

### menlopark_pdf.py - Menlo Park Agenda Parser

Parses Menlo Park agenda PDFs with letter-based section structure (H., I., J., K.).

```python
from parsing.menlopark_pdf import parse_menlopark_pdf_agenda

parsed = parse_menlopark_pdf_agenda(pdf_text, links)
# Returns: {"items": [{item_id, title, attachments, ...}, ...]}
```

### participation.py - Participation Info Extractor

Extracts civic engagement information (Zoom links, phone numbers, email) from meeting text.

```python
from parsing.participation import parse_participation_info

info = parse_participation_info(meeting_text, agenda_items)
# Returns: ParticipationInfo object with virtual_url, phone, email, etc.
```

## Error Handling

All extractors raise `ExtractionError` for failures:

```python
from exceptions import ExtractionError

try:
    result = extractor.extract_from_url(url)
except ExtractionError as e:
    logger.error("extraction failed", url=e.document_url, error=str(e))
```

## Performance Notes

- PyMuPDF handles ~80% of PDFs reliably
- OCR fallback adds 1-5 seconds per page
- Large documents (1000+ pages) are likely public comment compilations
- Memory usage peaks at ~300MB for 100MP image limit

## Dependencies

- `PyMuPDF` (fitz) - Primary PDF parsing
- `pytesseract` - OCR fallback
- `Pillow` - Image processing for OCR
- `requests` - PDF URL fetching
