"""
Async Analyzer - LLM analysis orchestration with concurrent processing

Async version of pipeline/analyzer.py with:
- Async PDF downloads (aiohttp)
- Concurrent PDF extraction (asyncio.to_thread for PyMuPDF)
- Concurrent batch processing

Coordinates:
- PDF extraction (parsing/)
- LLM summarization (analysis/llm/)
- Participation parsing (parsing/)
- Topic extraction (analysis/topics/)

Rate limiting is handled by the summarizer via Gemini's retry instructions.
"""

import asyncio
import time
from typing import List, Dict, Any, Optional, Tuple
import aiohttp

from exceptions import ExtractionError, LLMError
from parsing.pdf import PdfExtractor
from parsing.participation import parse_participation_info
from analysis.llm.summarizer import GeminiSummarizer

from config import get_logger

logger = get_logger(__name__).bind(component="pipeline")


class AnalysisError(Exception):
    """Base exception for analysis errors"""
    pass


class AsyncAnalyzer:
    """
    Async LLM analysis orchestrator.

    Key Features:
    - Async PDF downloads (aiohttp, concurrent)
    - CPU-bound extraction in thread pool (non-blocking)
    - Concurrent batch processing

    Rate limiting is handled reactively by the summarizer via Gemini's retry instructions.
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the async analyzer

        Args:
            api_key: Gemini API key (or uses environment variables)
        """
        self.pdf_extractor = PdfExtractor()  # Sync extractor, we'll wrap calls
        self.summarizer = GeminiSummarizer(api_key=api_key)  # Sync summarizer, we'll wrap calls
        self.http_session: Optional[aiohttp.ClientSession] = None

        logger.info(
            "async analyzer initialized",
            pdf_extractor="pymupdf",
            summarizer="gemini"
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session (lazy initialization)"""
        if self.http_session is None or self.http_session.closed:
            timeout = aiohttp.ClientTimeout(total=300, connect=30)  # 5min total, 30s connect
            self.http_session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/pdf,application/octet-stream,*/*"
                }
            )
        return self.http_session

    async def close(self):
        """Close HTTP session (cleanup)"""
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
            logger.debug("http session closed")

    async def download_pdf_async(self, url: str) -> bytes:
        """
        Download PDF asynchronously (non-blocking).

        Args:
            url: PDF URL

        Returns:
            PDF bytes

        Raises:
            ExtractionError: If download fails
        """
        session = await self._get_session()

        try:
            async with session.get(url, ssl=False) as resp:  # Disable SSL for Granicus S3
                if resp.status != 200:
                    raise ExtractionError(f"HTTP {resp.status} downloading PDF from {url}")

                pdf_bytes = await resp.read()
                logger.debug("pdf downloaded", url=url, size_mb=round(len(pdf_bytes) / 1024 / 1024, 2))
                return pdf_bytes

        except aiohttp.ClientError as e:
            logger.error("pdf download failed", url=url, error=str(e))
            raise ExtractionError(f"Failed to download PDF: {e}") from e

    async def extract_pdf_async(self, url: str) -> Dict[str, Any]:
        """
        Extract text from PDF asynchronously.

        Downloads PDF with async HTTP, extracts text in thread pool (CPU-bound).

        Args:
            url: PDF URL

        Returns:
            Dict with keys: success, text, page_count, etc.

        Raises:
            ExtractionError: If extraction fails
        """
        # Download PDF (async I/O)
        pdf_bytes = await self.download_pdf_async(url)

        # Extract text in thread pool (CPU-bound, blocks thread but not event loop)
        result = await asyncio.to_thread(
            self.pdf_extractor.extract_from_bytes,
            pdf_bytes
        )

        if not result.get("success"):
            raise ExtractionError(f"PDF extraction failed: {result.get('error', 'Unknown error')}")

        logger.debug("pdf extracted", url=url, pages=result.get("page_count", 0))
        return result

    async def process_agenda_with_cache_async(self, meeting_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point - process agenda with caching (async version).

        Args:
            meeting_data: Dictionary with packet_url, city_banana, etc.

        Returns:
            Dictionary with summary, processing_time, cached flag, etc.
        """
        packet_url = meeting_data.get("packet_url")
        if not packet_url:
            return {"success": False, "error": "No packet_url provided"}

        city_banana = meeting_data.get("city_banana", "unknown")

        # Process with Gemini
        logger.info("processing meeting", city=city_banana)
        start_time = time.time()

        try:
            # Process the agenda (returns summary, method, participation)
            summary, method, participation = await self.process_agenda_async(packet_url)

            processing_time = time.time() - start_time
            meeting_id = meeting_data.get("meeting_id")

            logger.info("processing success", city=city_banana, duration_seconds=round(processing_time, 1))

            return {
                "success": True,
                "summary": summary,
                "processing_time": processing_time,
                "processing_method": method,
                "participation": participation,
                "cached": False,
                "meeting_id": meeting_id,
            }

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                "processing failed",
                city=city_banana,
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(processing_time, 1)
            )
            return {
                "success": False,
                "error": str(e),
                "processing_time": processing_time,
                "cached": False,
            }

    async def process_agenda_async(self, url: str) -> Tuple[str, str, Optional[Dict[str, Any]]]:
        """
        Process agenda using PyMuPDF + Gemini (async, fail fast approach).

        Args:
            url: PDF URL

        Returns:
            Tuple of (summary, method_used, participation_info)

        Raises:
            AnalysisError: If processing fails
        """
        try:
            # Extract PDF text (async download + thread pool extraction)
            result = await self.extract_pdf_async(url)

            if result.get("success") and result.get("text"):
                extracted_text = result["text"]

                # Parse participation info BEFORE AI summarization
                participation = parse_participation_info(extracted_text)
                if participation:
                    logger.debug("extracted participation info", fields=list(participation.model_dump(exclude_none=True).keys()))

                # Summarize meeting (Gemini SDK is sync, run in thread pool)
                # Rate limiting handled reactively by summarizer via Gemini's retry instructions
                summary = await asyncio.to_thread(
                    self.summarizer.summarize_meeting,
                    extracted_text
                )

                logger.info("agenda processing success", url=url)

                # Cleanup: free PDF text memory
                del result
                del extracted_text

                # Convert Pydantic model to dict for return type consistency
                participation_dict = participation.model_dump() if participation else None
                return summary, "pymupdf_gemini", participation_dict
            else:
                logger.warning("no text extracted or poor quality", url=url)

        except (ExtractionError, LLMError, OSError, IOError) as e:
            logger.warning("processing failed", url=url, error=str(e), error_type=type(e).__name__)

        # Fail fast
        logger.error("analysis rejected", url=url)
        raise AnalysisError(
            "Document analysis failed. "
            "This PDF may be scanned or have complex formatting."
        )

    async def process_batch_items_async(
        self,
        item_requests: List[Dict[str, Any]],
        shared_context: Optional[str] = None,
        meeting_id: Optional[str] = None
    ) -> List[List[Dict[str, Any]]]:
        """
        Process multiple agenda items concurrently.

        Unlike sync version (generator), returns complete results after processing.
        Rate limiting handled reactively by summarizer via Gemini's retry instructions.

        Args:
            item_requests: List of dicts with structure:
                [{
                    'item_id': str,
                    'title': str,
                    'text': str,
                    'sequence': int,
                    'page_count': int or None
                }, ...]
            shared_context: Optional meeting-level shared document context
            meeting_id: Optional meeting ID (for cache naming)

        Returns:
            List of result chunks (compatible with sync generator interface)
            [[{
                'item_id': str,
                'success': bool,
                'summary': str,
                'topics': List[str],
                'error': str (if failed)
            }, ...]]
        """
        if not item_requests:
            return []

        logger.info(
            "processing batch items async",
            count=len(item_requests),
            concurrent=True
        )

        async def process_item(item: Dict[str, Any]) -> Dict[str, Any]:
            """Process single item"""
            try:
                text = item.get("text", "")
                title = item.get("title", "")
                page_count = item.get("page_count")

                # Summarize item (Gemini SDK is sync, run in thread pool)
                # Rate limiting handled reactively by summarizer
                summary, topics = await asyncio.to_thread(
                    self.summarizer.summarize_item,
                    title,
                    text,
                    page_count
                )

                return {
                    "item_id": item["item_id"],
                    "success": True,
                    "summary": summary,
                    "topics": topics
                }

            except Exception as e:
                logger.error(
                    "item processing failed",
                    item_id=item.get("item_id"),
                    error=str(e),
                    error_type=type(e).__name__
                )
                return {
                    "item_id": item["item_id"],
                    "success": False,
                    "error": str(e)
                }

        # Process all items concurrently
        results = await asyncio.gather(*[process_item(item) for item in item_requests])

        # Return as single chunk (compatible with sync generator interface)
        logger.info("batch processing complete", success=sum(1 for r in results if r["success"]), total=len(results))
        return [results]
