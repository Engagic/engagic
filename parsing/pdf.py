"""PDF extractor using PyMuPDF with OCR fallback

Moved from: infocore/processing/pdf_extractor.py

Legislative formatting detection (strikethrough/underline):
- Detects thin filled rectangles (MS Word/LibreOffice export format)
- Strikethrough = deletions from law (line through middle of text)
- Underline = additions to law (line below text)
- Outputs as [DELETED: text] and [ADDED: text] tags in markdown
"""

import io
import time
import warnings
import requests
from typing import Dict, Any, List, Tuple
import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from config import get_logger
from exceptions import ExtractionError

logger = get_logger(__name__).bind(component="parser")

# Browser-like headers to avoid bot detection
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "application/pdf,application/octet-stream,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# Set conservative limit for OCR on scanned PDFs
# 100MP = ~300MB peak RAM (conservative for 2GB VPS with other services)
# Convert PIL warnings to errors to catch decompression bombs
Image.MAX_IMAGE_PIXELS = 100000000
warnings.simplefilter('error', Image.DecompressionBombWarning)



def _detect_horizontal_lines(page: fitz.Page) -> List[Tuple[float, float, float]]:
    """
    Detect horizontal lines from drawing instructions.

    Strikethrough/underline in MS Word/LibreOffice are rendered as THIN FILLED RECTANGLES.

    Returns:
        list of (x0, x1, y_position) tuples for horizontal bars
    """
    lines = []
    paths = page.get_drawings()

    for path in paths:
        # Check if this path is a filled black rectangle (potential line)
        fill_color = path.get("fill")
        if fill_color and fill_color == (0.0, 0.0, 0.0):  # Black fill
            for item in path["items"]:
                if item[0] == "re":  # Rectangle
                    rect = item[1]
                    x0, y0, x1, y1 = rect

                    height = abs(y1 - y0)
                    width = abs(x1 - x0)

                    # Thin horizontal rectangle (height < 2 points, width > 5 points)
                    if height < 2 and width > 5:
                        y_mid = (y0 + y1) / 2
                        lines.append((x0, x1, y_mid))

                # Also check for actual line items (just in case)
                elif item[0] == "l":
                    p1, p2 = item[1:]
                    if abs(p1.y - p2.y) < 0.5:
                        line_x0 = min(p1.x, p2.x)
                        line_x1 = max(p1.x, p2.x)
                        lines.append((line_x0, line_x1, p1.y))

    return lines


def _match_lines_to_text(page: fitz.Page, lines: List[Tuple[float, float, float]]) -> Dict[str, List[Tuple[str, Tuple]]]:
    """
    Match horizontal lines to text spans and classify as strikethrough/underline.

    Returns dict with:
        'strikethrough': list of (text, bbox) tuples
        'underline': list of (text, bbox) tuples
    """
    result = {
        'strikethrough': [],
        'underline': []
    }

    # Get text with detailed positioning
    text_dict = page.get_text("dict")  # type: ignore[attr-defined]

    for block in text_dict["blocks"]:
        if block.get("type") != 0:  # Skip non-text blocks
            continue

        for line_obj in block.get("lines", []):
            for span in line_obj.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue

                bbox = span["bbox"]  # (x0, y0, x1, y1)
                text_x0, text_y0, text_x1, text_y1 = bbox

                # Text vertical center and bottom
                text_bottom_y = text_y1
                text_height = text_y1 - text_y0

                # Check each horizontal line
                for line_x0, line_x1, line_y in lines:
                    # Check if line horizontally overlaps with text
                    # (with small tolerance for slight misalignment)
                    if not (line_x1 < text_x0 - 2 or line_x0 > text_x1 + 2):
                        # Line overlaps text horizontally

                        # Strikethrough: line passes through middle of text
                        # (within 30% to 70% of text height from top)
                        if text_y0 + 0.3 * text_height <= line_y <= text_y0 + 0.7 * text_height:
                            result['strikethrough'].append((text, bbox))
                            break

                        # Underline: line is just below text
                        # (within 3 points below text bottom, or just touching)
                        elif text_bottom_y - 1 <= line_y <= text_bottom_y + 3:
                            result['underline'].append((text, bbox))
                            break

    return result


def _has_legislative_legend(doc: fitz.Document) -> bool:
    """Check if document contains legislative formatting legend (any page)."""
    for page_num in range(len(doc)):
        text = doc[page_num].get_text().lower()  # type: ignore[attr-defined]
        if (("addition" in text or "added" in text) and "underline" in text and
            ("deletion" in text or "deleted" in text) and "strikethrough" in text):
            return True
    return False


def _extract_text_with_formatting(page: fitz.Page, page_num: int) -> str:
    """
    Extract text from page with legislative formatting tags.

    Returns text with [DELETED: ...] and [ADDED: ...] tags for strikethrough/underline.
    """
    # Detect horizontal lines (strikethrough/underline indicators)
    lines = _detect_horizontal_lines(page)

    if not lines:
        # No formatting detected, return plain text
        return page.get_text()  # type: ignore[attr-defined]

    # Match lines to text
    matched = _match_lines_to_text(page, lines)
    strikethrough_spans = {bbox: text for text, bbox in matched['strikethrough']}
    underline_spans = {bbox: text for text, bbox in matched['underline']}

    # Get text with detailed positioning
    text_dict = page.get_text("dict")  # type: ignore[attr-defined]
    result_parts = []

    for block in text_dict["blocks"]:
        if block.get("type") != 0:  # Skip non-text blocks
            continue

        block_parts = []
        for line_obj in block.get("lines", []):
            line_parts = []
            for span in line_obj.get("spans", []):
                text = span.get("text", "")
                bbox = tuple(span["bbox"])

                # Check if this span has formatting
                if bbox in strikethrough_spans:
                    line_parts.append(f"[DELETED: {text}]")
                elif bbox in underline_spans:
                    line_parts.append(f"[ADDED: {text}]")
                else:
                    line_parts.append(text)

            block_parts.append("".join(line_parts))

        result_parts.append("\n".join(block_parts))

    return "\n\n".join(result_parts)


class PdfExtractor:
    """PDF extractor using PyMuPDF with OCR fallback"""

    def __init__(self, ocr_threshold: int = 100, ocr_dpi: int = 150, detect_legislative_formatting: bool = True):
        """Initialize PDF extractor

        Args:
            ocr_threshold: Minimum characters per page before triggering OCR fallback
            ocr_dpi: DPI for image rendering when using OCR (higher = better quality, slower)
                    Default 150 (reduced from 300) to prevent memory issues on VPS
            detect_legislative_formatting: If True, detect strikethrough (deletions) and underline (additions)
                    in legislative documents with formatting legends and tag them as [DELETED: ...] and [ADDED: ...]
                    Only activates if document contains legislative formatting legend. Default: True (safe for all PDFs)
        """
        self.ocr_threshold = ocr_threshold
        self.ocr_dpi = ocr_dpi
        self.detect_legislative_formatting = detect_legislative_formatting

    def _ocr_page(self, page) -> str:
        """Extract text from page using OCR

        Args:
            page: PyMuPDF page object

        Returns:
            Extracted text from OCR, or empty string if image too large
        """
        try:
            # Render page to high-DPI image
            pix = page.get_pixmap(dpi=self.ocr_dpi)

            # Check image size BEFORE trying PIL (prevent OOM)
            # 100MP = ~300MB peak RAM (conservative threshold for 2GB VPS with other services)
            megapixels = (pix.width * pix.height) / 1000000
            logger.debug(
                f"[PyMuPDF] Page {page.number + 1}: Rendering at {self.ocr_dpi} DPI = "
                f"{pix.width}x{pix.height} ({megapixels:.1f}MP)"
            )

            if megapixels > 100:
                logger.warning(
                    f"[PyMuPDF] Page {page.number + 1}: Image too large ({pix.width}x{pix.height} = "
                    f"{megapixels:.1f}MP), skipping OCR to prevent OOM"
                )
                return ""

            img_bytes = pix.tobytes("png")

            # Try to load image with PIL
            img = Image.open(io.BytesIO(img_bytes))

            # Run Tesseract OCR
            text = pytesseract.image_to_string(img)
            return text

        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            logger.warning("page image too large for OCR", page_num=page.number + 1)
            return ""
        except (OSError, pytesseract.TesseractError) as e:
            logger.error("OCR failed", page_num=page.number + 1, error=str(e), error_type=type(e).__name__)
            return ""

    def _is_ocr_better(self, original: str, ocr_result: str, page_num: int) -> bool:
        """Determine if OCR result is better than original text

        Args:
            original: Original extracted text
            ocr_result: OCR-produced text
            page_num: Page number (1-indexed, for logging)

        Returns:
            True if OCR should be used, False if original should be kept
        """
        orig_chars = len(original.strip())
        ocr_chars = len(ocr_result.strip())

        # If OCR produced nothing, always keep original
        if ocr_chars == 0:
            logger.info("keeping original text, OCR produced nothing", page_num=page_num)
            return False

        # Calculate quality metrics for OCR
        ocr_letters = sum(1 for c in ocr_result if c.isalpha())
        ocr_letter_ratio = ocr_letters / len(ocr_result) if len(ocr_result) > 0 else 0
        ocr_words = len(ocr_result.split())

        # OCR is better if:
        # 1. Produced significantly more text (2x+ characters) with reasonable quality (>40% letters)
        # 2. OR produced more text with high quality (>70% letters)
        significantly_more = ocr_chars >= (orig_chars * 2) and ocr_letter_ratio > 0.4
        high_quality_improvement = ocr_chars > orig_chars and ocr_letter_ratio > 0.7

        if significantly_more or high_quality_improvement:
            logger.info(
                f"[PyMuPDF] Page {page_num}: Using OCR "
                f"({ocr_chars} chars, {ocr_words} words, {ocr_letter_ratio:.1%} letters > original {orig_chars} chars)"
            )
            return True
        else:
            logger.info(
                f"[PyMuPDF] Page {page_num}: Keeping original "
                f"(OCR: {ocr_chars} chars, {ocr_letter_ratio:.1%} letters not better than original {orig_chars} chars)"
            )
            return False

    def extract_from_url(self, url: str, extract_links: bool = False) -> Dict[str, Any]:
        """Extract text and optionally links from PDF URL

        Args:
            url: PDF URL to extract from
            extract_links: Whether to extract hyperlinks (default False for backward compatibility)

        Returns dict with extraction results:
        {
            'success': bool,
            'text': str,
            'method': str,
            'page_count': int,
            'extraction_time': float,
            'links': list (if extract_links=True),
            'error': str (if failed)
        }
        """
        start_time = time.time()

        try:
            # Download PDF with browser-like headers to avoid bot detection
            response = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
            response.raise_for_status()
            pdf_bytes = response.content

            # Extract with PyMuPDF (with OCR fallback for scanned pages)
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                text_parts = []
                all_links = []
                ocr_pages = 0

                # Check for legislative legend once (if formatting detection enabled)
                use_formatting = self.detect_legislative_formatting and _has_legislative_legend(doc)
                if use_formatting:
                    logger.info("[PyMuPDF] Legislative formatting detected - tagging additions/deletions")

                for page_num in range(len(doc)):
                    page = doc[page_num]

                    # Extract text (with or without legislative formatting detection)
                    if use_formatting:
                        page_text = _extract_text_with_formatting(page, page_num + 1)
                    else:
                        page_text = page.get_text()  # type: ignore[attr-defined]

                    initial_char_count = len(page_text.strip())

                    # If page has minimal text, assume scanned/image-based PDF
                    if initial_char_count < self.ocr_threshold:
                        original_text = page_text  # Save original before OCR
                        initial_sample = original_text.strip()[:100].replace('\n', ' ')
                        logger.info(
                            f"[PyMuPDF] Page {page_num + 1}: OCR triggered "
                            f"({initial_char_count} chars < {self.ocr_threshold} threshold). "
                            f"Original: '{initial_sample}'"
                        )

                        ocr_result = self._ocr_page(page)
                        ocr_char_count = len(ocr_result.strip())
                        ocr_sample = ocr_result.strip()[:100].replace('\n', ' ')

                        # Calculate quality metrics for logging
                        letters = sum(1 for c in ocr_result if c.isalpha())
                        letter_ratio = letters / len(ocr_result) if len(ocr_result) > 0 else 0
                        word_count = len(ocr_result.split())

                        logger.info(
                            f"[PyMuPDF] Page {page_num + 1}: OCR produced {ocr_char_count} chars, "
                            f"{word_count} words, {letter_ratio:.1%} letters. "
                            f"Sample: '{ocr_sample}'"
                        )

                        # Decide whether to use OCR or keep original
                        if self._is_ocr_better(original_text, ocr_result, page_num + 1):
                            page_text = ocr_result
                            ocr_pages += 1
                        else:
                            page_text = original_text

                    text_parts.append(f"--- PAGE {page_num + 1} ---\n{page_text}")

                    # Extract links if requested
                    if extract_links:
                        page_links = page.get_links()  # type: ignore[attr-defined]
                        for link in page_links:
                            # Only external links (URIs), skip internal page references
                            if 'uri' in link and link['uri']:
                                all_links.append({
                                    'page': page_num + 1,
                                    'url': link['uri'],
                                    'rect': link.get('from', None),  # Rectangle coordinates on page
                                })

                full_text = "\n\n".join(text_parts)
                page_count = len(doc)
                # Context manager handles doc.close() automatically

            extraction_time = time.time() - start_time

            # Determine extraction method
            method = "pymupdf+ocr" if ocr_pages > 0 else "pymupdf"

            log_msg = f"[PyMuPDF] Extracted {page_count} pages, {len(full_text)} chars"
            if ocr_pages > 0:
                log_msg += f" (OCR: {ocr_pages} pages)"
            if extract_links:
                log_msg += f", {len(all_links)} links"
            log_msg += f" in {extraction_time:.2f}s"
            logger.info(log_msg)

            result = {
                "success": True,
                "text": full_text,
                "method": method,
                "page_count": page_count,
                "extraction_time": extraction_time,
                "ocr_pages": ocr_pages,
            }

            if extract_links:
                result["links"] = all_links

            return result

        except Exception as e:
            extraction_time = time.time() - start_time
            logger.error("[PyMuPDF] extraction failed", url=url[:100], error=str(e), error_type=type(e).__name__, extraction_time=round(extraction_time, 2))
            raise ExtractionError(
                f"PDF extraction failed after {extraction_time:.1f}s",
                document_url=url,
                document_type="pdf",
                original_error=e
            ) from e

    def extract_from_bytes(self, pdf_bytes: bytes, extract_links: bool = False) -> Dict[str, Any]:
        """Extract text and optionally links from PDF bytes

        Args:
            pdf_bytes: PDF file content as bytes
            extract_links: If True, also extract hyperlinks from PDF

        Returns dict with extraction results (same format as extract_from_url)
        """
        start_time = time.time()

        try:
            # Extract with PyMuPDF (with OCR fallback for scanned pages)
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                text_parts = []
                all_links = []
                ocr_pages = 0

                # Check for legislative legend once (if formatting detection enabled)
                use_formatting = self.detect_legislative_formatting and _has_legislative_legend(doc)
                if use_formatting:
                    logger.info("[PyMuPDF] Legislative formatting detected - tagging additions/deletions")

                for page_num in range(len(doc)):
                    page = doc[page_num]

                    # Extract text (with or without legislative formatting detection)
                    if use_formatting:
                        page_text = _extract_text_with_formatting(page, page_num + 1)
                    else:
                        page_text = page.get_text()  # type: ignore[attr-defined]

                    initial_char_count = len(page_text.strip())

                    # If page has minimal text, assume scanned/image-based PDF
                    if initial_char_count < self.ocr_threshold:
                        original_text = page_text  # Save original before OCR
                        initial_sample = original_text.strip()[:100].replace('\n', ' ')
                        logger.info(
                            f"[PyMuPDF] Page {page_num + 1}: OCR triggered "
                            f"({initial_char_count} chars < {self.ocr_threshold} threshold). "
                            f"Original: '{initial_sample}'"
                        )

                        ocr_result = self._ocr_page(page)
                        ocr_char_count = len(ocr_result.strip())
                        ocr_sample = ocr_result.strip()[:100].replace('\n', ' ')

                        # Calculate quality metrics for logging
                        letters = sum(1 for c in ocr_result if c.isalpha())
                        letter_ratio = letters / len(ocr_result) if len(ocr_result) > 0 else 0
                        word_count = len(ocr_result.split())

                        logger.info(
                            f"[PyMuPDF] Page {page_num + 1}: OCR produced {ocr_char_count} chars, "
                            f"{word_count} words, {letter_ratio:.1%} letters. "
                            f"Sample: '{ocr_sample}'"
                        )

                        # Decide whether to use OCR or keep original
                        if self._is_ocr_better(original_text, ocr_result, page_num + 1):
                            page_text = ocr_result
                            ocr_pages += 1
                        else:
                            page_text = original_text

                    text_parts.append(f"--- PAGE {page_num + 1} ---\n{page_text}")

                # Extract links if requested
                if extract_links:
                    page_links = page.get_links()  # type: ignore[attr-defined]
                    for link in page_links:
                        if 'uri' in link and link['uri']:
                            all_links.append({
                                'page': page_num + 1,
                                'url': link['uri'],
                                'rect': link.get('from', None),
                            })

                full_text = "\n\n".join(text_parts)
                page_count = len(doc)
                # Context manager handles doc.close() automatically

            extraction_time = time.time() - start_time

            # Determine extraction method
            method = "pymupdf+ocr" if ocr_pages > 0 else "pymupdf"

            log_msg = f"[PyMuPDF] Extracted {page_count} pages, {len(full_text)} chars"
            if ocr_pages > 0:
                log_msg += f" (OCR: {ocr_pages} pages)"
            if extract_links:
                log_msg += f", {len(all_links)} links"
            log_msg += f" in {extraction_time:.2f}s"
            logger.info(log_msg)

            result = {
                "success": True,
                "text": full_text,
                "method": method,
                "page_count": page_count,
                "extraction_time": extraction_time,
                "ocr_pages": ocr_pages,
            }

            if extract_links:
                result['links'] = all_links

            return result

        except Exception as e:
            extraction_time = time.time() - start_time
            logger.error("[PyMuPDF] extraction from bytes failed", error=str(e), error_type=type(e).__name__, extraction_time=round(extraction_time, 2))
            raise ExtractionError(
                f"PDF extraction from bytes failed after {extraction_time:.1f}s",
                document_type="pdf",
                original_error=e
            ) from e

    def validate_text(self, text: str) -> bool:
        """Validate text quality - basic check for now"""
        # Simple validation: check if text is not empty and has reasonable content
        if not text or len(text) < 100:
            return False

        # Check if text has reasonable letter ratio
        letters = sum(1 for c in text if c.isalpha())
        if letters / len(text) < 0.3:
            return False

        return True
