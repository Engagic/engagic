"""Rust PDF extractor with PyMuPDF fallback for Identity-H fonts"""

import logging
import os
import time
import requests
from typing import Dict, Any
from engagic_core import PdfExtractor
import fitz  # PyMuPDF

logger = logging.getLogger("engagic")

# Enable Rust tracing output (set RUST_LOG env var if not set)
if 'RUST_LOG' not in os.environ:
    os.environ['RUST_LOG'] = 'debug'


class RustPdfExtractor:
    """Direct wrapper around Rust PDF extractor"""

    def __init__(self):
        self._extractor = PdfExtractor()

    def extract_from_url(self, url: str) -> Dict[str, Any]:
        """Extract text from PDF URL with PyMuPDF fallback

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
            result = self._extractor.extract_from_url(url)
            extraction_time = time.time() - start_time

            if result:
                logger.info(f"[Rust poppler] Extracted {result.page_count} pages, {len(result.text)} chars in {extraction_time:.2f}s")
                return {
                    'success': True,
                    'text': result.text,
                    'method': 'rust_poppler',
                    'page_count': result.page_count,
                    'extraction_time': extraction_time
                }
            else:
                logger.warning(f"[Rust poppler] Extraction failed for {url} (likely Identity-H fonts), falling back to PyMuPDF")
                return self._fallback_pymupdf(url, start_time)

        except Exception as e:
            logger.warning(f"[Rust poppler] Extraction error for {url}: {e}, falling back to PyMuPDF")
            return self._fallback_pymupdf(url, start_time)

    def extract_from_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Extract text from PDF bytes

        Returns dict with extraction results (same format as extract_from_url)
        """
        start_time = time.time()

        try:
            result = self._extractor.extract_from_bytes(pdf_bytes)
            extraction_time = time.time() - start_time

            if result:
                logger.info(f"[Rust] Extracted {result.page_count} pages, {len(result.text)} chars in {extraction_time:.2f}s")
                return {
                    'success': True,
                    'text': result.text,
                    'method': 'rust_lopdf',
                    'page_count': result.page_count,
                    'extraction_time': extraction_time
                }
            else:
                logger.warning("[Rust] Extraction from bytes failed")
                return {
                    'success': False,
                    'error': 'Extraction returned no result',
                    'extraction_time': extraction_time
                }

        except Exception as e:
            extraction_time = time.time() - start_time
            logger.error(f"[Rust] Extraction error from bytes: {e}")
            return {
                'success': False,
                'error': str(e),
                'extraction_time': extraction_time
            }

    def validate_text(self, text: str) -> bool:
        """Validate text quality"""
        return self._extractor.validate_text(text)
