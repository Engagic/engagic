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
        try:
            from pdf_api_processor import PDFAPIProcessor
            self.pdf_processor = PDFAPIProcessor(self.api_key)
            logger.info("Claude PDF API processor initialized")
        except ImportError:
            logger.warning("PDF API processor not available - Tier 3 disabled")
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
        logger.info("Attempting Tier 1: PyPDF2 text extraction + text API...")
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
        except Exception as e:
            logger.debug(f"Tier 1 failed: {e}")
        
        # Tier 2: Mistral OCR + regular text API (moderate cost)
        if self.mistral_client:
            logger.info("Attempting Tier 2: Mistral OCR + text API...")
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
            except Exception as e:
                logger.debug(f"Tier 2 failed: {e}")
        
        # Tier 3: Claude PDF API (most expensive, last resort)
        if self.pdf_processor:
            logger.info("Attempting Tier 3: Claude PDF API...")
            try:
                summary = self._tier3_claude_pdf_api(url)
                if summary:
                    cost = 15.0  # Rough estimate for PDF API
                    self.stats["tier3_success"] += 1
                    self.stats["tier3_cost"] += cost
                    self.stats["total_cost"] += cost
                    logger.info(f"Tier 3 successful - Claude PDF API (cost: ${cost:.3f})")
                    return summary, "tier3_claude_pdf_api", cost
            except Exception as e:
                logger.error(f"Tier 3 failed: {e}")
        
        # All tiers failed
        raise ProcessingError("All processing tiers failed - unable to process PDF")
    
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
            # Use the PDF API processor with a comprehensive prompt
            summary = self.pdf_processor.process(url, method="url")
            return summary
        except Exception as e:
            logger.error(f"Claude PDF API failed: {e}")
            return None
    
    def _summarize_with_text_api(self, text: str, style: str = "comprehensive") -> str:
        """Summarize extracted text using regular text API (not PDF API)
        
        Args:
            text: Extracted text to summarize
            style: Summary style (comprehensive, brief)
            
        Returns:
            Summary text
        """
        page_count = self._estimate_page_count(text)
        logger.info(f"Summarizing {page_count} pages of text using text API")
        
        if style == "comprehensive":
            prompt = """Analyze this city council meeting agenda and provide a comprehensive summary for residents.

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

Agenda text:
{text}"""
        else:
            prompt = """Provide a brief summary of this city council meeting agenda, focusing on the most important items that affect residents:

{text}"""
        
        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt.format(text=text)}]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Text API summarization failed: {e}")
            raise
    
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
    print("\n=== PROCESSING INFO ===")
    print(f"Method: {method}")
    print(f"Cost: ${cost:.3f}")
    print("\n=== STATS ===")
    stats = processor.get_processing_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")