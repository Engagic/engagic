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
from pipeline.protocols import MetricsCollector, NullMetrics

from config import config, get_logger

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

    def __init__(
        self,
        api_key: Optional[str] = None,
        metrics: Optional[MetricsCollector] = None
    ):
        """Initialize the async analyzer

        Args:
            api_key: Gemini API key (or uses environment variables)
            metrics: Metrics collector for LLM call tracking (uses NullMetrics if not provided)
        """
        self.metrics = metrics or NullMetrics()
        self.pdf_extractor = PdfExtractor()  # Sync extractor, we'll wrap calls
        self.summarizer = GeminiSummarizer(api_key=api_key, metrics=self.metrics)
        self.http_session: Optional[aiohttp.ClientSession] = None
        self._request_count = 0
        self._recycle_after = 100  # Recycle session after N requests to prevent memory accumulation

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

    async def recycle_session(self):
        """Close and recreate HTTP session to free accumulated memory."""
        previous = self._request_count
        await self.close()
        self.http_session = None
        self._request_count = 0
        logger.info("http session recycled", previous_requests=previous)

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures cleanup even on exception"""
        await self.close()
        return False  # Don't suppress exceptions

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
        # Recycle session periodically to prevent memory accumulation
        self._request_count += 1
        if self._request_count >= self._recycle_after:
            await self.recycle_session()

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
            ExtractionError: If extraction fails or times out
        """
        # Download PDF (async I/O)
        pdf_bytes = await self.download_pdf_async(url)

        # Extract text in thread pool with timeout (defense in depth)
        # 10 min budget for huge PDFs with OCR - OCR itself has 5 min internal timeout
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.pdf_extractor.extract_from_bytes,
                    pdf_bytes
                ),
                timeout=600
            )
        except asyncio.TimeoutError:
            logger.error("PDF extraction timed out after 10 minutes", url=url[:100])
            raise ExtractionError(f"PDF extraction timed out after 10 minutes: {url[:100]}")

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
                # 5 min timeout - summarizer has internal 3 min retry budget
                try:
                    summary = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.summarizer.summarize_meeting,
                            extracted_text
                        ),
                        timeout=300
                    )
                except asyncio.TimeoutError:
                    logger.error("LLM summarization timed out after 5 minutes", url=url[:100])
                    raise LLMError("LLM summarization timed out after 5 minutes", model="gemini", prompt_type="meeting")

                logger.info("agenda processing success", url=url)

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
            """Process single item with timeout"""
            try:
                text = item.get("text", "")
                title = item.get("title", "")
                page_count = item.get("page_count")

                # Summarize item (Gemini SDK is sync, run in thread pool)
                # Rate limiting handled reactively by summarizer
                # 5 min timeout per item - summarizer has 3 min internal retry budget
                summary, topics = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.summarizer.summarize_item,
                        title,
                        text,
                        page_count
                    ),
                    timeout=300
                )

                return {
                    "item_id": item["item_id"],
                    "success": True,
                    "summary": summary,
                    "topics": topics
                }

            except asyncio.TimeoutError:
                logger.error(
                    "item summarization timed out after 5 minutes",
                    item_id=item.get("item_id"),
                    title=item.get("title", "")[:50]
                )
                return {
                    "item_id": item["item_id"],
                    "success": False,
                    "error": "LLM summarization timed out after 5 minutes"
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

        # Process items with controlled concurrency
        # Gemini API has TPM limits but built-in retry handles 429s
        # Concurrency configurable via ENGAGIC_LLM_CONCURRENCY (default 3)
        concurrency = config.LLM_CONCURRENCY
        semaphore = asyncio.Semaphore(concurrency)

        async def process_with_limit(item: Dict[str, Any], index: int) -> Dict[str, Any]:
            async with semaphore:
                logger.debug("processing item", index=index + 1, total=len(item_requests))
                return await process_item(item)

        # Concurrent processing with semaphore limiting
        results = await asyncio.gather(
            *[process_with_limit(item, i) for i, item in enumerate(item_requests)],
            return_exceptions=True
        )

        # Handle any unexpected exceptions from gather
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("unexpected item exception", item_id=item_requests[i].get("item_id"), error=str(result))
                processed.append({
                    "item_id": item_requests[i]["item_id"],
                    "success": False,
                    "error": str(result)
                })
            else:
                processed.append(result)

        # Return as single chunk (compatible with sync generator interface)
        logger.info("batch processing complete", success=sum(1 for r in processed if r["success"]), total=len(processed), concurrency=concurrency)
        return [processed]
