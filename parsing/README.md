# parsing/ - PDF Extraction Module

Document parsing utilities for legislative PDF extraction. Treats PDF parsing as adversarial: assumes malformed inputs, prioritizes extraction accuracy over speed.

## Files

### pdf.py - Core PDF Extractor

Primary extraction using PyMuPDF (fitz) with OCR fallback via Tesseract.

**Key class: `PdfExtractor`**

```python
from parsing.pdf import PdfExtractor

# Constructor parameters (all optional with defaults)
extractor = PdfExtractor(
    ocr_threshold=100,                  # Min chars per page before OCR triggers
    ocr_dpi=150,                        # DPI for OCR rendering (lower = faster, higher = better quality)
    detect_legislative_formatting=True, # Enable [DELETED]/[ADDED] tag detection
    max_ocr_workers=4                   # Parallel OCR threads
)

# Extract from URL
result = extractor.extract_from_url(pdf_url, extract_links=True)

# Extract from bytes
result = extractor.extract_from_bytes(pdf_bytes, extract_links=True)

# Validate extracted text quality
is_valid = extractor.validate_text(result["text"])
```

**Return format:**
```python
{
    "success": bool,
    "text": str,             # Extracted text content
    "method": str,           # "pymupdf" or "pymupdf+ocr"
    "page_count": int,       # Total pages in document
    "extraction_time": float, # Seconds elapsed
    "ocr_pages": int,        # Pages that required OCR
    "links": list,           # Extracted hyperlinks (only if extract_links=True)
}
```

On failure, raises `ExtractionError` (not a return value).

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
# Returns: {"items": [{"record_number": "O2025-0019668", "sequence": 1, "title_hint": "Amendment of..."}, ...]}
```

### menlopark_pdf.py - Menlo Park Agenda Parser

Parses Menlo Park agenda PDFs with letter-based section structure (H., I., J., K.).

```python
from parsing.menlopark_pdf import parse_menlopark_pdf_agenda

parsed = parse_menlopark_pdf_agenda(pdf_text, links)
# Returns: {"items": [{item_id, title, sequence, attachments: [{name, url, type}]}, ...]}
```

### participation.py - Participation Info Extractor

Extracts civic engagement information from meeting text before AI summarization.

**Extracts:**
- Multiple emails with inferred purpose (written comments, city clerk, etc.)
- Phone numbers (normalized to +1 format)
- Virtual meeting URLs (Zoom, Google Meet, Teams, WebEx, GoToMeeting)
- Streaming URLs with platform detection (YouTube, Facebook Live, Granicus, Midpen Media, Vimeo)
- Cable TV channel info
- Zoom meeting IDs (handles spaces/dashes)
- Hybrid vs virtual-only detection flags

```python
from parsing.participation import parse_participation_info

info = parse_participation_info(meeting_text)
# Returns: ParticipationInfo model or None if nothing found
# Uses models from database.models (ParticipationInfo, EmailContext, StreamingUrl)
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
- OCR fallback uses parallel ThreadPoolExecutor (configurable via `max_ocr_workers`)
- OCR adds 1-5 seconds per page sequentially, faster with parallel workers
- Large documents (1000+ pages) are likely public comment compilations
- Memory usage peaks at ~300MB per OCR worker for 100MP image limit

## Dependencies

- `PyMuPDF` (fitz) - Primary PDF parsing
- `pytesseract` - OCR fallback
- `Pillow` - Image processing for OCR
- `requests` - PDF URL fetching
- `pydantic` - Data models for ParticipationInfo (via database.models)
