"""PDF extractor using PyMuPDF"""

import logging
import time
import requests
from typing import Dict, Any
import fitz  # PyMuPDF

logger = logging.getLogger("engagic")


class PdfExtractor:
    """PDF extractor using PyMuPDF"""

    def __init__(self):
        pass

    def extract_from_url(self, url: str) -> Dict[str, Any]:
        """Extract text from PDF URL

        Returns dict with extraction results:
        {
            'success': bool,
            'text': str,
            'method': str,
            'page_count': int,
            'extraction_time': float,
            'error': str (if failed)
        }
        """
        start_time = time.time()

        try:
            # Download PDF
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            pdf_bytes = response.content

            # Extract with PyMuPDF
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text_parts = []
            for page_num, page in enumerate(doc, 1):
                text_parts.append(f"--- PAGE {page_num} ---\n{page.get_text()}")

            full_text = "\n\n".join(text_parts)
            page_count = len(doc)
            doc.close()

            extraction_time = time.time() - start_time
            logger.info(f"[PyMuPDF] Extracted {page_count} pages, {len(full_text)} chars in {extraction_time:.2f}s")

            return {
                'success': True,
                'text': full_text,
                'method': 'pymupdf',
                'page_count': page_count,
                'extraction_time': extraction_time
            }

        except Exception as e:
            extraction_time = time.time() - start_time
            logger.error(f"[PyMuPDF] Failed for {url}: {e}")
            return {
                'success': False,
                'error': f"PyMuPDF extraction failed: {str(e)}",
                'extraction_time': extraction_time
            }

    def extract_from_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Extract text from PDF bytes

        Returns dict with extraction results (same format as extract_from_url)
        """
        start_time = time.time()

        try:
            # Extract with PyMuPDF
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text_parts = []
            for page_num, page in enumerate(doc, 1):
                text_parts.append(f"--- PAGE {page_num} ---\n{page.get_text()}")

            full_text = "\n\n".join(text_parts)
            page_count = len(doc)
            doc.close()

            extraction_time = time.time() - start_time
            logger.info(f"[PyMuPDF] Extracted {page_count} pages, {len(full_text)} chars in {extraction_time:.2f}s")

            return {
                'success': True,
                'text': full_text,
                'method': 'pymupdf',
                'page_count': page_count,
                'extraction_time': extraction_time
            }

        except Exception as e:
            extraction_time = time.time() - start_time
            logger.error(f"[PyMuPDF] Extraction from bytes failed: {e}")
            return {
                'success': False,
                'error': f"PyMuPDF extraction failed: {str(e)}",
                'extraction_time': extraction_time
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
