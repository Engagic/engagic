"""
Pipeline Analyzer - LLM analysis orchestration

Coordinates:
- PDF extraction (parsing/)
- LLM summarization (analysis/llm/)
- Participation parsing (parsing/)
- Topic extraction (analysis/topics/)
- Caching (database/)

Moved from: pipeline/processor.py (renamed for clarity)
"""

import time
from typing import List, Dict, Any, Optional, Tuple

from database.db import UnifiedDatabase
from database.transaction import transaction
from config import config
from exceptions import ExtractionError, LLMError
from parsing.pdf import PdfExtractor
from parsing.participation import parse_participation_info
from analysis.llm.summarizer import GeminiSummarizer

from config import get_logger

logger = get_logger(__name__).bind(component="pipeline")



class AnalysisError(Exception):
    """Base exception for analysis errors"""
    pass


class Analyzer:
    """LLM analysis orchestrator"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the analyzer

        Args:
            api_key: Gemini API key (or uses environment variables)
        """
        self.pdf_extractor = PdfExtractor()
        self.summarizer = GeminiSummarizer(api_key=api_key)
        self.db = UnifiedDatabase(config.UNIFIED_DB_PATH)

        logger.info(
            "analyzer initialized",
            pdf_extractor="pymupdf",
            summarizer="gemini"
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

        # Check cache first (also increments hit count if found)
        cached_meeting = self.db.get_cached_summary(packet_url)
        if cached_meeting:
            logger.info("cache hit", city=city_banana)
            return {
                "success": True,
                "summary": cached_meeting.summary,
                "processing_time": cached_meeting.processing_time or 0,
                "cached": True,
                "meeting_data": cached_meeting.to_dict(),
                "processing_method": cached_meeting.processing_method or "cached",
            }

        # Process with Gemini
        logger.info("cache miss", city=city_banana)
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

            # Update meeting with summary and participation + cache metadata
            meeting_id = meeting_data.get("meeting_id")
            with transaction(self.db.conn):
                if meeting_id:
                    self.db.update_meeting_summary(
                        meeting_id, summary, method, processing_time, participation
                    )
                # Store processing metadata in cache table
                self.db.store_processing_result(packet_url, method, processing_time)

            logger.info("processing success", city=city_banana)

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
                "processing failed",
                city=city_banana,
                error=str(e),
                error_type=type(e).__name__
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
                    logger.debug("extracted participation info", fields=list(participation.keys()))

                # Summarize meeting
                summary = self.summarizer.summarize_meeting(extracted_text)
                logger.info("agenda processing success", url=url)

                # Cleanup: free PDF text memory
                del result
                del extracted_text

                return summary, "pymupdf_gemini", participation
            else:
                logger.warning(
                    "no text extracted or poor quality",
                    url=url
                )

        except (ExtractionError, LLMError, OSError, IOError) as e:
            logger.warning("processing failed", url=url, error=str(e), error_type=type(e).__name__)

        # Fail fast
        logger.error("analysis rejected", url=url)
        raise AnalysisError(
            "Document analysis failed. "
            "This PDF may be scanned or have complex formatting."
        )

    def process_batch_items(
        self,
        item_requests: List[Dict[str, Any]],
        shared_context: Optional[str] = None,
        meeting_id: Optional[str] = None
    ):
        """Process multiple agenda items using Gemini Batch API, yielding chunk results

        Generator that yields chunk results immediately as they complete.
        Enables incremental saving to prevent data loss on crashes.

        Args:
            item_requests: List of dicts with structure:
                [{
                    'item_id': str,
                    'title': str,
                    'text': str,  # Item-specific text only (shared docs excluded)
                    'sequence': int,
                    'page_count': int or None
                }, ...]
            shared_context: Optional meeting-level shared document context (for caching)
            meeting_id: Optional meeting ID (for cache naming)

        Yields:
            List of results per chunk: [{
                'item_id': str,
                'success': bool,
                'summary': str,
                'topics': List[str],
                'error': str (if failed)
            }, ...]
        """
        if not item_requests:
            return

        logger.info(
            f"[Analyzer] Delegating {len(item_requests)} items to batch summarizer"
        )

        # Yield from the summarizer's generator
        yield from self.summarizer.summarize_batch(
            item_requests,
            shared_context=shared_context,
            meeting_id=meeting_id
        )
