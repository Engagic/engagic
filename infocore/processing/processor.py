"""
Agenda Processor - High-level orchestration for meeting agenda processing

This module coordinates PDF extraction, summarization, and caching.
Heavy lifting delegated to:
- pdf_extractor.py - PyMuPDF text extraction
- summarizer.py - Gemini LLM orchestration
- chunker.py - Document parsing and boundary detection

STRATEGY: Fail fast with simple, cost-effective processing
- Tier 1: PyMuPDF + Gemini (60% success rate, ~$0.001/doc, ~2-5s)
- If Tier 1 fails: raise error immediately (document needs paid tier)

Premium tiers (Tier 2 Mistral OCR, Tier 3 Gemini PDF) archived for future use.
See: backend/archived/premium_processing_tiers.py
"""

import time
import json
import logging
from typing import List, Dict, Any, Optional, Union

# Our modules
from infocore.database import UnifiedDatabase
from infocore.config import config
from infocore.processing.pdf_extractor import PdfExtractor
from infocore.processing.summarizer import GeminiSummarizer
from infocore.processing.chunker import AgendaChunker
from infocore.processing.participation_parser import parse_participation_info

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
        # Initialize components
        self.pdf_extractor = PdfExtractor()
        self.summarizer = GeminiSummarizer(api_key=api_key)
        self.chunker = AgendaChunker()
        self.db = UnifiedDatabase(config.UNIFIED_DB_PATH)

        logger.info(
            "[Processor] Initialized with PyMuPDF extractor, Gemini summarizer, and agenda chunker"
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

        # Extract city context for logging
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

    def process_agenda(self, url: Union[str, List[str]]) -> tuple[str, str, Optional[Dict[str, Any]]]:
        """Process agenda using Tier 1 (PyMuPDF + Gemini) - fail fast approach

        FREE TIER STRATEGY:
        - Try Tier 1: PyMuPDF text extraction + Gemini (60% success rate)
        - If it fails: raise error immediately (no expensive fallbacks)
        - Premium tiers archived in backend/archived/premium_processing_tiers.py

        Args:
            url: Single URL string or list of URLs

        Returns:
            Tuple of (summary, method_used, participation_info)

        Raises:
            ProcessingError: If Tier 1 fails (document requires paid tier)
        """
        # Handle multiple URLs
        if isinstance(url, list):
            return self._process_multiple_pdfs(url)

        # Tier 1: PyMuPDF extraction + Gemini text API (free tier)
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
                logger.info(f"[Tier1] SUCCESS - {url}")

                # Cleanup: free PDF text memory
                del result
                del extracted_text

                return summary, "tier1_pymupdf_gemini", participation
            else:
                logger.warning(
                    f"[Tier1] FAILED - No text extracted or poor quality - {url}"
                )

        except Exception as e:
            logger.warning(f"[Tier1] FAILED - {type(e).__name__}: {str(e)} - {url}")

        # Free tier: fail fast (no expensive fallbacks)
        logger.error(f"[Tier1] REJECTED - Requires premium tier - {url}")
        raise ProcessingError(
            "Document requires premium tier for processing. "
            "This PDF may be scanned or have complex formatting that requires OCR."
        )

    def _process_multiple_pdfs(self, urls: List[str]) -> tuple[str, str, Optional[Dict[str, Any]]]:
        """Process multiple PDFs by extracting all text first, then summarizing with full context

        Strategy: Most multi-PDF cases are main agenda + supplemental materials.
        The model should reason over the complete context to produce a coherent summary.
        """
        logger.info(f"Processing {len(urls)} PDFs with combined context")

        # Extract text from all PDFs
        all_text_parts = []
        failed_pdfs = []

        for i, url in enumerate(urls, 1):
            logger.info(f"Extracting text from PDF {i}/{len(urls)}: {url}")
            try:
                result = self.pdf_extractor.extract_from_url(url)
                if result.get("success") and result.get("text"):
                    text = result["text"]
                    # Label each document for model context
                    doc_label = (
                        "MAIN AGENDA" if i == 1 else f"SUPPLEMENTAL MATERIAL {i - 1}"
                    )
                    all_text_parts.append(f"=== {doc_label} ===\n{text}")
                    logger.info(
                        f"[PyMuPDF] Extracted {len(text)} chars from document {i}"
                    )
                else:
                    logger.warning(f"[PyMuPDF] No text from PDF {i}")
                    failed_pdfs.append(i)
            except Exception as e:
                logger.error(
                    f"[PyMuPDF] Failed to extract from PDF {i}: {type(e).__name__}: {str(e)}"
                )
                failed_pdfs.append(i)

        # If we got no usable text from any PDF, fail fast
        if not all_text_parts:
            logger.error(
                f"[Tier1] REJECTED - No usable text from any of {len(urls)} PDFs"
            )
            raise ProcessingError(
                f"All {len(urls)} documents require premium tier for processing. "
                "These PDFs may be scanned or have complex formatting that requires OCR."
            )

        # Combine all text and summarize with full context
        combined_text = "\n\n".join(all_text_parts)
        logger.info(
            f"[Tier1] Combined {len(all_text_parts)}/{len(urls)} documents ({len(combined_text)} chars total)"
        )

        # Parse participation info from combined text BEFORE summarization
        participation = parse_participation_info(combined_text)
        if participation:
            logger.debug(f"[Participation] Extracted from {len(urls)} PDFs: {list(participation.keys())}")

        # Summarize with full context (model sees all documents at once)
        summary = self.summarizer.summarize_meeting(combined_text)

        # Note partial failures in the summary if any PDFs couldn't be processed
        if failed_pdfs:
            failure_note = f"\n\n[Note: {len(failed_pdfs)} of {len(urls)} documents could not be processed]"
            summary += failure_note
            logger.warning(
                f"Partial success: {len(all_text_parts)}/{len(urls)} documents processed"
            )

        # Cleanup: free memory immediately (50-100MB per large meeting)
        del all_text_parts
        del combined_text

        return summary, f"multiple_pdfs_{len(urls)}_combined", participation

    def process_agenda_item(
        self, item_data: Dict[str, Any], city_banana: str
    ) -> Dict[str, Any]:
        """Process a single agenda item with its attachments

        Args:
            item_data: Dictionary with structure:
                {
                    'item_id': str,
                    'title': str,
                    'sequence': int,
                    'attachments': [{'name': str, 'url': str, 'type': str}, ...]
                }
            city_banana: City identifier for logging

        Returns:
            Dictionary with:
                {
                    'success': bool,
                    'summary': str,
                    'topics': List[str],
                    'processing_time': float,
                    'attachments_processed': int,
                    'error': str (if success=False)
                }
        """
        start_time = time.time()
        item_title = item_data.get("title", "Untitled Item")
        attachments = item_data.get("attachments", [])

        logger.info(f"[Item] Processing: {item_title[:80]}")

        if not attachments:
            logger.info("[Item] No attachments, skipping processing")
            return {
                "success": True,
                "summary": None,
                "topics": [],
                "processing_time": time.time() - start_time,
                "attachments_processed": 0,
            }

        logger.info(f"[Item] Found {len(attachments)} attachment(s)")

        try:
            # Process attachments - handle both URL-based and text segment types
            all_text_parts = []
            processed_count = 0

            for i, att in enumerate(attachments, 1):
                att_type = att.get("type", "unknown")

                # Case 1: Text segment (from item detection)
                if att_type == "text_segment":
                    text_content = att.get("content", "")
                    if text_content:
                        all_text_parts.append(text_content)
                        processed_count += 1
                        logger.info(
                            f"[Item] Using text segment ({len(text_content)} chars)"
                        )
                    continue

                # Case 2: PDF attachment with URL (from Legistar/adapters)
                if att_type == "pdf":
                    att_name = att.get("name", f"Attachment {i}")
                    att_url = att.get("url")

                    if not att_url:
                        logger.warning(
                            f"[Item] PDF attachment {i} has no URL, skipping"
                        )
                        continue

                    logger.info(f"[Item] Extracting from PDF: {att_name}")

                    try:
                        result = self.pdf_extractor.extract_from_url(att_url)
                        if result.get("success") and result.get("text"):
                            text = result["text"]
                            all_text_parts.append(f"=== {att_name} ===\n{text}")
                            processed_count += 1
                            logger.info(
                                f"[PyMuPDF] Extracted {len(text)} chars from {att_name}"
                            )
                        else:
                            logger.warning(f"[PyMuPDF] No text from {att_name}")
                    except Exception as e:
                        logger.warning(
                            f"[PyMuPDF] Failed to extract from {att_name}: {e}"
                        )
                else:
                    logger.debug(f"[Item] Skipping attachment type: {att_type}")

            # If no usable text, return empty result
            if not all_text_parts:
                logger.warning("[Item] No usable text from any attachment")
                return {
                    "success": False,
                    "error": "No usable text extracted from attachments",
                    "processing_time": time.time() - start_time,
                    "attachments_processed": 0,
                }

            # Combine all attachment text
            combined_text = "\n\n".join(all_text_parts)

            # Generate item summary with topic extraction (delegate to summarizer)
            summary, topics = self.summarizer.summarize_item(item_title, combined_text)

            processing_time = time.time() - start_time
            logger.info(
                f"[Item] Processed in {processing_time:.1f}s - {processed_count} attachments, {len(topics)} topics"
            )

            return {
                "success": True,
                "summary": summary,
                "topics": topics,
                "processing_time": processing_time,
                "attachments_processed": processed_count,
            }

        except Exception as e:
            logger.error(f"[Item] Processing failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "processing_time": time.time() - start_time,
                "attachments_processed": 0,
            }

    def process_batch_items(
        self, item_requests: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Process multiple agenda items using Gemini Batch API for 50% cost savings

        Delegates to summarizer.summarize_batch() for actual batch processing.

        Args:
            item_requests: List of dicts with structure:
                [{
                    'item_id': str,
                    'title': str,
                    'text': str,  # Pre-extracted and concatenated text
                    'sequence': int
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
