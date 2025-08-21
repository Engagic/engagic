"""
Async version of the PDF processor for non-blocking operations
"""

import asyncio
import aiohttp
import os
import re
import time
import logging
import tempfile
import hashlib
from typing import List, Dict, Any, Optional, Union
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# PDF processing
from PyPDF2 import PdfReader
import anthropic

# Our modules
from backend.database import DatabaseManager
from backend.core.config import config

logger = logging.getLogger("engagic")

# Security and processing limits
MAX_PDF_SIZE = 100 * 1024 * 1024  # 100MB max (reduced from 200MB)
MAX_PAGES = 1000
MAX_URL_LENGTH = 2000
MAX_CONCURRENT_DOWNLOADS = 3
MAX_CONCURRENT_PROCESSING = 2


class AsyncAgendaProcessor:
    """Async PDF processor for non-blocking operations"""
    
    def __init__(self, api_key: Optional[str] = None, mistral_api_key: Optional[str] = None):
        """Initialize the async processor"""
        # Initialize Anthropic client
        self.api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or config.get_api_key()
        if not self.api_key:
            raise ValueError("API key required - set LLM_API_KEY or ANTHROPIC_API_KEY environment variable")
        
        self.client = anthropic.AsyncAnthropic(api_key=self.api_key)  # Use async client
        
        # Initialize database
        self.db = DatabaseManager(
            locations_db_path=config.LOCATIONS_DB_PATH,
            meetings_db_path=config.MEETINGS_DB_PATH,
            analytics_db_path=config.ANALYTICS_DB_PATH,
        )
        
        # Thread pool for CPU-intensive operations
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Semaphores for rate limiting
        self.download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        self.processing_semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROCESSING)
        
        # Load basic English words for validation
        self.english_words = self._load_basic_english_words()
        
        # Processing statistics
        self.stats = {
            "tier1_success": 0,
            "tier2_success": 0, 
            "tier3_success": 0,
            "total_processed": 0,
            "total_cost": 0.0,
            "tier1_cost": 0.0,
            "tier2_cost": 0.0,
            "tier3_cost": 0.0
        }
    
    def _load_basic_english_words(self) -> set:
        """Load basic English words for text quality validation"""
        # Essential civic and government terms
        civic_words = {
            "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by",
            "council", "city", "meeting", "agenda", "item", "public", "comment", "session",
            "board", "commission", "appointment", "ordinance", "resolution", "budget",
            "planning", "zoning", "development", "traffic", "safety", "park", "library",
            "police", "fire", "emergency", "infrastructure", "project", "contract",
            "approval", "review", "hearing", "vote", "motion", "approve", "deny",
            "discussion", "report", "presentation", "staff", "department", "mayor",
            "member", "chair", "chairman", "chairwoman", "minutes", "action", "adopt"
        }
        return civic_words
    
    async def process_agenda_with_cache(self, meeting_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point - process agenda with caching (async)"""
        packet_url = meeting_data.get("packet_url")
        if not packet_url:
            return {"success": False, "error": "No packet_url provided"}
        
        # Check cache first (synchronous DB operation)
        cached_meeting = await asyncio.get_event_loop().run_in_executor(
            self.executor, self.db.get_cached_summary, packet_url
        )
        
        if cached_meeting:
            logger.info(f"Cache hit for {packet_url}")
            return {
                "success": True,
                "summary": cached_meeting["processed_summary"],
                "processing_time": cached_meeting.get("processing_time_seconds", 0),
                "cached": True,
                "meeting_data": cached_meeting,
                "processing_method": cached_meeting.get("processing_method", "cached")
            }
        
        # Process with optimal tiered approach
        logger.info(f"Cache miss for {packet_url} - processing with async tiered approach...")
        start_time = time.time()
        
        try:
            # Process the agenda asynchronously
            summary, method, cost = await self.process_agenda_optimal(packet_url)
            
            # Store in database (run in executor to not block)
            processing_time = time.time() - start_time
            meeting_data["processed_summary"] = summary
            meeting_data["processing_time_seconds"] = processing_time
            meeting_data["processing_method"] = method
            meeting_data["processing_cost"] = cost
            
            meeting_id = await asyncio.get_event_loop().run_in_executor(
                self.executor, 
                self.db.store_meeting_summary,
                meeting_data, summary, processing_time
            )
            
            logger.info(f"Processed agenda {packet_url} in {processing_time:.1f}s using {method} (cost: ${cost:.3f})")
            
            return {
                "success": True,
                "summary": summary,
                "processing_time": processing_time,
                "cached": False,
                "meeting_data": meeting_data,
                "meeting_id": meeting_id,
                "processing_method": method,
                "processing_cost": cost,
                "stats": self.stats
            }
            
        except Exception as e:
            logger.error(f"Failed to process agenda: {e}")
            return {
                "success": False,
                "error": str(e),
                "processing_time": time.time() - start_time,
                "cached": False
            }
    
    async def process_agenda_optimal(self, url: Union[str, List[str]]) -> tuple[str, str, float]:
        """Process agenda using optimal three-tier approach (async)"""
        async with self.processing_semaphore:
            self.stats["total_processed"] += 1
            
            # Handle multiple URLs
            if isinstance(url, list):
                return await self._process_multiple_pdfs(url)
            
            # Tier 1: PyPDF2 text extraction + regular text API (cheapest)
            logger.info(f"Attempting Tier 1: PyPDF2 text extraction + text API for {url[:80]}...")
            try:
                text = await self._tier1_extract_text(url)
                if text and self._is_good_text_quality(text):
                    summary = await self._summarize_with_text_api(text, "comprehensive")
                    cost = self._estimate_text_api_cost(text)
                    self.stats["tier1_success"] += 1
                    self.stats["tier1_cost"] += cost
                    self.stats["total_cost"] += cost
                    logger.info(f"Tier 1 successful - PyPDF2 + text API (cost: ${cost:.3f})")
                    return summary, "tier1_pypdf2_text_api", cost
                else:
                    logger.warning(f"Tier 1 failed: Poor text quality from {url[:80]}")
            except Exception as e:
                logger.warning(f"Tier 1 failed for {url[:80]}: {type(e).__name__}: {str(e)}")
            
            # For now, if Tier 1 fails, return an error
            # (Tier 2 and 3 would require additional async implementations)
            raise Exception("PDF processing failed - only Tier 1 is currently implemented in async mode")
    
    async def _tier1_extract_text(self, url: str) -> Optional[str]:
        """Tier 1: Extract text using PyPDF2 (async)"""
        # Validate URL
        if not url or len(url) > MAX_URL_LENGTH:
            raise ValueError(f"Invalid URL length: {len(url) if url else 0}")
        
        parsed = urlparse(url)
        if parsed.scheme not in ['http', 'https']:
            raise ValueError("URL must use HTTP or HTTPS")
        
        # Download PDF asynchronously
        pdf_content = await self._download_pdf(url)
        if not pdf_content:
            return None
        
        # Extract text in thread pool (CPU-intensive)
        text = await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self._extract_text_from_pdf,
            pdf_content
        )
        
        return text
    
    def _extract_text_from_pdf(self, pdf_content: bytes) -> Optional[str]:
        """Extract text from PDF content (synchronous, runs in thread pool)"""
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                tmp.write(pdf_content)
                tmp.flush()
                
                reader = PdfReader(tmp.name)
                if len(reader.pages) > MAX_PAGES:
                    logger.warning(f"PDF has {len(reader.pages)} pages, truncating to {MAX_PAGES}")
                
                all_text = []
                for i, page in enumerate(reader.pages[:MAX_PAGES]):
                    try:
                        text = page.extract_text()
                        if text.strip():
                            all_text.append(f"--- PAGE {i+1} ---\n{text}")
                    except Exception as e:
                        logger.debug(f"Failed to extract page {i+1}: {e}")
                        continue
                
                combined_text = "\n".join(all_text)
                return self._normalize_text(combined_text) if combined_text.strip() else None
                
        except Exception as e:
            logger.debug(f"PyPDF2 extraction failed: {e}")
            return None
    
    async def _download_pdf(self, url: str) -> Optional[bytes]:
        """Download PDF asynchronously with size limits"""
        async with self.download_semaphore:
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {"User-Agent": "Engagic-Agenda-Processor/3.0"}
                    timeout = aiohttp.ClientTimeout(total=60)
                    
                    async with session.get(url, headers=headers, timeout=timeout) as response:
                        response.raise_for_status()
                        
                        # Check content length
                        content_length = response.headers.get("content-length")
                        if content_length and int(content_length) > MAX_PDF_SIZE:
                            logger.error(f"PDF too large: {content_length} bytes")
                            return None
                        
                        # Download with size checking
                        chunks = []
                        downloaded = 0
                        async for chunk in response.content.iter_chunked(8192):
                            downloaded += len(chunk)
                            if downloaded > MAX_PDF_SIZE:
                                logger.error("PDF exceeds maximum size")
                                return None
                            chunks.append(chunk)
                        
                        return b"".join(chunks)
                        
            except Exception as e:
                logger.error(f"Failed to download PDF: {e}")
                return None
    
    async def _summarize_with_text_api(self, text: str, style: str = "comprehensive") -> str:
        """Summarize extracted text using async Anthropic API"""
        page_count = self._estimate_page_count(text)
        text_size = len(text)
        max_size = 75000  # Conservative limit for text API
        
        logger.info(f"Summarizing {page_count} pages ({text_size} chars) using async text API")
        
        # Use different approaches based on document complexity
        if page_count <= 30 and text_size <= max_size:
            # Short documents: use simple, focused approach
            logger.info("Using short agenda summarization approach")
            return await self._summarize_short_agenda(text)
        elif text_size > max_size:
            # Large documents: use chunking approach
            logger.info(f"Text too large ({text_size} chars), using chunking approach")
            return await self._summarize_with_chunking(text, style)
        else:
            # Medium documents: use comprehensive single-pass approach
            logger.info("Using comprehensive single-pass summarization")
            return await self._summarize_comprehensive_single(text)
    
    async def _summarize_short_agenda(self, text: str) -> str:
        """Summarize short agendas with simple, focused approach (async)"""
        try:
            response = await self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=3000,
                messages=[{
                    "role": "user",
                    "content": f"""This is a city council meeting agenda. Provide a clear, concise summary that covers:

                    **Key Agenda Items:**
                    - List the main topics/issues being discussed
                    - Include any public hearings or votes
                    - Note any budget or financial items

                    **Important Details:**
                    - Specific addresses, dollar amounts, ordinance numbers
                    - Deadlines or implementation dates
                    - Public participation opportunities

                    Keep it brief but informative. Focus on what citizens need to know.

                    Agenda text:
                    {text}"""
                }]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Short agenda summarization failed: {e}")
            raise
    
    async def _summarize_comprehensive_single(self, text: str) -> str:
        """Comprehensive single-pass summarization for medium-sized documents (async)"""
        try:
            response = await self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                messages=[{
                    "role": "user", 
                    "content": f"""Analyze this city council meeting agenda and provide a comprehensive summary for residents.
                    
                    Focus on extracting all important information that affects residents.
                    Format as organized sections with bullet points. Be thorough and detailed.
                    Skip pure administrative items unless they have significant public impact.

                    Agenda text:
                    {text}"""
                }]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Comprehensive summarization failed: {e}")
            raise
    
    async def _summarize_with_chunking(self, text: str, style: str = "comprehensive") -> str:
        """Summarize large text using smart chunking approach (async)"""
        chunks = self._chunk_by_agenda_items(text)
        logger.info(f"Split into {len(chunks)} chunks for async processing")
        
        # Process chunks concurrently with rate limiting
        tasks = []
        for i, chunk in enumerate(chunks):
            task = self._process_chunk(chunk, i, len(chunks))
            tasks.append(task)
        
        # Wait for all chunks to complete
        summaries = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle results
        final_summaries = []
        for i, summary in enumerate(summaries):
            if isinstance(summary, Exception):
                logger.error(f"Error processing chunk {i + 1}: {summary}")
                final_summaries.append(f"--- SECTION {i + 1} SUMMARY ---\n[ERROR: Could not process this section]\n")
            else:
                final_summaries.append(f"--- SECTION {i + 1} SUMMARY ---\n{summary}\n")
        
        return "\n".join(final_summaries)
    
    async def _process_chunk(self, chunk: str, index: int, total: int) -> str:
        """Process a single chunk asynchronously"""
        logger.info(f"Processing chunk {index + 1}/{total}...")
        
        # Add some jitter to avoid rate limit bursts
        await asyncio.sleep(index * 0.5)
        
        chunk_prompt = f"""Analyze this portion of a city council meeting agenda packet and extract the key information 
        that residents should know about. Focus on important details and public impact.

        Text to analyze:
        {chunk}"""
        
        response = await self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            messages=[{"role": "user", "content": chunk_prompt}]
        )
        
        return response.content[0].text
    
    async def _process_multiple_pdfs(self, urls: List[str]) -> tuple[str, str, float]:
        """Process multiple PDFs concurrently and combine summaries"""
        logger.info(f"Processing {len(urls)} PDFs concurrently")
        
        # Process PDFs concurrently
        tasks = []
        for i, url in enumerate(urls, 1):
            task = self._process_single_pdf(url, i, len(urls))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results
        summaries = []
        total_cost = 0.0
        methods_used = []
        
        for i, result in enumerate(results, 1):
            if isinstance(result, Exception):
                logger.error(f"Failed to process PDF {i}: {result}")
                summaries.append(f"=== DOCUMENT {i} ===\n[Error: Could not process]")
            else:
                summary, method, cost = result
                summaries.append(f"=== DOCUMENT {i} ===\n{summary}")
                total_cost += cost
                methods_used.append(method)
        
        combined_summary = "\n\n".join(summaries)
        combined_method = f"multiple_pdfs_{len(urls)}_docs"
        
        return combined_summary, combined_method, total_cost
    
    async def _process_single_pdf(self, url: str, index: int, total: int) -> tuple[str, str, float]:
        """Process a single PDF from a list"""
        logger.info(f"Processing PDF {index}/{total}: {url[:80]}...")
        return await self.process_agenda_optimal(url)
    
    def _chunk_by_agenda_items(self, text: str, max_chunk_size: int = 75000) -> List[str]:
        """Smart chunking that respects agenda item boundaries"""
        # Look for agenda item patterns
        agenda_patterns = [
            r"\n\s*\d+\.\s+[A-Z]",  # "1. ITEM NAME"
            r"\n\s*[A-Z]\.\s+[A-Z]",  # "A. ITEM NAME"
            r"\n\s*Item\s+\d+",  # "Item 1"
            r"\n\s*AGENDA\s+ITEM",  # "AGENDA ITEM"
        ]

        # Find all potential split points
        split_points = [0]
        for pattern in agenda_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                split_points.append(match.start())

        split_points = sorted(set(split_points))
        split_points.append(len(text))

        # Group split points into appropriately sized chunks
        chunks = []
        current_chunk_start = 0

        for i in range(1, len(split_points)):
            chunk_end = split_points[i]
            chunk_size = chunk_end - current_chunk_start

            if chunk_size > max_chunk_size and chunks:
                # Start new chunk
                chunk_text = text[current_chunk_start : split_points[i - 1]]
                chunks.append(chunk_text)
                current_chunk_start = split_points[i - 1]
            elif i == len(split_points) - 1:
                # Last chunk
                chunk_text = text[current_chunk_start:chunk_end]
                chunks.append(chunk_text)

        # Fallback to simple chunking if no agenda patterns found
        if len(chunks) <= 1:
            return self._simple_chunk(text, max_chunk_size)

        return chunks

    def _simple_chunk(self, text: str, chunk_size: int) -> List[str]:
        """Fallback chunking by character count with page boundaries"""
        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            # Try to break on page boundary
            if end < len(text):
                page_break = text.rfind("--- PAGE", start, end)
                if page_break > start + chunk_size // 2:
                    end = page_break

            chunks.append(text[start:end])
            start = end

        return chunks
    
    def _is_good_text_quality(self, text: str) -> bool:
        """Validate if extracted text is good quality"""
        if not text or len(text) < 100:
            return False
        
        # Check character distribution
        letters = sum(1 for c in text if c.isalpha())
        total_chars = len(text)
        
        if total_chars == 0:
            return False
        
        letter_ratio = letters / total_chars
        if letter_ratio < 0.3:  # Too few letters indicates poor extraction
            return False
        
        # Check for actual words
        words = text.split()
        if len(words) < 20:
            return False
        
        # Check for recognizable English words
        sample_words = words[:100]
        recognizable = sum(1 for word in sample_words if word.lower().strip('.,!?();:') in self.english_words)
        
        if len(sample_words) >= 50 and recognizable < 5:
            return False
        
        return True
    
    def _normalize_text(self, text: str) -> str:
        """Clean up and normalize extracted text"""
        # Remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        
        # Fix common extraction issues
        text = text.replace('|', 'I')  # Common OCR mistake
        text = text.replace('‚', ',')  # Unicode comma issue
        
        return text.strip()
    
    def _estimate_page_count(self, text: str) -> int:
        """Estimate page count from text"""
        # Look for page markers first
        page_markers = re.findall(r'--- PAGE (\d+) ---', text)
        if page_markers:
            return len(page_markers)
        
        # Estimate based on character count
        chars_per_page = 3000
        return max(1, len(text) // chars_per_page)
    
    def _estimate_text_api_cost(self, text: str) -> float:
        """Estimate cost for text API usage"""
        # Rough estimate: ~750 characters per token, ~$0.003 per 1K tokens for Claude
        tokens = len(text) // 750
        return (tokens / 1000) * 0.003
    
    async def close(self):
        """Clean up resources"""
        self.executor.shutdown(wait=False)