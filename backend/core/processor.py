"""
PDF Processing Stack for Engagic - Free Tier (Tier 1 Only)

STRATEGY: Fail fast with simple, cost-effective processing
- Tier 1: PyPDF2 + Gemini (60% success rate, ~$0.001/doc, ~2-5s)
- If Tier 1 fails: raise error immediately (document needs paid tier)

Premium tiers (Tier 2 Mistral OCR, Tier 3 Gemini PDF) archived for future use.
See: backend/archived/premium_processing_tiers.py

Key features:
- Smart model selection (Flash vs Flash-Lite based on document size)
- No chunking needed (1M+ token context window)
- Batch processing support for 50% cost savings
- Simple, clean implementation without complex fallback logic
"""

import os
import re
import time
import json
import hashlib
import logging
import tempfile
import requests
from typing import List, Dict, Any, Optional, Union
from urllib.parse import urlparse
from dataclasses import dataclass
from enum import Enum

# PDF processing
from PyPDF2 import PdfReader

# Google AI
from google import genai
from google.genai import types

# Our modules
from backend.database import UnifiedDatabase
from backend.core.config import config

logger = logging.getLogger("engagic")

# Security and processing limits
MAX_PDF_SIZE = 200 * 1024 * 1024  # 200MB max
MAX_PAGES = 1000  # Maximum pages to process
MAX_URL_LENGTH = 2000

# Model thresholds
FLASH_LITE_MAX_CHARS = 200000  # Use Flash-Lite for documents under ~200K chars
FLASH_LITE_MAX_PAGES = 50      # Or under 50 pages


class ProcessingError(Exception):
    """Base exception for PDF processing errors"""
    pass


class ResultType(Enum):
    """Result type for batch processing"""
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class BatchMessage:
    """Message content from batch processing"""
    content: List[Dict[str, str]]


@dataclass 
class BatchResult:
    """Result from batch processing"""
    custom_id: str
    result_type: ResultType
    message: Optional[BatchMessage] = None
    error: Optional[str] = None


def validate_url(url: str) -> None:
    """Validate URL for security"""
    if not url or len(url) > MAX_URL_LENGTH:
        raise ValueError(f"Invalid URL length: {len(url) if url else 0}")
    
    parsed = urlparse(url)
    if parsed.scheme not in ['http', 'https']:
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
    """PDF processor optimized for cost and quality"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the processor

        Args:
            api_key: API key (or uses environment variables)
        """
        # Initialize client
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
        if not self.api_key:
            raise ValueError("API key required - set GEMINI_API_KEY or LLM_API_KEY environment variable")

        # Initialize client (will use GEMINI_API_KEY env var if api_key is None)
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = genai.Client()  # Uses GEMINI_API_KEY from environment

        # Model names for selection
        self.flash_model_name = 'gemini-2.5-flash'
        self.flash_lite_model_name = 'gemini-2.5-flash-lite'

        # Initialize unified database
        self.db = UnifiedDatabase(config.UNIFIED_DB_PATH)

        # Load basic English words for validation
        self.english_words = self._load_basic_english_words()
    
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
        except Exception:
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
        
        # Extract city context for logging
        city_banana = meeting_data.get("city_banana", "unknown")

        # Check cache first
        cached_meeting = self.db.get_cached_summary(packet_url)
        if cached_meeting:
            logger.info(f"[Cache] HIT - {city_banana}")

            return {
                "success": True,
                "summary": cached_meeting.summary,
                "processing_time": cached_meeting.processing_time or 0,
                "cached": True,
                "meeting_data": cached_meeting.to_dict(),
                "processing_method": cached_meeting.processing_method or "cached"
            }

        # Process with Gemini
        logger.info(f"[Cache] MISS - {city_banana}")
        start_time = time.time()

        try:
            # Process the agenda
            summary, method = self.process_agenda_optimal(packet_url)

            # Store in database
            processing_time = time.time() - start_time
            meeting_data["processed_summary"] = summary
            meeting_data["processing_time_seconds"] = processing_time
            meeting_data["processing_method"] = method

            # Update meeting with summary
            meeting_id = meeting_data.get("meeting_id")
            if meeting_id:
                self.db.update_meeting_summary(meeting_id, summary, method, processing_time)

            # Store in processing_cache
            self._store_in_processing_cache(packet_url, summary, processing_time)

            logger.info(f"[Processing] SUCCESS - {city_banana}")

            return {
                "success": True,
                "summary": summary,
                "processing_time": processing_time,
                "cached": False,
                "meeting_data": meeting_data,
                "meeting_id": meeting_id,
                "processing_method": method
            }

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"[Processing] FAILED - {city_banana} - {type(e).__name__}: {e}")
            return {
                "success": False,
                "error": str(e),
                "processing_time": processing_time,
                "cached": False
            }
    
    def process_agenda_optimal(self, url: Union[str, List[str]]) -> tuple[str, str]:
        """Process agenda using Tier 1 (PyPDF2 + Gemini) - fail fast approach

        FREE TIER STRATEGY:
        - Try Tier 1: PyPDF2 text extraction + Gemini (60% success rate)
        - If it fails: raise error immediately (no expensive fallbacks)
        - Premium tiers archived in backend/archived/premium_processing_tiers.py

        Args:
            url: Single URL string or list of URLs

        Returns:
            Tuple of (summary, method_used)

        Raises:
            ProcessingError: If Tier 1 fails (document requires paid tier)
        """
        # Handle multiple URLs
        if isinstance(url, list):
            return self._process_multiple_pdfs(url)

        # Tier 1: PyPDF2 text extraction + Gemini text API (free tier)
        try:
            text = self._tier1_extract_text(url)
            if text and self._is_good_text_quality(text):
                summary = self._summarize_with_gemini(text)
                logger.info(f"[Tier1] SUCCESS - {url}")
                return summary, "tier1_pypdf2_gemini"
            else:
                if not text:
                    logger.warning(f"[Tier1] FAILED - No text extracted - {url}")
                else:
                    logger.warning(f"[Tier1] FAILED - Poor text quality ({len(text)} chars) - {url}")

        except Exception as e:
            logger.warning(f"[Tier1] FAILED - {type(e).__name__}: {str(e)} - {url}")

        # Free tier: fail fast (no expensive fallbacks)
        # TODO: When you have paid customers, check subscription tier here
        # and enable Tier 2/3 from backend/archived/premium_processing_tiers.py
        logger.error(f"[Tier1] REJECTED - Requires premium tier - {url}")
        raise ProcessingError(
            "Document requires premium tier for processing. "
            "This PDF may be scanned or have complex formatting that requires OCR."
        )
    
    def _tier1_extract_text(self, url: str) -> Optional[str]:
        """Tier 1: Extract text using PyPDF2"""
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
    
    # Tier 2 (Mistral OCR) and Tier 3 (Gemini PDF API) archived
    # See: backend/archived/premium_processing_tiers.py for re-enablement

    def _summarize_with_gemini(self, text: str) -> str:
        """Summarize extracted text using Gemini
        
        Args:
            text: Extracted text to summarize
            
        Returns:
            Summary text
        """
        # Determine which model to use based on text size
        text_size = len(text)
        page_count = self._estimate_page_count(text)
        
        if text_size < FLASH_LITE_MAX_CHARS and page_count <= FLASH_LITE_MAX_PAGES:
            model_name = self.flash_lite_model_name
            model_display = "flash-lite"
        else:
            model_name = self.flash_model_name
            model_display = "flash"
        
        logger.info(f"Summarizing {page_count} pages ({text_size} chars) using Gemini {model_display}")
        
        # Get appropriate prompt based on document size
        if page_count <= 30:
            prompt = self._get_short_agenda_prompt(text)
        else:
            prompt = self._get_comprehensive_prompt() + f"\n\nAgenda text:\n{text}"
        
        try:
            # Confidence: 9/10 - Gemini's large context handles everything in one pass
            # Adaptive thinking based on document complexity
            if page_count <= 10 and text_size <= 30000:
                # Easy task: Simple agendas, disable thinking for speed
                logger.info(f"Simple document ({page_count} pages) - disabling thinking for speed")
                config = types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                    thinking_config=types.ThinkingConfig(thinking_budget=0)  # No thinking needed
                )
            elif page_count <= 50 and text_size <= 150000:
                # Medium task: Standard agendas, use moderate thinking
                logger.info(f"Medium document ({page_count} pages) - using moderate thinking")
                if model_name == self.flash_lite_model_name:
                    # Flash-Lite needs explicit budget since it doesn't think by default
                    config = types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=8192,
                        thinking_config=types.ThinkingConfig(thinking_budget=2048)  # Moderate thinking
                    )
                else:
                    # Flash uses dynamic thinking by default
                    config = types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=8192,
                        # Let model decide thinking budget dynamically
                    )
            else:
                # Hard task: Complex documents, use dynamic thinking for best quality
                logger.info(f"Complex document ({page_count} pages) - using dynamic thinking")
                config = types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                    thinking_config=types.ThinkingConfig(thinking_budget=-1)  # Dynamic thinking
                )
            
            response = self.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )

            if response.text is None:
                raise ValueError("Gemini returned no text in response")
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini summarization failed: {e}")
            raise
    
    def _get_short_agenda_prompt(self, text: str) -> str:
        """Get prompt for short agendas"""
        return f"""This is a city council meeting agenda. Provide a clear, concise summary that covers:

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
    
    def _get_comprehensive_prompt(self) -> str:
        """Get prompt for comprehensive agenda analysis"""
        return """Analyze this city council meeting agenda and provide a comprehensive summary for residents.

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
Skip pure administrative items unless they have significant public impact."""
    
    def _process_multiple_pdfs(self, urls: List[str]) -> tuple[str, str]:
        """Process multiple PDFs by extracting all text first, then summarizing with full context

        Strategy: Most multi-PDF cases are main agenda + supplemental materials.
        The model should reason over the complete context to produce a coherent summary,
        rather than separate summaries concatenated together.
        """
        logger.info(f"Processing {len(urls)} PDFs with combined context")

        # Extract text from all PDFs
        all_text_parts = []
        failed_pdfs = []

        for i, url in enumerate(urls, 1):
            logger.info(f"Extracting text from PDF {i}/{len(urls)}: {url}")
            try:
                text = self._tier1_extract_text(url)
                if text and self._is_good_text_quality(text):
                    # Label each document for model context
                    doc_label = "MAIN AGENDA" if i == 1 else f"SUPPLEMENTAL MATERIAL {i-1}"
                    all_text_parts.append(f"=== {doc_label} ===\n{text}")
                    logger.info(f"[Tier1] Extracted {len(text)} chars from document {i}")
                else:
                    logger.warning(f"[Tier1] Poor quality or no text from PDF {i}")
                    failed_pdfs.append(i)
            except Exception as e:
                logger.error(f"[Tier1] Failed to extract from PDF {i}: {type(e).__name__}: {str(e)}")
                failed_pdfs.append(i)

        # If we got no usable text from any PDF, fail fast
        if not all_text_parts:
            logger.error(f"[Tier1] REJECTED - No usable text from any of {len(urls)} PDFs")
            raise ProcessingError(
                f"All {len(urls)} documents require premium tier for processing. "
                "These PDFs may be scanned or have complex formatting that requires OCR."
            )

        # Combine all text and summarize with full context
        combined_text = "\n\n".join(all_text_parts)
        logger.info(f"[Tier1] Combined {len(all_text_parts)}/{len(urls)} documents ({len(combined_text)} chars total)")

        # Summarize with full context (model sees all documents at once)
        summary = self._summarize_with_gemini(combined_text)

        # Note partial failures in the summary if any PDFs couldn't be processed
        if failed_pdfs:
            failure_note = f"\n\n[Note: {len(failed_pdfs)} of {len(urls)} documents could not be processed]"
            summary += failure_note
            logger.warning(f"Partial success: {len(all_text_parts)}/{len(urls)} documents processed")

        return summary, f"multiple_pdfs_{len(urls)}_combined"
    
    def _download_pdf(self, url: str) -> Optional[bytes]:
        """Download PDF with validation and size limits"""
        try:
            # Handle Google Docs viewer URLs
            if 'docs.google.com/gview' in url:
                from urllib.parse import parse_qs, unquote
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if 'url' in params:
                    url = unquote(params['url'][0])
                    logger.debug(f"Extracted actual PDF URL from Google Docs viewer: {url}")
            
            response = requests.get(
                url,
                timeout=30,
                stream=True,
                headers={"User-Agent": "Engagic-Gemini-Processor/1.0"}
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
            logger.debug(f"Quality check FAILED: Text too short ({len(text) if text else 0} chars, need >= 100)")
            return False

        # Check character distribution
        letters = sum(1 for c in text if c.isalpha())
        total_chars = len(text)

        if total_chars == 0:
            logger.debug("Quality check FAILED: Zero characters")
            return False

        letter_ratio = letters / total_chars
        if letter_ratio < 0.3:
            logger.warning(f"Quality check FAILED: Letter ratio too low ({letter_ratio:.2%}, need >= 30%)")
            logger.warning(f"  Extracted {letters} letters out of {total_chars} total chars")
            logger.warning("  First 300 chars of extracted text:")
            logger.warning(f"  {repr(text[:300])}")
            return False

        # Check for actual words
        words = text.split()
        if len(words) < 20:
            logger.warning(f"Quality check FAILED: Too few words ({len(words)}, need >= 20)")
            logger.warning(f"  Extracted text: {repr(text[:200])}")
            return False

        # Check for recognizable English words
        sample_words = words[:100]
        recognizable = sum(1 for word in sample_words if word.lower().strip('.,!?();:') in self.english_words)

        if len(sample_words) >= 50 and recognizable < 5:
            logger.warning(f"Quality check FAILED: Too few recognizable words ({recognizable}/{len(sample_words)})")
            logger.warning(f"  First 20 words: {sample_words[:20]}")
            return False

        # Check for excessive single-character "words" (sign of bad extraction)
        single_chars = sum(1 for word in sample_words if len(word) == 1)
        if len(sample_words) >= 50 and single_chars > 20:
            logger.warning(f"Quality check FAILED: Too many single-char words ({single_chars}/{len(sample_words)})")
            logger.warning(f"  First 30 words: {sample_words[:30]}")
            return False

        logger.debug(f"Quality check PASSED: {total_chars} chars, {len(words)} words, {letter_ratio:.2%} letters, {recognizable}/{len(sample_words)} recognizable")
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
    
    def _update_cache_hit_count(self, packet_url: str):
        """Update cache hit count in processing_cache table"""
        try:
            conn = self.db.conn
            if conn:
                cursor = conn.cursor()
                
                # Serialize packet_url if it's a list
                lookup_url = packet_url
                if isinstance(packet_url, list):
                    lookup_url = json.dumps(packet_url)
                
                cursor.execute("""
                    UPDATE processing_cache 
                    SET cache_hit_count = cache_hit_count + 1,
                        last_accessed = CURRENT_TIMESTAMP
                    WHERE packet_url = ?
                """, (lookup_url,))
                
                conn.commit()
        except Exception as e:
            logger.debug(f"Could not update cache hit count: {e}")
    
    def _store_in_processing_cache(self, packet_url: str, summary: str, processing_time: float):
        """Store processing results in processing_cache table"""
        try:
            conn = self.db.conn
            if conn:
                cursor = conn.cursor()
                
                # Serialize packet_url if it's a list
                lookup_url = packet_url
                if isinstance(packet_url, list):
                    lookup_url = json.dumps(packet_url)
                
                # Generate content hash
                content_hash = hashlib.md5(summary.encode()).hexdigest() if summary else None
                
                cursor.execute("""
                    INSERT OR REPLACE INTO processing_cache
                    (packet_url, content_hash, processing_method,
                     processing_time, cache_hit_count, created_at)
                    VALUES (?, ?, 'tier1_pypdf2_gemini', ?, 0, CURRENT_TIMESTAMP)
                """, (
                    lookup_url,
                    content_hash,
                    processing_time
                ))
                
                conn.commit()
                logger.debug(f"Stored in processing_cache: {packet_url}")
        except Exception as e:
            logger.error(f"Failed to store in processing_cache: {e}")
    
    def process_batch_agendas(
        self, 
        batch_requests: List[Dict[str, str]], 
        wait_for_results: bool = True,
        return_raw: bool = False
    ) -> List[Dict[str, Any]]:
        """Process multiple agendas using Gemini's Batch API for 50% cost savings
        
        Args:
            batch_requests: List of {"url": packet_url, "custom_id": custom_id}
            wait_for_results: Whether to wait for batch completion (default True)
            return_raw: Whether to return raw batch results (default False)
            
        Returns:
            List of processing results matching the input custom_ids
        """
        if not batch_requests:
            return []
            
        logger.info(f"Processing {len(batch_requests)} agendas using Gemini Batch API (50% cost savings)")
        
        try:
            # Prepare inline requests for Gemini batch
            inline_requests = []
            request_map = {}  # Map custom_id to original request
            
            for req in batch_requests:
                try:
                    # Handle both single URLs and lists of URLs
                    urls = req["url"] if isinstance(req["url"], list) else [req["url"]]
                    
                    # Extract text from all URLs
                    all_texts = []
                    for url in urls:
                        text = self._tier1_extract_text(url)
                        if text and self._is_good_text_quality(text):
                            all_texts.append(text)
                    
                    if not all_texts:
                        logger.warning(f"Skipping {req['custom_id']} - failed text extraction from all URLs")
                        continue
                    
                    # Combine all texts
                    text = "\n\n--- NEXT DOCUMENT ---\n\n".join(all_texts)
                    
                    # Get appropriate prompt based on document size
                    page_count = self._estimate_page_count(text)
                    if page_count <= 30:
                        prompt = self._get_short_agenda_prompt(text)
                    else:
                        prompt = self._get_comprehensive_prompt() + f"\n\nAgenda text:\n{text}"
                    
                    # Create inline request for Gemini batch
                    inline_requests.append({
                        'contents': [{
                            'parts': [{'text': prompt}],
                            'role': 'user'
                        }],
                        'generation_config': {
                            'temperature': 0.3,
                            'max_output_tokens': 8192
                        }
                    })
                    
                    # Store mapping for result processing
                    request_map[len(inline_requests) - 1] = req
                    
                except Exception as e:
                    logger.error(f"Error preparing batch request for {req['custom_id']}: {e}")
                    continue
            
            if not inline_requests:
                logger.warning("No valid batch requests to process")
                return []
            
            # Submit to Gemini Batch API
            # Confidence: 9/10 - Using inline requests for smaller batches
            batch_job = self.client.batches.create(
                model=self.flash_model_name,  # Use Flash for batch processing
                src=inline_requests,
                config={
                    'display_name': f"agenda-batch-{time.time()}"
                }
            )

            batch_name = batch_job.name
            if not batch_name:
                raise ValueError("Batch job created but no name returned")
            logger.info(f"Submitted batch {batch_name} with {len(inline_requests)} requests")
            
            if not wait_for_results:
                return [{"batch_id": batch_name, "status": "submitted"}]
            
            # Poll for completion
            max_wait_time = 3600  # 1 hour max wait
            poll_interval = 30    # Check every 30 seconds
            waited_time = 0
            
            completed_states = {
                'JOB_STATE_SUCCEEDED',
                'JOB_STATE_FAILED', 
                'JOB_STATE_CANCELLED',
                'JOB_STATE_EXPIRED'
            }
            
            while waited_time < max_wait_time:
                batch_job = self.client.batches.get(name=batch_name)

                if batch_job.state and batch_job.state.name in completed_states:
                    logger.info(f"Batch {batch_name} completed with state: {batch_job.state.name}")
                    break

                state_name = batch_job.state.name if batch_job.state else "unknown"
                logger.info(f"Batch {batch_name} still processing... ({waited_time}s waited, state: {state_name})")
                time.sleep(poll_interval)
                waited_time += poll_interval

            if waited_time >= max_wait_time:
                logger.error(f"Batch {batch_name} timed out after {max_wait_time}s")
                return []

            if not batch_job.state or batch_job.state.name != 'JOB_STATE_SUCCEEDED':
                state_name = batch_job.state.name if batch_job.state else "unknown"
                logger.error(f"Batch {batch_name} failed with state: {state_name}")
                if batch_job.error:
                    logger.error(f"Error details: {batch_job.error}")
                return []
            
            # Process results
            results = []
            
            if batch_job.dest and batch_job.dest.inlined_responses:
                for i, inline_response in enumerate(batch_job.dest.inlined_responses):
                    if i not in request_map:
                        logger.warning(f"No mapping found for response index {i}")
                        continue
                    
                    original_req = request_map[i]
                    
                    if inline_response.response:
                        try:
                            # Extract summary text from response
                            summary = inline_response.response.text
                            
                            # Create result object matching expected format
                            result = BatchResult(
                                custom_id=original_req["custom_id"],
                                result_type=ResultType.SUCCEEDED,
                                message=BatchMessage(content=[{'text': summary or ""}]),
                                error=None
                            )
                            
                            results.append(result)
                            logger.info(f"Successfully processed {original_req['custom_id']}")
                            
                        except Exception as e:
                            logger.error(f"Error extracting response for {original_req['custom_id']}: {e}")
                            
                            result = BatchResult(
                                custom_id=original_req["custom_id"],
                                result_type=ResultType.FAILED,
                                message=None,
                                error=str(e)
                            )
                            
                            results.append(result)
                    
                    elif inline_response.error:
                        logger.error(f"Batch item {original_req['custom_id']} failed: {inline_response.error}")
                        
                        result = BatchResult(
                            custom_id=original_req["custom_id"],
                            result_type=ResultType.FAILED,
                            message=None,
                            error=str(inline_response.error)
                        )
                        
                        results.append(result)
            
            successful_count = sum(1 for r in results if r.result_type == ResultType.SUCCEEDED)
            logger.info(f"Batch processing complete: {successful_count}/{len(results)} successful")
            
            return results
            
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            
            # Fallback to individual processing
            logger.info("Falling back to individual processing")
            results = []
            for req in batch_requests:
                try:
                    summary, method = self.process_agenda_optimal(req["url"])
                    
                    result = BatchResult(
                        custom_id=req["custom_id"],
                        result_type=ResultType.SUCCEEDED,
                        message=BatchMessage(content=[{'text': summary}]),
                        error=None
                    )
                    
                    results.append(result)
                    
                except Exception as e:
                    logger.error(f"Individual processing failed for {req['custom_id']}: {e}")
                    
                    result = BatchResult(
                        custom_id=req["custom_id"],
                        result_type=ResultType.FAILED,
                        message=None,
                        error=str(e)
                    )
                    
                    results.append(result)
            
            return results


def create_processor(**kwargs) -> AgendaProcessor:
    """Create a processor instance"""
    return AgendaProcessor(**kwargs)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python gemini_processor.py <pdf_url>")
        sys.exit(1)
    
    processor = create_processor()
    
    test_url = sys.argv[1]
    summary, method = processor.process_agenda_optimal(test_url)
    
    print("=== SUMMARY ===")
    print(summary)
    print("\n=== PROCESSING INFO ===")
    print(f"Method: {method}")