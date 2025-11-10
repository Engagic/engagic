"""PDF extractor using PyMuPDF with OCR fallback

Moved from: infocore/processing/pdf_extractor.py
"""

import io
import logging
import time
import requests
from typing import Dict, Any
import fitz  # PyMuPDF
import pytesseract
from PIL import Image

logger = logging.getLogger("engagic")


class PdfExtractor:
    """PDF extractor using PyMuPDF with OCR fallback"""

    def __init__(self, ocr_threshold: int = 100, ocr_dpi: int = 300):
        """Initialize PDF extractor

        Args:
            ocr_threshold: Minimum characters per page before triggering OCR fallback
            ocr_dpi: DPI for image rendering when using OCR (higher = better quality, slower)
        """
        self.ocr_threshold = ocr_threshold
        self.ocr_dpi = ocr_dpi

    def _ocr_page(self, page) -> str:
        """Extract text from page using OCR

        Args:
            page: PyMuPDF page object

        Returns:
            Extracted text from OCR
        """
        # Render page to high-DPI image
        pix = page.get_pixmap(dpi=self.ocr_dpi)
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))

        # Run Tesseract OCR
        text = pytesseract.image_to_string(img)
        return text

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
            # Download PDF
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            pdf_bytes = response.content

            # Extract with PyMuPDF (with OCR fallback for scanned pages)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text_parts = []
            all_links = []
            ocr_pages = 0

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text()  # type: ignore[attr-defined]

                # If page has minimal text, assume scanned/image-based PDF
                if len(page_text.strip()) < self.ocr_threshold:
                    page_text = self._ocr_page(page)
                    ocr_pages += 1

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
            doc.close()

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
            logger.error(f"[PyMuPDF] Failed for {url}: {e}")
            return {
                "success": False,
                "error": f"PyMuPDF extraction failed: {str(e)}",
                "extraction_time": extraction_time,
            }

    def extract_from_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Extract text from PDF bytes

        Returns dict with extraction results (same format as extract_from_url)
        """
        start_time = time.time()

        try:
            # Extract with PyMuPDF (with OCR fallback for scanned pages)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text_parts = []
            ocr_pages = 0

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text()  # type: ignore[attr-defined]

                # If page has minimal text, assume scanned/image-based PDF
                if len(page_text.strip()) < self.ocr_threshold:
                    page_text = self._ocr_page(page)
                    ocr_pages += 1

                text_parts.append(f"--- PAGE {page_num + 1} ---\n{page_text}")

            full_text = "\n\n".join(text_parts)
            page_count = len(doc)
            doc.close()

            extraction_time = time.time() - start_time

            # Determine extraction method
            method = "pymupdf+ocr" if ocr_pages > 0 else "pymupdf"

            log_msg = f"[PyMuPDF] Extracted {page_count} pages, {len(full_text)} chars"
            if ocr_pages > 0:
                log_msg += f" (OCR: {ocr_pages} pages)"
            log_msg += f" in {extraction_time:.2f}s"
            logger.info(log_msg)

            return {
                "success": True,
                "text": full_text,
                "method": method,
                "page_count": page_count,
                "extraction_time": extraction_time,
                "ocr_pages": ocr_pages,
            }

        except Exception as e:
            extraction_time = time.time() - start_time
            logger.error(f"[PyMuPDF] Extraction from bytes failed: {e}")
            return {
                "success": False,
                "error": f"PyMuPDF extraction failed: {str(e)}",
                "extraction_time": extraction_time,
            }

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
