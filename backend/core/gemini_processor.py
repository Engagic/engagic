"""
Gemini-based PDF Processing Stack for Engagic

Optimized for cost-efficiency and quality using Google's Gemini models.
Text-first approach with PDF fallback for maximum information extraction.

Key features:
- Smart model selection (Flash vs Flash-Lite based on document size)
- No chunking needed (1M+ token context window)
- Batch processing support for 50% cost savings
- Simple, clean implementation without cost tracking overhead
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

# PDF processing
from PyPDF2 import PdfReader

# Google Gemini
from google import genai
from google.genai import types

# Our modules
from backend.database import DatabaseManager
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


class GeminiProcessor:
    """Gemini-based PDF processor optimized for cost and quality"""
    
    def __init__(self, api_key: Optional[str] = None, mistral_api_key: Optional[str] = None):
        """Initialize the Gemini processor
        
        Args:
            api_key: Gemini API key (or uses environment variables)
            mistral_api_key: Mistral API key for OCR fallback (optional)
        """
        # Initialize Gemini client
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
        if not self.api_key:
            raise ValueError("API key required - set GEMINI_API_KEY or LLM_API_KEY environment variable")
        
        # Initialize Gemini client (will use GEMINI_API_KEY env var if api_key is None)
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = genai.Client()  # Uses GEMINI_API_KEY from environment
        
        # Model names for selection
        self.flash_model_name = 'gemini-2.5-flash'
        self.flash_lite_model_name = 'gemini-2.5-flash-lite'
        
        # Initialize database
        self.db = DatabaseManager(
            locations_db_path=config.LOCATIONS_DB_PATH,
            meetings_db_path=config.MEETINGS_DB_PATH,
            analytics_db_path=config.ANALYTICS_DB_PATH,
        )
        
        # Initialize Mistral OCR if available (for Tier 2 fallback)
        self.mistral_api_key = mistral_api_key or os.getenv("MISTRAL_API_KEY")
        self.mistral_client = None
        if self.mistral_api_key:
            try:
                from mistralai import Mistral
                self.mistral_client = Mistral(api_key=self.mistral_api_key)
                logger.info("Mistral OCR client initialized for fallback")
            except ImportError:
                logger.warning("Mistral SDK not available - OCR fallback disabled")
        
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
        
        # Check cache first
        cached_meeting = self.db.get_cached_summary(packet_url)
        if cached_meeting:
            logger.info(f"Cache hit for {packet_url}")
            
            # Update processing_cache hit count
            self._update_cache_hit_count(packet_url)
            
            return {
                "success": True,
                "summary": cached_meeting["processed_summary"],
                "processing_time": cached_meeting.get("processing_time_seconds", 0),
                "cached": True,
                "meeting_data": cached_meeting,
                "processing_method": cached_meeting.get("processing_method", "cached")
            }
        
        # Process with Gemini
        logger.info(f"Cache miss for {packet_url} - processing with Gemini...")
        start_time = time.time()
        
        try:
            # Process the agenda
            summary, method = self.process_agenda_optimal(packet_url)
            
            # Store in database
            processing_time = time.time() - start_time
            meeting_data["processed_summary"] = summary
            meeting_data["processing_time_seconds"] = processing_time
            meeting_data["processing_method"] = method
            
            meeting_id = self.db.store_meeting_summary(meeting_data, summary, processing_time)
            
            # Store in processing_cache
            self._store_in_processing_cache(packet_url, summary, processing_time)
            
            logger.info(f"Processed agenda {packet_url} in {processing_time:.1f}s using {method}")
            
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
            logger.error(f"Failed to process agenda: {e}")
            return {
                "success": False,
                "error": str(e),
                "processing_time": time.time() - start_time,
                "cached": False
            }
    
    def process_agenda_optimal(self, url: Union[str, List[str]]) -> tuple[str, str]:
        """Process agenda using optimal approach with Gemini
        
        Args:
            url: Single URL string or list of URLs
            
        Returns:
            Tuple of (summary, method_used)
        """
        # Handle multiple URLs
        if isinstance(url, list):
            return self._process_multiple_pdfs(url)
        
        # Tier 1: PyPDF2 text extraction + Gemini text API (preferred)
        logger.info(f"Attempting Tier 1: PyPDF2 text extraction + Gemini for {url[:80]}...")
        try:
            text = self._tier1_extract_text(url)
            if text and self._is_good_text_quality(text):
                summary = self._summarize_with_gemini(text)
                logger.info(f"Tier 1 successful - PyPDF2 + Gemini")
                return summary, "tier1_pypdf2_gemini"
            else:
                if not text:
                    logger.warning(f"Tier 1 failed: No text extracted from PDF {url[:80]}")
                else:
                    logger.warning(f"Tier 1 failed: Poor text quality - {len(text)} chars extracted")
        except Exception as e:
            logger.warning(f"Tier 1 failed for {url[:80]}: {type(e).__name__}: {str(e)}")
        
        # Tier 2: Mistral OCR + Gemini text API (if available)
        if self.mistral_client:
            logger.info(f"Attempting Tier 2: Mistral OCR + Gemini for {url[:80]}...")
            try:
                text = self._tier2_mistral_ocr(url)
                if text and self._is_good_text_quality(text):
                    summary = self._summarize_with_gemini(text)
                    logger.info(f"Tier 2 successful - Mistral OCR + Gemini")
                    return summary, "tier2_mistral_gemini"
                else:
                    logger.warning(f"Tier 2 failed: Poor OCR quality")
            except Exception as e:
                logger.warning(f"Tier 2 failed for {url[:80]}: {type(e).__name__}: {str(e)}")
        
        # Tier 3: Direct Gemini PDF API (fallback for complex PDFs)
        logger.info(f"Attempting Tier 3: Direct Gemini PDF API for {url[:80]}...")
        try:
            summary = self._tier3_gemini_pdf_api(url)
            if summary:
                logger.info(f"Tier 3 successful - Gemini PDF API")
                return summary, "tier3_gemini_pdf_api"
            else:
                logger.error(f"Tier 3 failed: No summary returned")
        except Exception as e:
            logger.error(f"Tier 3 failed for {url[:80]}: {type(e).__name__}: {str(e)}")
        
        # All tiers failed
        logger.error(f"All processing tiers failed for {url[:80]}")
        raise ProcessingError(f"All processing tiers failed for document")
    
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
    
    def _tier2_mistral_ocr(self, url: str) -> Optional[str]:
        """Tier 2: Use Mistral OCR API for text extraction"""
        if not self.mistral_client:
            return None
        
        try:
            # Download PDF first
            pdf_content = self._download_pdf(url)
            if not pdf_content:
                return None
            
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
            logger.info(f"Mistral OCR extracted {len(text)} characters")
            
            return self._normalize_text(text) if text else None
            
        except Exception as e:
            logger.error(f"Mistral OCR failed: {e}")
            return None
    
    def _tier3_gemini_pdf_api(self, url: str) -> Optional[str]:
        """Tier 3: Use Gemini's native PDF processing"""
        try:
            # Download PDF
            pdf_content = self._download_pdf(url)
            if not pdf_content:
                return None
            
            # Upload PDF to Gemini
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                tmp_file.write(pdf_content)
                tmp_path = tmp_file.name
            
            try:
                # Upload file to Gemini
                uploaded_file = self.client.files.upload(path=tmp_path)
                logger.info(f"Uploaded PDF to Gemini: {uploaded_file.name}")
                
                # Determine which model to use based on PDF size
                pdf_size = len(pdf_content)
                if pdf_size < 5 * 1024 * 1024:  # Under 5MB - use Flash-Lite
                    model_name = self.flash_lite_model_name
                    model_display = "flash-lite"
                else:
                    model_name = self.flash_model_name
                    model_display = "flash"
                
                # Generate summary directly from PDF
                prompt = self._get_comprehensive_prompt()
                
                # PDF API: Use moderate thinking since we're asking for complex analysis
                config = types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                    thinking_config=types.ThinkingConfig(thinking_budget=4096)  # Moderate thinking for analysis
                )
                
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=[uploaded_file, prompt],
                    config=config
                )
                
                logger.info(f"Gemini PDF API ({model_display}) generated summary")
                return response.text
                
            finally:
                # Clean up temp file
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                    
        except Exception as e:
            logger.error(f"Gemini PDF API failed: {e}")
            return None
    
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
        """Process multiple PDFs and combine summaries"""
        logger.info(f"Processing {len(urls)} PDFs")
        summaries = []
        
        for i, url in enumerate(urls, 1):
            logger.info(f"Processing PDF {i}/{len(urls)}: {url[:80]}...")
            try:
                summary, method = self.process_agenda_optimal(url)
                summaries.append(f"=== DOCUMENT {i} ===\n{summary}")
            except Exception as e:
                logger.error(f"Failed to process PDF {i}: {e}")
                summaries.append(f"=== DOCUMENT {i} ===\n[Error: Could not process]")
        
        combined_summary = "\n\n".join(summaries)
        return combined_summary, f"multiple_pdfs_{len(urls)}_docs"
    
    def _download_pdf(self, url: str) -> Optional[bytes]:
        """Download PDF with validation and size limits"""
        try:
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
    
    def _update_cache_hit_count(self, packet_url: str):
        """Update cache hit count in processing_cache table"""
        try:
            with self.db.meetings.get_connection() as conn:
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
            with self.db.meetings.get_connection() as conn:
                cursor = conn.cursor()
                
                # Serialize packet_url if it's a list
                lookup_url = packet_url
                if isinstance(packet_url, list):
                    lookup_url = json.dumps(packet_url)
                
                # Generate content hash
                content_hash = hashlib.md5(summary.encode()).hexdigest() if summary else None
                
                cursor.execute("""
                    INSERT OR REPLACE INTO processing_cache
                    (packet_url, content_hash, summary_size, 
                     processing_duration_seconds, cache_hit_count, created_at)
                    VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
                """, (
                    lookup_url,
                    content_hash,
                    len(summary) if summary else 0,
                    processing_time
                ))
                
                conn.commit()
                logger.debug(f"Stored in processing_cache: {packet_url}")
        except Exception as e:
            logger.error(f"Failed to store in processing_cache: {e}")
    
    def process_agenda(self, url: str, **kwargs) -> str:
        """Legacy compatibility method"""
        summary, method = self.process_agenda_optimal(url)
        return summary


def create_processor(**kwargs) -> GeminiProcessor:
    """Create a Gemini processor instance"""
    return GeminiProcessor(**kwargs)


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