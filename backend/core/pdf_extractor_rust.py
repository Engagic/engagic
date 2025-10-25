"""Rust PDF extractor - thin Python wrapper"""

import logging
from typing import Optional
from engagic_core import PdfExtractor

logger = logging.getLogger("engagic")


class RustPdfExtractor:
    """Direct wrapper around Rust PDF extractor"""

    def __init__(self):
        self._extractor = PdfExtractor()

    def extract_from_url(self, url: str) -> Optional[str]:
        """Extract text from PDF URL

        Returns extracted text or None if extraction fails
        """
        result = self._extractor.extract_from_url(url)
        if result:
            logger.info(f"[Rust] Extracted {result.page_count} pages, {len(result.text)} chars")
            return result.text
        return None

    def extract_from_bytes(self, pdf_bytes: bytes) -> Optional[str]:
        """Extract text from PDF bytes"""
        result = self._extractor.extract_from_bytes(pdf_bytes)
        if result:
            logger.info(f"[Rust] Extracted {result.page_count} pages, {len(result.text)} chars")
            return result.text
        return None

    def validate_text(self, text: str) -> bool:
        """Validate text quality"""
        return self._extractor.validate_text(text)
