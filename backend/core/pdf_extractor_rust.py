"""Rust PDF extractor - thin Python wrapper"""

import logging
import time
from typing import Dict, Optional
from engagic_core import PdfExtractor

logger = logging.getLogger("engagic")

# Enable Rust tracing output (set RUST_LOG env var if not set)
import os
if 'RUST_LOG' not in os.environ:
    os.environ['RUST_LOG'] = 'debug'


class RustPdfExtractor:
    """Direct wrapper around Rust PDF extractor"""

    def __init__(self):
        self._extractor = PdfExtractor()

    def extract_from_url(self, url: str) -> Dict[str, any]:
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
            result = self._extractor.extract_from_url(url)
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
                logger.warning(f"[Rust] Extraction failed for {url}")
                return {
                    'success': False,
                    'error': 'Extraction returned no result',
                    'extraction_time': extraction_time
                }

        except Exception as e:
            extraction_time = time.time() - start_time
            logger.error(f"[Rust] Extraction error for {url}: {e}")
            return {
                'success': False,
                'error': str(e),
                'extraction_time': extraction_time
            }

    def extract_from_bytes(self, pdf_bytes: bytes) -> Dict[str, any]:
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
                logger.warning(f"[Rust] Extraction from bytes failed")
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
