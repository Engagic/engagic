"""
Engagic Optimal PDF Processing Stack

Three-tier approach for maximum quality and cost efficiency:
Tier 1: PyPDF2 text extraction + regular text API (free extraction, lowest cost)
Tier 2: Mistral OCR API + regular text API ($1/1000 pages)
Tier 3: Claude PDF API (most expensive, last resort)

Key features:
- Smart text quality validation to avoid wasting money
- Proper API usage (text extraction uses text API, not PDF API)
- Cost tracking and processing statistics
- Robust error handling and fallback logic
"""

import os
import re
import time
import logging
import tempfile
import requests
import anthropic
from typing import List, Dict, Any, Optional, Union
from urllib.parse import urlparse
from pathlib import Path

# PDF processing
from PyPDF2 import PdfReader

# Our modules
from databases import DatabaseManager
from config import config

logger = logging.getLogger("engagic")

# Security and processing limits
MAX_PDF_SIZE = 200 * 1024 * 1024  # 200MB max
MAX_PAGES = 1000  # Maximum pages to process
MAX_URL_LENGTH = 2000


class ProcessingError(Exception):
    """Base exception for PDF processing errors"""
    pass


def validate_url(url: str) -> None:
    """Validate URL for security"""
    if not url or len(url) > MAX_URL_LENGTH:
        raise ValueError(f"Invalid URL length: {len(url) if url else 0}")
    
    parsed = urlparse(url)
    if not parsed.scheme in ['http', 'https']:
        raise ValueError("URL must use HTTP or HTTPS")
    
    if not parsed.netloc:
        raise ValueError("URL must have a valid domain")


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file operations"""
    # Remove directory traversal attempts
    filename = os.path.basename(filename)
    # Remove/replace unsafe characters
    filename = re.sub(r'[^\w\-_\.]', '_', filename)
    return filename[:255]  # Limit length


class AgendaProcessor:
    """Optimal three-tier PDF processor for cost-effective, high-quality results"""
    
    def __init__(self, api_key: Optional[str] = None, mistral_api_key: Optional[str] = None):
        """Initialize the processor
        
        Args:
            api_key: Anthropic API key (or uses environment variables)
            mistral_api_key: Mistral API key for Tier 2 (optional)
        """
        # Initialize Anthropic client
        self.api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or config.get_api_key()
        if not self.api_key:
            raise ValueError("API key required - set LLM_API_KEY or ANTHROPIC_API_KEY environment variable")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        
        # Initialize database
        self.db = DatabaseManager(
            locations_db_path=config.LOCATIONS_DB_PATH,
            meetings_db_path=config.MEETINGS_DB_PATH,
            analytics_db_path=config.ANALYTICS_DB_PATH,
        )
        
        # Initialize Mistral OCR if available
        self.mistral_api_key = mistral_api_key or os.getenv("MISTRAL_API_KEY")
        self.mistral_client = None
        if self.mistral_api_key:
            try:
                from mistralai import Mistral
                self.mistral_client = Mistral(api_key=self.mistral_api_key)
                logger.info("Mistral OCR client initialized")
            except ImportError:
                logger.warning("Mistral SDK not available - Tier 2 disabled")
        
        # Initialize Claude PDF API processor for Tier 3
        if self.api_key:
            try:
                from pdf_api_processor import PDFAPIProcessor
                self.pdf_processor = PDFAPIProcessor(self.api_key)
                logger.info("Claude PDF API processor initialized")
            except ImportError:
                logger.warning("PDF API processor not available - Tier 3 disabled")
                self.pdf_processor = None
        else:
            logger.info("No API key available - PDF API processor disabled")
            self.pdf_processor = None
        
        # Load basic English words for validation
        self.english_words = self._load_basic_english_words()
        
        # Processing statistics
        self.stats = {
            "tier1_success": 0,
            "tier2_success": 0, 
            "tier3_success": 0,
            "total_processed": 0,
            "total_cost": 0.0,
            "tier1_cost": 0.0,  # Text API cost for PyPDF2
            "tier2_cost": 0.0,  # Mistral OCR + text API cost
            "tier3_cost": 0.0   # PDF API cost
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
        
        # Try to load NLTK words if available
        try:
            from nltk.corpus import words
            return civic_words.union(set(word.lower() for word in words.words()[:5000]))
        except:
            return civic_words
    
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
        
        # Check cache first
        cached_meeting = self.db.get_cached_summary(packet_url)
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
        logger.info(f"Cache miss for {packet_url} - processing with optimal tiered approach...")
        start_time = time.time()
        
        try:
            # Process the agenda
            summary, method, cost = self.process_agenda_optimal(packet_url)
            
            # Store in database
            processing_time = time.time() - start_time
            meeting_data["processed_summary"] = summary
            meeting_data["processing_time_seconds"] = processing_time
            meeting_data["processing_method"] = method
            meeting_data["processing_cost"] = cost
            
            meeting_id = self.db.store_meeting_summary(meeting_data, summary, processing_time)
            
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
    
    def process_agenda_optimal(self, url: Union[str, List[str]]) -> tuple[str, str, float]:
        """Process agenda using optimal three-tier approach
        
        Args:
            url: Single URL string or list of URLs
            
        Returns:
            Tuple of (summary, method_used, cost)
        """
        self.stats["total_processed"] += 1
        
        # Handle multiple URLs
        if isinstance(url, list):
            return self._process_multiple_pdfs(url)
        
        # Tier 1: PyPDF2 text extraction + regular text API (cheapest)
        logger.info(f"Attempting Tier 1: PyPDF2 text extraction + text API for {url[:80]}...")
        try:
            text = self._tier1_extract_text(url)
            if text and self._is_good_text_quality(text):
                summary = self._summarize_with_text_api(text, "comprehensive")
                cost = self._estimate_text_api_cost(text)
                self.stats["tier1_success"] += 1
                self.stats["tier1_cost"] += cost
                self.stats["total_cost"] += cost
                logger.info(f"Tier 1 successful - PyPDF2 + text API (cost: ${cost:.3f})")
                return summary, "tier1_pypdf2_text_api", cost
            else:
                if not text:
                    logger.warning(f"Tier 1 failed: No text extracted from PDF {url[:80]}")
                else:
                    logger.warning(f"Tier 1 failed: Poor text quality - {len(text)} chars extracted from {url[:80]}")
        except Exception as e:
            logger.warning(f"Tier 1 failed for {url[:80]}: {type(e).__name__}: {str(e)}")
        
        # Tier 2: Mistral OCR + regular text API (moderate cost)
        if self.mistral_client:
            logger.info(f"Attempting Tier 2: Mistral OCR + text API for {url[:80]}...")
            try:
                text, ocr_cost = self._tier2_mistral_ocr(url)
                if text and self._is_good_text_quality(text):
                    summary = self._summarize_with_text_api(text, "comprehensive")
                    text_cost = self._estimate_text_api_cost(text)
                    total_cost = ocr_cost + text_cost
                    self.stats["tier2_success"] += 1
                    self.stats["tier2_cost"] += total_cost
                    self.stats["total_cost"] += total_cost
                    logger.info(f"Tier 2 successful - Mistral OCR + text API (cost: ${total_cost:.3f})")
                    return summary, "tier2_mistral_text_api", total_cost
                else:
                    if not text:
                        logger.warning(f"Tier 2 failed: No text from Mistral OCR for {url[:80]}")
                    else:
                        logger.warning(f"Tier 2 failed: Poor OCR quality - {len(text)} chars from {url[:80]}")
            except Exception as e:
                logger.warning(f"Tier 2 failed for {url[:80]}: {type(e).__name__}: {str(e)}")
        else:
            logger.debug("Tier 2 skipped: No Mistral client available")
        
        # Tier 3: Claude PDF API (most expensive, last resort)
        if self.pdf_processor:
            logger.info(f"Attempting Tier 3: Claude PDF API for {url[:80]}...")
            try:
                summary = self._tier3_claude_pdf_api(url)
                if summary:
                    cost = 15.0  # Rough estimate for PDF API
                    self.stats["tier3_success"] += 1
                    self.stats["tier3_cost"] += cost
                    self.stats["total_cost"] += cost
                    logger.info(f"Tier 3 successful - Claude PDF API (cost: ${cost:.3f})")
                    return summary, "tier3_claude_pdf_api", cost
                else:
                    logger.error(f"Tier 3 failed: No summary returned from PDF API for {url[:80]}")
            except Exception as e:
                logger.error(f"Tier 3 failed for {url[:80]}: {type(e).__name__}: {str(e)}")
        else:
            logger.debug("Tier 3 skipped: No PDF processor available (API key missing)")
        
        # All tiers failed - provide detailed explanation
        failure_reasons = []
        if "docs.google.com/gview" in url:
            failure_reasons.append("Google Docs viewer URLs are not directly processable")
        if not self.api_key:
            failure_reasons.append("No API key available for AI processing")
        if not self.pdf_processor:
            failure_reasons.append("PDF API processor not available")
        
        reason_str = "; ".join(failure_reasons) if failure_reasons else "Unknown reasons"
        logger.error(f"All processing tiers failed for {url[:80]} - {reason_str}")
        raise ProcessingError(f"All processing tiers failed - {reason_str}")
    
    def _tier1_extract_text(self, url: str) -> Optional[str]:
        """Tier 1: Extract text using PyPDF2
        
        Args:
            url: PDF URL to process
            
        Returns:
            Extracted text if successful, None otherwise
        """
        validate_url(url)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Download PDF
            pdf_content = self._download_pdf(url)
            if not pdf_content:
                return None
            
            pdf_path = os.path.join(temp_dir, "agenda.pdf")
            with open(pdf_path, "wb") as f:
                f.write(pdf_content)
            
            # Extract text with PyPDF2
            try:
                reader = PdfReader(pdf_path)
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
    
    def _tier2_mistral_ocr(self, url: str) -> tuple[Optional[str], float]:
        """Tier 2: Use Mistral OCR API
        
        Args:
            url: PDF URL to process
            
        Returns:
            Tuple of (extracted_text, ocr_cost)
        """
        if not self.mistral_client:
            return None, 0.0
        
        try:
            # Download PDF first
            pdf_content = self._download_pdf(url)
            if not pdf_content:
                return None, 0.0
            
            # Convert to base64 for Mistral API
            import base64
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
            
            # Call Mistral OCR API
            response = self.mistral_client.chat.complete(
                model="mistral-ocr-latest",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all text from this PDF document. Preserve the structure and formatting."},
                        {"type": "pdf", "pdf": pdf_base64}
                    ]
                }]
            )
            
            text = response.choices[0].message.content
            
            # Estimate cost (roughly $1 per 1000 pages, estimate pages from PDF size)
            estimated_pages = max(1, len(pdf_content) // 50000)  # Rough estimate
            cost = estimated_pages * 0.001  # $1 per 1000 pages
            
            logger.info(f"Mistral OCR processed ~{estimated_pages} pages, cost: ${cost:.3f}")
            
            return self._normalize_text(text) if text else None, cost
            
        except Exception as e:
            logger.error(f"Mistral OCR failed: {e}")
            return None, 0.0
    
    def _tier3_claude_pdf_api(self, url: str) -> Optional[str]:
        """Tier 3: Use Claude PDF API with optimized prompt
        
        Args:
            url: PDF URL to process
            
        Returns:
            Summary from PDF API
        """
        if not self.pdf_processor:
            return None
        
        try:
            # Try URL method first, then fallback to base64
            try:
                summary = self.pdf_processor.process(url, method="url")
                return summary
            except Exception as url_error:
                logger.warning(f"PDF API URL method failed: {url_error}, trying base64...")
                summary = self.pdf_processor.process(url, method="base64")
                return summary
        except Exception as e:
            logger.error(f"Claude PDF API failed: {e}")
            return None
    
    def _summarize_with_text_api(self, text: str, style: str = "comprehensive") -> str:
        """Summarize extracted text using optimal approach based on document size
        
        Args:
            text: Extracted text to summarize
            style: Summary style (comprehensive, brief)
            
        Returns:
            Summary text
        """
        page_count = self._estimate_page_count(text)
        text_size = len(text)
        max_size = 75000  # Conservative limit for text API
        
        logger.info(f"Summarizing {page_count} pages ({text_size} chars) using text API")
        
        # Use different approaches based on document complexity
        if page_count <= 30 and text_size <= max_size:
            # Short documents: use simple, focused approach
            logger.info("Using short agenda summarization approach")
            return self._summarize_short_agenda(text)
        elif text_size > max_size:
            # Large documents: use chunking approach
            logger.info(f"Text too large ({text_size} chars), using chunking approach")
            return self._summarize_with_chunking(text, style)
        else:
            # Medium documents: use comprehensive single-pass approach
            logger.info("Using comprehensive single-pass summarization")
            return self._summarize_comprehensive_single(text)
    
    def _summarize_short_agenda(self, text: str) -> str:
        """Summarize short agendas with simple, focused approach"""
        try:
            response = self.client.messages.create(
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
    
    def _summarize_comprehensive_single(self, text: str) -> str:
        """Comprehensive single-pass summarization for medium-sized documents"""
        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                messages=[{
                    "role": "user", 
                    "content": f"""Analyze this city council meeting agenda and provide a comprehensive summary for residents.
                    **Complete Agenda Items** (list every single one):
                    - Item number and full title
                    - Complete description of what's being proposed
                    - Department or presenter
                    - Action required (vote, discussion, information only)

                    **Financial Details** (every dollar amount):
                    - Budget items with exact amounts
                    - Contract values and vendors
                    - Grant amounts and sources
                    - Fee changes or rate adjustments

                    **Property and Development** (all locations):
                    - Complete addresses for any property discussed
                    - Zoning changes with current and proposed zoning
                    - Development project names and descriptions
                    - Square footage, units, or measurements

                    **Public Participation**:
                    - Public hearing items with times
                    - Comment period details
                    - How to participate (in person, online, written)
                    - Deadlines for input

                    **Key Details to Preserve**:
                    - Exact dollar amounts (not "several million" but "$3,456,789")
                    - Complete addresses (not "downtown" but "123 Main Street")
                    - Full names and titles
                    - Precise dates and times
                    - Ordinance and resolution numbers

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
    
    def _summarize_with_chunking(self, text: str, style: str = "comprehensive") -> str:
        """Summarize large text using smart chunking approach"""
        chunks = self._chunk_by_agenda_items(text)
        logger.info(f"Split into {len(chunks)} chunks for processing")
        
        summaries = []
        rate_limit_delay = 2  # Conservative delay between API calls
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i + 1}/{len(chunks)}...")
            
            try:
                chunk_prompt = f"""Analyze this portion of a city council meeting agenda packet and extract the key information 
                that residents should know about. Focus on:

                1. **Agenda Items**: What specific issues/proposals are being discussed?
                2. **Public Impact**: How might these affect residents' daily lives?
                3. **Financial Details**: Any budget items, costs, or financial impacts
                4. **Location/Property Details**: Specific addresses, developments, or geographic areas affected
                5. **Timing**: When things will happen, deadlines, or implementation dates
                6. **Public Participation**: Opportunities for public comment or hearings

                Format as clear bullet points. Preserve specific details like addresses, dollar amounts, ordinance numbers, and dates. 
                Skip pure administrative items unless they have significant public impact.

                Text to analyze:
                {chunk}"""
                
                response = self.client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=4000,
                    messages=[{"role": "user", "content": chunk_prompt}]
                )
                
                summaries.append(f"--- SECTION {i + 1} SUMMARY ---\n{response.content[0].text}\n")
                
                # Rate limiting between chunks
                if i < len(chunks) - 1:
                    logger.debug(f"Waiting {rate_limit_delay} seconds...")
                    time.sleep(rate_limit_delay)
                    
            except Exception as e:
                logger.error(f"Error processing chunk {i + 1}: {e}")
                summaries.append(f"--- SECTION {i + 1} SUMMARY ---\n[ERROR: Could not process this section - {str(e)}]\n")
        
        return "\n".join(summaries)
    
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
    
    def _process_multiple_pdfs(self, urls: List[str]) -> tuple[str, str, float]:
        """Process multiple PDFs and combine summaries
        
        Args:
            urls: List of PDF URLs
            
        Returns:
            Tuple of (combined_summary, method_used, total_cost)
        """
        logger.info(f"Processing {len(urls)} PDFs")
        summaries = []
        total_cost = 0.0
        methods_used = []
        
        for i, url in enumerate(urls, 1):
            logger.info(f"Processing PDF {i}/{len(urls)}: {url[:80]}...")
            try:
                summary, method, cost = self.process_agenda_optimal(url)
                summaries.append(f"=== DOCUMENT {i} ===\n{summary}")
                total_cost += cost
                methods_used.append(method)
            except Exception as e:
                logger.error(f"Failed to process PDF {i}: {e}")
                summaries.append(f"=== DOCUMENT {i} ===\n[Error: Could not process]")
        
        combined_summary = "\n\n".join(summaries)
        combined_method = f"multiple_pdfs_{len(urls)}_docs"
        
        return combined_summary, combined_method, total_cost
    
    def _download_pdf(self, url: str) -> Optional[bytes]:
        """Download PDF with validation and size limits"""
        try:
            response = requests.get(
                url,
                timeout=30,
                stream=True,
                headers={"User-Agent": "Engagic-Agenda-Processor/3.0"}
            )
            response.raise_for_status()
            
            # Check content length
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_PDF_SIZE:
                logger.error(f"PDF too large: {content_length} bytes")
                return None
            
            # Download with size checking
            pdf_content = b""
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded > MAX_PDF_SIZE:
                        logger.error("PDF exceeds maximum size")
                        return None
                    pdf_content += chunk
            
            return pdf_content
            
        except Exception as e:
            logger.error(f"Failed to download PDF: {e}")
            return None
    
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
        
        # Check for excessive single-character "words" (sign of bad extraction)
        single_chars = sum(1 for word in sample_words if len(word) == 1)
        if len(sample_words) >= 50 and single_chars > 20:
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
    
    def process_batch_agendas(
        self, 
        batch_requests: List[Dict[str, str]], 
        wait_for_results: bool = True,
        return_raw: bool = False
    ) -> List[Dict[str, Any]]:
        """Process multiple agendas using Anthropic's Batch API for 50% cost savings
        
        Args:
            batch_requests: List of {"url": packet_url, "custom_id": custom_id}
            wait_for_results: Whether to wait for batch completion (default True)
            return_raw: Whether to return raw batch results (default False)
            
        Returns:
            List of processing results matching the input custom_ids
        """
        if not batch_requests:
            return []
            
        logger.info(f"Processing {len(batch_requests)} agendas using Batch API (50% cost savings)")
        
        try:
            # Prepare batch API requests
            api_requests = []
            for req in batch_requests:
                # Extract text first using tier 1 approach
                try:
                    text = self._tier1_extract_text(req["url"])
                    if not text or not self._is_good_text_quality(text):
                        # Skip this request if text extraction fails
                        logger.warning(f"Skipping {req['custom_id']} - failed text extraction")
                        continue
                        
                    # Determine processing approach based on text size
                    text_size = len(text)
                    page_count = self._estimate_page_count(text)
                    
                    if page_count <= 30 and text_size <= 75000:
                        # Short agenda approach
                        prompt = f"""This is a city council meeting agenda. Provide a clear, concise summary that covers:

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
                    elif text_size <= 75000:
                        # Comprehensive single-pass approach
                        prompt = f"""Analyze this city council meeting agenda and provide a comprehensive summary for residents.
                        **Complete Agenda Items** (list every single one):
                        - Item number and full title
                        - Complete description of what's being proposed
                        - Department or presenter
                        - Action required (vote, discussion, information only)

                        **Financial Details** (every dollar amount):
                        - Budget items with exact amounts
                        - Contract values and vendors
                        - Grant amounts and sources
                        - Fee changes or rate adjustments

                        **Property and Development** (all locations):
                        - Complete addresses for any property discussed
                        - Zoning changes with current and proposed zoning
                        - Development project names and descriptions
                        - Square footage, units, or measurements

                        **Public Participation**:
                        - Public hearing items with times
                        - Comment period details
                        - How to participate (in person, online, written)
                        - Deadlines for input

                        **Key Details to Preserve**:
                        - Exact dollar amounts (not "several million" but "$3,456,789")
                        - Complete addresses (not "downtown" but "123 Main Street")
                        - Full names and titles
                        - Precise dates and times
                        - Ordinance and resolution numbers

                        Format as organized sections with bullet points. Be thorough and detailed.
                        Skip pure administrative items unless they have significant public impact.

                        Agenda text:
                        {text}"""
                    else:
                        # For very large texts, we'll need chunking - use first chunk for batch
                        chunks = self._chunk_by_agenda_items(text, max_chunk_size=75000)
                        first_chunk = chunks[0] if chunks else text[:75000]
                        prompt = f"""Analyze this portion of a city council meeting agenda packet and extract the key information 
                        that residents should know about. Focus on:

                        1. **Agenda Items**: What specific issues/proposals are being discussed?
                        2. **Public Impact**: How might these affect residents' daily lives?
                        3. **Financial Details**: Any budget items, costs, or financial impacts
                        4. **Location/Property Details**: Specific addresses, developments, or geographic areas affected
                        5. **Timing**: When things will happen, deadlines, or implementation dates
                        6. **Public Participation**: Opportunities for public comment or hearings

                        Format as clear bullet points. Preserve specific details like addresses, dollar amounts, ordinance numbers, and dates. 
                        Skip pure administrative items unless they have significant public impact.

                        Text to analyze:
                        {first_chunk}"""
                    
                    # Create batch API request
                    api_requests.append({
                        "custom_id": req["custom_id"],
                        "params": {
                            "model": "claude-3-5-sonnet-20241022",
                            "max_tokens": 4000,
                            "messages": [{"role": "user", "content": prompt}]
                        }
                    })
                    
                except Exception as e:
                    logger.error(f"Error preparing batch request for {req['custom_id']}: {e}")
                    continue
            
            if not api_requests:
                logger.warning("No valid batch requests to process")
                return []
            
            # Submit to Anthropic Batch API
            batch_response = self.client.messages.batches.create(requests=api_requests)
            batch_id = batch_response.id
            
            logger.info(f"Submitted batch {batch_id} with {len(api_requests)} requests")
            
            if not wait_for_results:
                return [{"batch_id": batch_id, "status": "submitted"}]
            
            # Poll for completion
            max_wait_time = 3600  # 1 hour max wait
            poll_interval = 30    # Check every 30 seconds
            waited_time = 0
            
            while waited_time < max_wait_time:
                batch_status = self.client.messages.batches.retrieve(batch_id)
                
                if batch_status.processing_status == "ended":
                    logger.info(f"Batch {batch_id} completed successfully")
                    break
                elif batch_status.processing_status in ["canceled", "failed"]:
                    logger.error(f"Batch {batch_id} failed with status: {batch_status.processing_status}")
                    return []
                
                logger.info(f"Batch {batch_id} still processing... ({waited_time}s waited)")
                time.sleep(poll_interval)
                waited_time += poll_interval
            
            if waited_time >= max_wait_time:
                logger.error(f"Batch {batch_id} timed out after {max_wait_time}s")
                return []
            
            # Retrieve and process results
            results = []
            for result in self.client.messages.batches.results(batch_id):
                if result.result.type == "succeeded":
                    summary = result.result.message.content[0].text
                    cost = self._estimate_batch_cost(result.result.message.usage)
                    
                    results.append({
                        "custom_id": result.custom_id,
                        "summary": summary,
                        "processing_time": 0,  # Batch processing time not tracked per item
                        "processing_method": "batch_api_tier1",
                        "processing_cost": cost,
                        "success": True
                    })
                elif result.result.type == "errored":
                    logger.error(f"Batch item {result.custom_id} failed: {result.result.error}")
                    results.append({
                        "custom_id": result.custom_id,
                        "error": str(result.result.error),
                        "success": False
                    })
                else:
                    logger.warning(f"Batch item {result.custom_id} status: {result.result.type}")
                    results.append({
                        "custom_id": result.custom_id,
                        "error": f"Batch processing {result.result.type}",
                        "success": False
                    })
            
            # Update stats
            successful_count = sum(1 for r in results if r.get("success"))
            total_cost = sum(r.get("processing_cost", 0) for r in results if r.get("success"))
            
            self.stats["tier1_success"] += successful_count
            self.stats["total_processed"] += len(results)
            self.stats["tier1_cost"] += total_cost
            self.stats["total_cost"] += total_cost
            
            logger.info(f"Batch processing complete: {successful_count}/{len(results)} successful, ${total_cost:.3f} total cost")
            
            return results
            
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            return []
    
    def _estimate_batch_cost(self, usage) -> float:
        """Estimate cost for batch API usage (50% of regular pricing)"""
        if not usage:
            return 0.0
        
        input_tokens = getattr(usage, 'input_tokens', 0)
        output_tokens = getattr(usage, 'output_tokens', 0)
        
        # Batch pricing is 50% of regular pricing for Claude 3.5 Sonnet
        input_cost = (input_tokens / 1000) * 1.50  # $1.50 per 1K tokens (batch rate)
        output_cost = (output_tokens / 1000) * 7.50  # $7.50 per 1K tokens (batch rate)
        
        return input_cost + output_cost
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get comprehensive processing statistics"""
        total = self.stats["total_processed"]
        if total == 0:
            return self.stats
        
        return {
            **self.stats,
            "tier1_percentage": (self.stats["tier1_success"] / total) * 100,
            "tier2_percentage": (self.stats["tier2_success"] / total) * 100,
            "tier3_percentage": (self.stats["tier3_success"] / total) * 100,
            "average_cost": self.stats["total_cost"] / total if total > 0 else 0,
            "cost_breakdown": {
                "tier1_cost": self.stats["tier1_cost"],
                "tier2_cost": self.stats["tier2_cost"], 
                "tier3_cost": self.stats["tier3_cost"]
            }
        }
    
    def process_agenda(self, url: str, **kwargs) -> str:
        """Legacy compatibility method - use process_agenda_optimal instead"""
        summary, method, cost = self.process_agenda_optimal(url)
        return summary

def create_processor(**kwargs) -> AgendaProcessor:
    """Create an optimal processor instance"""
    return AgendaProcessor(**kwargs)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python fullstack.py <pdf_url>")
        sys.exit(1)
    
    processor = create_processor()
    
    test_url = sys.argv[1]
    summary, method, cost = processor.process_agenda_optimal(test_url)
    
    print("=== SUMMARY ===")
    print(summary)
    print(f"\n=== PROCESSING INFO ===")
    print(f"Method: {method}")
    print(f"Cost: ${cost:.3f}")
    print(f"\n=== STATS ===")
    stats = processor.get_processing_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")
