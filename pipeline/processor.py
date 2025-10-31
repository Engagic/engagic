"""
Pipeline Processor - Orchestrates meeting agenda processing

Simplified orchestration layer that coordinates:
- PDF extraction (parsing/)
- LLM summarization (analysis/llm/)
- Participation parsing (parsing/)
- Topic extraction (analysis/topics/)
- Caching (database/)

Moved from: infocore/processing/processor.py (simplified)
"""

import time
import json
import logging
from typing import List, Dict, Any, Optional, Tuple

from database.db import UnifiedDatabase
from config import config
from parsing.pdf import PdfExtractor
from parsing.participation import parse_participation_info
from analysis.llm.summarizer import GeminiSummarizer
from analysis.topics.normalizer import get_normalizer

logger = logging.getLogger("engagic")


class ProcessingError(Exception):
    """Base exception for PDF processing errors"""
    pass


class AgendaProcessor:
    """High-level agenda processing orchestrator"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the processor

        Args:
            api_key: Gemini API key (or uses environment variables)
        """
        self.pdf_extractor = PdfExtractor()
        self.summarizer = GeminiSummarizer(api_key=api_key)
        self.db = UnifiedDatabase(config.UNIFIED_DB_PATH)

        logger.info(
            "[Processor] Initialized with PyMuPDF extractor, Gemini summarizer"
        )

    def process_agenda_with_cache(self, meeting_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point - process agenda with caching

        Args:
            meeting_data: Dictionary with packet_url, city_banana, etc.

        Returns:
            Dictionary with summary, processing_time, cached flag, etc.
        """
        packet_url = meeting_data.get("packet_url")
        if not packet_url:
            return {"success": False, "error": "No packet_url provided"}

        city_banana = meeting_data.get("city_banana", "unknown")

        # Check cache first
        cached_meeting = self.db.get_cached_summary(packet_url)
        if cached_meeting:
            logger.info(f"[Cache] HIT - {city_banana}")
            self._update_cache_hit_count(packet_url)

            return {
                "success": True,
                "summary": cached_meeting.summary,
                "processing_time": cached_meeting.processing_time or 0,
                "cached": True,
                "meeting_data": cached_meeting.to_dict(),
                "processing_method": cached_meeting.processing_method or "cached",
            }

        # Process with Gemini
        logger.info(f"[Cache] MISS - {city_banana}")
        start_time = time.time()

        try:
            # Process the agenda (returns summary, method, participation)
            summary, method, participation = self.process_agenda(packet_url)

            # Store in database
            processing_time = time.time() - start_time
            meeting_data["processed_summary"] = summary
            meeting_data["processing_time_seconds"] = processing_time
            meeting_data["processing_method"] = method
            if participation:
                meeting_data["participation"] = participation

            # Update meeting with summary and participation
            meeting_id = meeting_data.get("meeting_id")
            if meeting_id:
                self.db.update_meeting_summary(
                    meeting_id, summary, method, processing_time, participation
                )

            # Store in cache
            self._store_in_cache(packet_url, summary, processing_time)

            logger.info(f"[Processing] SUCCESS - {city_banana}")

            return {
                "success": True,
                "summary": summary,
                "processing_time": processing_time,
                "cached": False,
                "meeting_data": meeting_data,
                "meeting_id": meeting_id,
                "processing_method": method,
            }

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                f"[Processing] FAILED - {city_banana} - {type(e).__name__}: {e}"
            )
            return {
                "success": False,
                "error": str(e),
                "processing_time": processing_time,
                "cached": False,
            }

    def process_agenda(self, url: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
        """Process agenda using PyMuPDF + Gemini (fail fast approach)

        Args:
            url: PDF URL

        Returns:
            Tuple of (summary, method_used, participation_info)

        Raises:
            ProcessingError: If processing fails
        """
        try:
            result = self.pdf_extractor.extract_from_url(url)
            if result.get("success") and result.get("text"):
                extracted_text = result["text"]

                # Parse participation info BEFORE AI summarization
                participation = parse_participation_info(extracted_text)
                if participation:
                    logger.debug(f"[Participation] Extracted info: {list(participation.keys())}")

                # Summarize meeting
                summary = self.summarizer.summarize_meeting(extracted_text)
                logger.info(f"[Processing] SUCCESS - {url}")

                # Cleanup: free PDF text memory
                del result
                del extracted_text

                return summary, "pymupdf_gemini", participation
            else:
                logger.warning(
                    f"[Processing] FAILED - No text extracted or poor quality - {url}"
                )

        except Exception as e:
            logger.warning(f"[Processing] FAILED - {type(e).__name__}: {str(e)} - {url}")

        # Fail fast
        logger.error(f"[Processing] REJECTED - {url}")
        raise ProcessingError(
            "Document processing failed. "
            "This PDF may be scanned or have complex formatting."
        )

    def process_batch_items(
        self, item_requests: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Process multiple agenda items using Gemini Batch API

        Delegates to summarizer.summarize_batch() for actual batch processing.

        Args:
            item_requests: List of dicts with structure:
                [{
                    'item_id': str,
                    'title': str,
                    'text': str,
                    'sequence': int,
                    'page_count': int or None
                }, ...]

        Returns:
            List of results: [{
                'item_id': str,
                'success': bool,
                'summary': str,
                'topics': List[str],
                'error': str (if failed)
            }, ...]
        """
        if not item_requests:
            return []

        logger.info(
            f"[Processor] Delegating {len(item_requests)} items to batch summarizer"
        )
        return self.summarizer.summarize_batch(item_requests)

    def _update_cache_hit_count(self, packet_url: str):
        """Update cache hit count in cache table"""
        try:
            conn = self.db.conn
            if conn:
                cursor = conn.cursor()

                # Serialize packet_url if it's a list
                lookup_url = packet_url
                if isinstance(packet_url, list):
                    lookup_url = json.dumps(packet_url)

                cursor.execute(
                    """
                    UPDATE processing_cache
                    SET hit_count = hit_count + 1,
                        last_accessed = CURRENT_TIMESTAMP
                    WHERE packet_url = ?
                """,
                    (lookup_url,),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to update cache hit count: {e}")

    def _store_in_cache(self, packet_url: str, summary: str, processing_time: float):
        """Store processing result in cache"""
        try:
            conn = self.db.conn
            if conn:
                cursor = conn.cursor()

                # Serialize packet_url if it's a list
                lookup_url = packet_url
                if isinstance(packet_url, list):
                    lookup_url = json.dumps(packet_url)

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO processing_cache
                    (packet_url, summary, processing_time, created_at, last_accessed, hit_count)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0)
                """,
                    (lookup_url, summary, processing_time),
                )
                conn.commit()
                logger.debug(f"[Cache] Stored summary for {lookup_url}")
        except Exception as e:
            logger.warning(f"Failed to store in cache: {e}")
