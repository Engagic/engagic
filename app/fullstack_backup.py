import requests
import tempfile
import os
import re
import time
import logging
import pytesseract
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
import anthropic
import argparse
import sys
from typing import List, Dict, Any
from databases import DatabaseManager
from config import config
from urllib.parse import urlparse, quote
import ipaddress
import socket

logger = logging.getLogger("engagic")

# Security constants
MAX_PDF_SIZE = 200 * 1024 * 1024  # 200MB max PDF size
MAX_PAGES = 1000  # Maximum pages to process
MAX_OCR_PAGES = 200  # Maximum pages to OCR (OCR is slow and resource intensive)
MAX_URL_LENGTH = 2000  # Maximum URL length
ALLOWED_SCHEMES = ['http', 'https']
BLOCKED_NETWORKS = [
    ipaddress.ip_network('127.0.0.0/8'),  # Localhost
    ipaddress.ip_network('10.0.0.0/8'),   # Private network
    ipaddress.ip_network('172.16.0.0/12'), # Private network
    ipaddress.ip_network('192.168.0.0/16'), # Private network
    ipaddress.ip_network('169.254.0.0/16'), # Link-local
    ipaddress.ip_network('::1/128'),        # IPv6 localhost
    ipaddress.ip_network('fc00::/7'),       # IPv6 private
    ipaddress.ip_network('fe80::/10'),      # IPv6 link-local
]

def validate_url(url: str) -> None:
    """Validate URL for security issues including SSRF protection"""
    # Check URL length
    if len(url) > MAX_URL_LENGTH:
        raise ValueError(f"URL exceeds maximum length of {MAX_URL_LENGTH} characters")
    
    # Parse and validate URL structure
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Invalid URL format")
    
    # Check scheme
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"URL scheme must be one of: {', '.join(ALLOWED_SCHEMES)}")
    
    # Check for empty hostname
    if not parsed.hostname:
        raise ValueError("URL must include a hostname")
    
    # Prevent file:// and other dangerous schemes
    if parsed.scheme == 'file':
        raise ValueError("File URLs are not allowed")
    
    # Resolve hostname to prevent DNS rebinding attacks
    try:
        # Get IP address
        ip_str = socket.gethostbyname(parsed.hostname)
        ip_addr = ipaddress.ip_address(ip_str)
        
        # Check against blocked networks (SSRF protection)
        for network in BLOCKED_NETWORKS:
            if ip_addr in network:
                raise ValueError(f"URL points to blocked network: {network}")
                
    except socket.gaierror:
        raise ValueError(f"Unable to resolve hostname: {parsed.hostname}")
    except Exception as e:
        raise ValueError(f"URL validation failed: {str(e)}")

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent directory traversal"""
    # Remove any path components
    basename = os.path.basename(filename)
    # Remove potentially dangerous characters
    safe_name = re.sub(r'[^\w\s\-\.]', '', basename)
    # Ensure it doesn't start with a dot (hidden file)
    if safe_name.startswith('.'):
        safe_name = safe_name[1:]
    # Add timestamp to prevent collisions
    timestamp = str(int(time.time()))
    name, ext = os.path.splitext(safe_name)
    return f"{name}_{timestamp}{ext}" if safe_name else f"file_{timestamp}.pdf"

class AgendaProcessor:
    def __init__(self, api_key=None, db_path="/root/engagic/app/meetings.db"):
        """Initialize processor with optional API key and database"""
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        if not self.api_key:
            raise ValueError("LLM_API_KEY environment variable required")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.english_words = self._load_english_words()
        self.db = DatabaseManager(
            locations_db_path=config.LOCATIONS_DB_PATH,
            meetings_db_path=config.MEETINGS_DB_PATH,
            analytics_db_path=config.ANALYTICS_DB_PATH
        )

    def _load_english_words(self):
        """Load English word set with comprehensive fallback for civic terms"""
        try:
            from nltk.corpus import words

            return set(word.lower() for word in words.words())
        except:
            # Comprehensive civic/municipal terms
            return set(
                [
                    "the",
                    "and",
                    "or",
                    "but",
                    "in",
                    "on",
                    "at",
                    "to",
                    "for",
                    "of",
                    "with",
                    "by",
                    "council",
                    "city",
                    "meeting",
                    "agenda",
                    "item",
                    "public",
                    "comment",
                    "session",
                    "board",
                    "commission",
                    "appointment",
                    "ordinance",
                    "resolution",
                    "budget",
                    "planning",
                    "zoning",
                    "development",
                    "traffic",
                    "safety",
                    "park",
                    "library",
                    "police",
                    "fire",
                    "emergency",
                    "infrastructure",
                    "project",
                    "contract",
                    "approval",
                    "review",
                    "hearing",
                    "closed",
                    "property",
                    "agreement",
                    "staff",
                    "street",
                    "avenue",
                    "boulevard",
                    "road",
                    "drive",
                    "lane",
                    "court",
                    "place",
                    "north",
                    "south",
                    "east",
                    "west",
                    "permit",
                    "variance",
                    "conditional",
                    "use",
                    "environmental",
                    "impact",
                    "report",
                    "ceqa",
                    "downtown",
                    "residential",
                    "commercial",
                    "industrial",
                    "mixed",
                    "density",
                    "housing",
                    "affordable",
                    "transportation",
                    "transit",
                    "parking",
                    "bicycle",
                    "pedestrian",
                    "crosswalk",
                ]
            )

    def download_and_extract_text(self, url) -> str:
        """Download PDF(s) and extract text using smart extraction strategy
        
        Args:
            url: Either a string URL or a list of URLs
        """
        # Handle list of URLs
        if isinstance(url, list):
            logger.info(f"Processing {len(url)} PDFs")
            all_texts = []
            for i, pdf_url in enumerate(url, 1):
                try:
                    logger.info(f"Processing PDF {i}/{len(url)}: {pdf_url[:80]}...")
                    text = self._download_and_extract_single(pdf_url)
                    all_texts.append(f"--- DOCUMENT {i} ---\n{text}")
                except Exception as e:
                    logger.error(f"Failed to process PDF {i}: {e}")
                    continue
            
            if not all_texts:
                raise Exception("No documents could be processed")
            
            # Combine all texts with clear separators
            return "\n\n".join(all_texts)
        else:
            # Single URL
            return self._download_and_extract_single(url)
    
    def _download_and_extract_single(self, url: str) -> str:
        """Download a single PDF and extract text"""
        # Validate URL for security
        validate_url(url)
        
        logger.info(f"Downloading and processing PDF from: {url[:80]}...")  # Log truncated URL

        # Store original tempdir setting
        original_tempdir = tempfile.tempdir
        original_tmpdir = os.environ.get('TMPDIR')
        original_temp = os.environ.get('TEMP')
        original_tmp = os.environ.get('TMP')

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Force all temp files (requests, PIL, Tesseract, etc.) into our temp_dir
                tempfile.tempdir = temp_dir
                os.environ['TMPDIR'] = temp_dir
                os.environ['TEMP'] = temp_dir
                os.environ['TMP'] = temp_dir
                
                logger.debug(f"Redirecting all temp files into: {temp_dir}")
                
                # Download PDF with size limit via streaming
                try:
                    response = requests.get(url, timeout=30, stream=True, headers={
                        'User-Agent': 'Engagic-Agenda-Processor/1.0'
                    })
                    response.raise_for_status()
                    
                    # Check content length if provided
                    content_length = response.headers.get('content-length')
                    if content_length and int(content_length) > MAX_PDF_SIZE:
                        raise ValueError(f"PDF size {content_length} exceeds maximum allowed size of {MAX_PDF_SIZE} bytes")
                    
                    # Download with size checking
                    pdf_content = b''
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            downloaded += len(chunk)
                            if downloaded > MAX_PDF_SIZE:
                                raise ValueError(f"PDF size exceeds maximum allowed size of {MAX_PDF_SIZE} bytes")
                            pdf_content += chunk
                            
                except requests.RequestException as e:
                    raise Exception(f"Failed to download PDF: {e}")

                pdf_path = os.path.join(temp_dir, sanitize_filename("agenda.pdf"))
                with open(pdf_path, "wb") as f:
                    f.write(pdf_content)

                # Smart text extraction
                raw_text = self._extract_text_smart(pdf_path)

                # Normalize the formatting
                return self._normalize_text_formatting(raw_text)
                
            finally:
                # Always restore original tempdir settings
                tempfile.tempdir = original_tempdir
                if original_tmpdir:
                    os.environ['TMPDIR'] = original_tmpdir
                elif 'TMPDIR' in os.environ:
                    del os.environ['TMPDIR']
                    
                if original_temp:
                    os.environ['TEMP'] = original_temp
                elif 'TEMP' in os.environ:
                    del os.environ['TEMP']
                    
                if original_tmp:
                    os.environ['TMP'] = original_tmp
                elif 'TMP' in os.environ:
                    del os.environ['TMP']

    def _extract_text_smart(self, pdf_path: str) -> str:
        """Try PDFReader first, fall back to OCR for problematic pages"""
        logger.info("Attempting digital text extraction...")

        try:
            with open(pdf_path, "rb") as f:
                reader = PdfReader(f)
                total_pages = len(reader.pages)
                
                # Check page count limit
                if total_pages > MAX_PAGES:
                    raise ValueError(f"PDF has {total_pages} pages, exceeds maximum of {MAX_PAGES} pages")
                
                logger.info(f"Processing {total_pages} pages...")

                all_text = ""
                ocr_pages = []

                for page_num, page in enumerate(reader.pages, 1):
                    try:
                        page_text = page.extract_text()

                        # Check if extraction was successful
                        if self._is_good_digital_extraction(page_text):
                            all_text += f"\n--- PAGE {page_num} ---\n{page_text}\n"
                            if page_num % 10 == 0:
                                logger.info(
                                    f"Digital extraction: {page_num}/{total_pages} pages..."
                                )
                        else:
                            # Mark for OCR
                            ocr_pages.append(page_num)
                            all_text += f"\n--- PAGE {page_num} ---\n[NEEDS_OCR]\n"

                    except Exception as e:
                        logger.error(f"Error extracting page {page_num}: {e}")
                        ocr_pages.append(page_num)
                        all_text += f"\n--- PAGE {page_num} ---\n[NEEDS_OCR]\n"

                # OCR the problematic pages
                if ocr_pages:
                    logger.info(f"Running OCR on {len(ocr_pages)} pages...")
                    ocr_text = self._ocr_specific_pages(pdf_path, ocr_pages)

                    # Replace [NEEDS_OCR] markers with actual OCR text
                    for page_num in ocr_pages:
                        marker = f"--- PAGE {page_num} ---\n[NEEDS_OCR]"
                        if page_num in ocr_text:
                            replacement = (
                                f"--- PAGE {page_num} ---\n{ocr_text[page_num]}"
                            )
                            all_text = all_text.replace(marker, replacement)

                return all_text

        except Exception as e:
            logger.warning(f"Digital extraction failed: {e}")
            logger.info("Falling back to full OCR...")
            return self._full_ocr(pdf_path)

    def _normalize_text_formatting(self, raw_text: str) -> str:
        """Fix weird PDFReader formatting by reconstructing proper lines"""
        logger.info("Normalizing text formatting...")

        pages = raw_text.split("--- PAGE")
        normalized_pages = []

        for i, page in enumerate(pages):
            if i == 0 and not page.strip():
                continue

            # Extract page number and content - limit search to prevent ReDoS
            # Split on first newline to avoid DOTALL on entire content
            lines = page.split('\n', 1)
            if not lines:
                continue
            
            header_match = re.match(r"\s*(\d+)\s*---\s*", lines[0])
            if not header_match:
                continue
                
            page_num = header_match.group(1)
            page_content = lines[1] if len(lines) > 1 else ""

            # Normalize this page
            normalized_content = self._normalize_page_content(page_content)
            normalized_pages.append(f"--- PAGE {page_num} ---\n{normalized_content}\n")

        return "\n".join(normalized_pages)

    def _normalize_page_content(self, content: str) -> str:
        """Reconstruct proper paragraphs from weirdly formatted text"""
        lines = content.split("\n")

        # Group lines into logical blocks
        blocks = []
        current_block = []

        for line in lines:
            line = line.strip()

            if not line:
                # Empty line - end current block if it has content
                if current_block:
                    blocks.append(" ".join(current_block))
                    current_block = []
                continue

            # Check if this line should start a new block
            if self._should_start_new_block(line, current_block):
                if current_block:
                    blocks.append(" ".join(current_block))
                current_block = [line]
            else:
                # Add to current block
                current_block.append(line)

        # Don't forget the last block
        if current_block:
            blocks.append(" ".join(current_block))

        # Clean up each block
        cleaned_blocks = []
        for block in blocks:
            # Remove excessive spaces
            cleaned_block = re.sub(r"\s+", " ", block).strip()
            if cleaned_block:
                cleaned_blocks.append(cleaned_block)

        return "\n\n".join(cleaned_blocks)

    def _should_start_new_block(self, line: str, current_block: list) -> bool:
        """Determine if this line should start a new paragraph/block"""
        if not current_block:
            return True

        # Section headers (all caps, short)
        if line.isupper() and len(line) < 50:
            return True

        # Numbered items
        if re.match(r"^\d+[\.\)]\s", line):
            return True

        # Lettered items
        if re.match(r"^[A-Z][\.\)]\s", line):
            return True

        # Time patterns
        if re.match(r"^\d{1,2}:\d{2}\s*(AM|PM)", line, re.IGNORECASE):
            return True

        # URLs or email addresses
        if re.search(r"(https?://|@.*\.)", line):
            return True

        # Meeting info patterns
        if re.search(r"(Meeting ID|Phone:|Council Chambers)", line, re.IGNORECASE):
            return True

        return False

    def _is_good_digital_extraction(self, text: str) -> bool:
        """Check if digital extraction produced meaningful text"""
        text = text.strip()

        if len(text) < 50:
            return False

        # Check for reasonable character distribution
        letters = sum(1 for c in text if c.isalpha())
        total_chars = len(text)

        if total_chars == 0:
            return False

        letter_ratio = letters / total_chars
        if letter_ratio < 0.3:
            return False

        # Additional quality checks for fragmented text
        lines = text.split("\n")
        valid_lines = [line.strip() for line in lines if line.strip()]

        if not valid_lines:
            return False

        # Check for excessive single-word lines (sign of fragmented extraction)
        single_word_lines = sum(1 for line in valid_lines if len(line.split()) == 1)
        if len(valid_lines) > 10 and (single_word_lines / len(valid_lines)) > 0.5:
            logger.info(
                f"Digital extraction appears fragmented: {single_word_lines}/{len(valid_lines)} single-word lines"
            )
            return False

        # Check for reasonable sentence structure in first few lines
        sample_text = " ".join(valid_lines[:5])
        words = sample_text.split()
        if len(words) > 10:
            # Should have some longer words and reasonable punctuation
            long_words = sum(1 for word in words if len(word) > 3)
            if (long_words / len(words)) < 0.3:
                logger.info("Digital extraction lacks proper word structure")
                return False

        return True

    def _ocr_specific_pages(self, pdf_path: str, page_numbers: List[int]) -> dict:
        """OCR only specific pages"""
        ocr_results = {}
        
        # Get the temp directory from the pdf_path's parent (which is our controlled temp_dir)
        temp_dir = os.path.dirname(pdf_path)

        for page_num in page_numbers:
            try:
                # Check if PDF still exists
                if not os.path.exists(pdf_path):
                    logger.error(f"PDF file disappeared during processing: {pdf_path}")
                    ocr_results[page_num] = f"[ERROR: PDF file no longer exists]"
                    continue
                    
                pages = convert_from_path(
                    pdf_path, dpi=200, first_page=page_num, last_page=page_num,
                    output_folder=temp_dir
                )
                if pages and len(pages) > 0:
                    try:
                        ocr_text = pytesseract.image_to_string(pages[0])
                        ocr_results[page_num] = ocr_text
                    except Exception as ocr_error:
                        logger.warning(f"OCR failed for page {page_num}: {ocr_error}")
                        ocr_results[page_num] = f"[OCR_FAILED: Page {page_num} - possibly PowerPoint or image]"
                else:
                    logger.warning(f"No image generated for page {page_num}")
                    ocr_results[page_num] = f"[NO_IMAGE: Page {page_num}]"
            except Exception as e:
                logger.error(f"OCR failed for page {page_num}: {e}")
                ocr_results[page_num] = f"[OCR_ERROR: {str(e)}]"

        return ocr_results

    def _full_ocr(self, pdf_path: str) -> str:
        """Full OCR fallback for entire document"""
        logger.info("Running full OCR...")

        with open(pdf_path, "rb") as f:
            reader = PdfReader(f)
            total_pages = len(reader.pages)
            
            # Check page count limit
            if total_pages > MAX_PAGES:
                raise ValueError(f"PDF has {total_pages} pages, exceeds maximum of {MAX_PAGES} pages")
            
            # Warn if document is very large for OCR
            if total_pages > MAX_OCR_PAGES:
                logger.warning(f"PDF has {total_pages} pages, which exceeds OCR limit of {MAX_OCR_PAGES}. Only OCRing first {MAX_OCR_PAGES} pages.")
                pages_to_ocr = MAX_OCR_PAGES
            else:
                pages_to_ocr = total_pages

        all_text = ""
        
        # Get the temp directory from the pdf_path's parent (which is our controlled temp_dir)
        temp_dir = os.path.dirname(pdf_path)

        for page_num in range(1, pages_to_ocr + 1):
            try:
                # Check if PDF still exists
                if not os.path.exists(pdf_path):
                    logger.error(f"PDF file disappeared during processing: {pdf_path}")
                    all_text += f"\n--- PAGE {page_num} ---\n[ERROR: PDF file no longer exists]\n"
                    continue
                    
                pages = convert_from_path(
                    pdf_path, dpi=200, first_page=page_num, last_page=page_num,
                    output_folder=temp_dir
                )
                if pages and len(pages) > 0:
                    try:
                        ocr_text = pytesseract.image_to_string(pages[0])
                        all_text += f"\n--- PAGE {page_num} ---\n{ocr_text}\n"
                    except Exception as ocr_error:
                        logger.warning(f"OCR failed for page {page_num}: {ocr_error}")
                        all_text += f"\n--- PAGE {page_num} ---\n[OCR_FAILED: possibly PowerPoint or image content]\n"
                else:
                    logger.warning(f"No image generated for page {page_num}")
                    all_text += f"\n--- PAGE {page_num} ---\n[NO_IMAGE: conversion failed]\n"

                if page_num % 10 == 0:
                    logger.info(f"OCR progress: {page_num}/{total_pages} pages...")

            except Exception as e:
                logger.warning(f"OCR error on page {page_num}: {e}")
                all_text += f"\n--- PAGE {page_num} ---\n[OCR_ERROR: {str(e)}]\n"

        # Add note if we truncated
        if total_pages > MAX_OCR_PAGES:
            all_text += f"\n\n[NOTE: Document has {total_pages} pages total. Only OCR'd first {MAX_OCR_PAGES} pages due to size limits.]\n"

        return all_text

    def clean_text(self, raw_text: str, english_threshold: float = 0.7) -> str:
        """Clean text using simple English word percentage check"""
        logger.info(
            f"Cleaning text with {english_threshold * 100}% English word threshold..."
        )

        pages = raw_text.split("--- PAGE")
        cleaned_pages = []
        total_lines_kept = 0
        total_lines_processed = 0
        pages_kept = 0
        pages_skipped = 0

        for i, page in enumerate(pages):
            if i == 0 and not page.strip():
                continue

            # Extract page number and content - limit search to prevent ReDoS
            # Split on first newline to avoid DOTALL on entire content
            lines = page.split('\n', 1)
            if not lines:
                continue
            
            header_match = re.match(r"\s*(\d+)\s*---\s*", lines[0])
            if not header_match:
                continue
                
            page_num = header_match.group(1)
            page_content = lines[1] if len(lines) > 1 else ""

            # Process lines
            lines = page_content.split("\n")
            cleaned_lines = []

            for line in lines:
                total_lines_processed += 1
                line = line.strip()

                if not line:
                    continue

                # Check if line meets English word threshold
                if self._meets_english_threshold(line, english_threshold):
                    # Basic cleanup - remove weird characters but keep punctuation
                    cleaned_line = re.sub(r'[^\w\s\.,;:()"\'\-$%/]', " ", line)
                    cleaned_line = re.sub(r"\s+", " ", cleaned_line).strip()

                    if cleaned_line:
                        cleaned_lines.append(cleaned_line)
                        total_lines_kept += 1

            # Keep page if it has any valid content
            if cleaned_lines:
                cleaned_content = "\n".join(cleaned_lines)
                cleaned_pages.append(f"--- PAGE {page_num} ---\n{cleaned_content}\n")
                pages_kept += 1
            else:
                pages_skipped += 1

        result = "\n".join(cleaned_pages)
        logger.info(
            f"Cleaning complete: {total_lines_kept}/{total_lines_processed} lines kept"
        )
        logger.info(f"Pages: {pages_kept} kept, {pages_skipped} skipped")

        return result

    def _meets_english_threshold(self, line: str, threshold: float) -> bool:
        """Check if line meets the English word percentage threshold"""
        # Extract words (2+ letters)
        words = re.findall(r"\b[a-zA-Z]{2,}\b", line.lower())

        if len(words) == 0:
            # No words found - keep very short lines, skip long ones
            return len(line.strip()) < 20

        # Count valid English words
        valid_words = sum(1 for word in words if word in self.english_words)

        # Calculate percentage
        percentage = valid_words / len(words)

        return percentage >= threshold

    def _chunk_by_agenda_items(
        self, text: str, max_chunk_size: int = 75000
    ) -> List[str]:
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

    def _get_page_count(self, text: str) -> int:
        """Count the number of pages in the text"""
        page_markers = re.findall(r"--- PAGE \d+ ---", text)
        return len(page_markers)

    def summarize(self, text: str, rate_limit_delay: int = 5) -> str:
        """Summarize text with improved prompting and short agenda handling"""
        page_count = self._get_page_count(text)
        logger.info(f"Document has {page_count} pages")

        # Use different approach for short documents
        if page_count <= 30:
            return self._summarize_short_agenda(text, rate_limit_delay)
        else:
            return self._summarize_long_agenda(text, rate_limit_delay)

    def _summarize_short_agenda(self, text: str, rate_limit_delay: int = 5) -> str:
        """Summarize short agendas (<=10 pages) with simplified prompt"""
        logger.info("Using short agenda summarization approach")
        
        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=3000,
                messages=[
                    {
                        "role": "user",
                        "content": f"""This is a short city council meeting agenda. Provide a clear, concise summary that covers:

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
                        {text}""",
                    }
                ],
            )

            return response.content[0].text  # type: ignore

        except Exception as e:
            logger.error(f"Error processing short agenda: {e}")
            return f"[ERROR: Could not process agenda - {str(e)}]"

    def _summarize_long_agenda(self, text: str, rate_limit_delay: int = 5) -> str:
        """Summarize long agendas (>10 pages) using chunking approach"""
        logger.info("Using long agenda summarization approach")
        
        chunks = self._chunk_by_agenda_items(text)
        logger.info(f"Split into {len(chunks)} chunks for processing")

        summaries = []

        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i + 1}/{len(chunks)}...")

            try:
                response = self.client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=4000,
                    messages=[
                        {
                            "role": "user",
                            "content": f"""Analyze this portion of a city council meeting agenda packet and extract the key information 
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
                        {chunk}""",
                        }
                    ],
                )

                summaries.append(
                    f"--- SECTION {i + 1} SUMMARY ---\n{response.content[0].text}\n"  # type: ignore
                )

                # Rate limiting
                if i < len(chunks) - 1:
                    logger.info(f"Waiting {rate_limit_delay} seconds...")
                    time.sleep(rate_limit_delay)

            except Exception as e:
                logger.error(f"Error processing chunk {i + 1}: {e}")
                summaries.append(
                    f"--- SECTION {i + 1} SUMMARY ---\n[ERROR: Could not process this section - {str(e)}]\n"
                )

        return "\n".join(summaries)

    def process_agenda_with_cache(self, meeting_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process agenda with database caching - main entry point for cached processing"""
        packet_url = meeting_data["packet_url"]

        # Check cache first
        cached_meeting = self.db.get_cached_summary(packet_url)
        if cached_meeting:
            logger.info(f"Cache hit for {packet_url}")
            return {
                "summary": cached_meeting["processed_summary"],
                "processing_time": cached_meeting["processing_time_seconds"],
                "cached": True,
                "meeting_data": cached_meeting,
            }

        # Cache miss - process the agenda
        logger.info(f"Cache miss for {packet_url} - processing...")
        start_time = time.time()

        try:
            # Get city info
            city_slug = meeting_data.get("city_slug")
            city_info = self.db.get_city_by_slug(city_slug) if city_slug else {}

            # Merge meeting data with city info
            full_meeting_data = {**meeting_data, **city_info}

            # Process the agenda - download_and_extract_text now handles both single URLs and lists
            summary = self.process_agenda(
                packet_url, save_raw=False, save_cleaned=False
            )
            processing_time = time.time() - start_time

            # Store in database
            vendor = meeting_data.get("vendor")
            meeting_id = self.db.store_meeting_summary(
                full_meeting_data, summary, processing_time
            )

            logger.info(
                f"Processed and cached agenda {packet_url} in {processing_time:.1f}s (ID: {meeting_id})"
            )

            return {
                "summary": summary,
                "processing_time": processing_time,
                "cached": False,
                "meeting_data": full_meeting_data,
                "meeting_id": meeting_id,
            }

        except Exception as e:
            logger.error(f"Error processing agenda {packet_url}: {e}")
            raise

    def process_agenda(
        self,
        url,  # Can be string or list
        english_threshold: float = 0.7,
        save_raw: bool = True,
        save_cleaned: bool = True,
    ) -> str:
        """Complete pipeline: download → clean → summarize"""
        try:
            # Extract text (handles both single URLs and lists)
            raw_text = self.download_and_extract_text(url)

            if save_raw:
                self._save_text(raw_text, "raw_agenda.txt")

            # Clean text with configurable threshold
            logger.info(f"Cleaning text for url: {url}")
            cleaned_text = self.clean_text(raw_text, english_threshold)

            if save_cleaned:
                self._save_text(cleaned_text, "cleaned_agenda.txt")

            # Summarize
            logger.info("Starting summarization...")
            summary = self.summarize(cleaned_text)

            if save_raw or save_cleaned:  # Only save if we're saving other files
                self._save_text(summary, "agenda_summary.txt")
                logger.info("Complete! Summary saved to agenda_summary.txt")

            return summary

        except Exception as e:
            logger.error(f"Error processing agenda: {e}")
            raise

    def _save_text(self, text: str, filename: str) -> None:
        """Save text to file with UTF-8 encoding"""
        # Sanitize filename to prevent directory traversal
        safe_filename = sanitize_filename(filename)
        with open(safe_filename, "w", encoding="utf-8") as f:
            f.write(text)
        logger.info(f"Saved to {safe_filename} ({len(text)} characters)")

    def download_packet(self, url: str, output_path: str = None) -> str:
        """Download PDF packet and save to file"""
        # Validate URL for security
        validate_url(url)

        if not output_path:
            output_path = "downloaded_packet.pdf"
        
        # Sanitize output path
        safe_output_path = sanitize_filename(output_path)

        logger.info(f"Downloading packet from: {url[:80]}...")

        try:
            # Download with streaming and size limit
            response = requests.get(url, timeout=30, stream=True, headers={
                'User-Agent': 'Engagic-Agenda-Processor/1.0'
            })
            response.raise_for_status()
            
            # Check content length
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > MAX_PDF_SIZE:
                raise ValueError(f"PDF size {content_length} exceeds maximum allowed size of {MAX_PDF_SIZE} bytes")
            
            # Download with size checking
            pdf_content = b''
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded > MAX_PDF_SIZE:
                        raise ValueError(f"PDF size exceeds maximum allowed size of {MAX_PDF_SIZE} bytes")
                    pdf_content += chunk
                    
        except requests.RequestException as e:
            raise Exception(f"Failed to download PDF: {e}")

        with open(safe_output_path, "wb") as f:
            f.write(pdf_content)

        logger.info(f"Packet saved to {safe_output_path} ({len(pdf_content)} bytes)")
        return safe_output_path
    

    def download_and_process(
        self, url: str, english_threshold: float = 0.7, save_files: bool = True
    ) -> Dict[str, str]:
        """Download packet and extract/clean text without summarizing"""
        raw_text = self.download_and_extract_text(url)
        cleaned_text = self.clean_text(raw_text, english_threshold)

        result = {"raw_text": raw_text, "cleaned_text": cleaned_text}

        if save_files:
            self._save_text(raw_text, "raw_extracted_text.txt")
            self._save_text(cleaned_text, "cleaned_extracted_text.txt")
            logger.info("Text extraction complete - files saved")

        return result

    def process_packet(
        self, file_path: str, english_threshold: float = 0.7, save_files: bool = True
    ) -> Dict[str, str]:
        """Process a local PDF file"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.lower().endswith(".pdf"):
            raise ValueError("File must be a PDF")

        logger.info(f"Processing local packet: {file_path}")

        raw_text = self._extract_text_smart(file_path)
        raw_text = self._normalize_text_formatting(raw_text)
        cleaned_text = self.clean_text(raw_text, english_threshold)

        result = {"raw_text": raw_text, "cleaned_text": cleaned_text}

        if save_files:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            self._save_text(raw_text, f"{base_name}_raw.txt")
            self._save_text(cleaned_text, f"{base_name}_cleaned.txt")
            logger.info("Text processing complete - files saved")

        return result

    def full_pipeline(
        self, url: str, english_threshold: float = 0.7, save_files: bool = True
    ) -> Dict[str, str]:
        """Complete pipeline: download → process → summarize"""
        logger.info("Starting full pipeline...")

        raw_text = self.download_and_extract_text(url)
        cleaned_text = self.clean_text(raw_text, english_threshold)
        summary = self.summarize(cleaned_text)

        result = {
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "summary": summary,
        }

        if save_files:
            self._save_text(raw_text, "pipeline_raw.txt")
            self._save_text(cleaned_text, "pipeline_cleaned.txt")
            self._save_text(summary, "pipeline_summary.txt")
            logger.info("Full pipeline complete - all files saved")

        return result


def create_cli_parser():
    """Create CLI argument parser"""
    parser = argparse.ArgumentParser(
        description="Engagic Agenda Processor - Process city council meeting packets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fullstack.py --download-packet https://example.com/packet.pdf
  python fullstack.py --download-process https://example.com/packet.pdf
  python fullstack.py --process-packet local_file.pdf
  python fullstack.py --full-pipeline https://example.com/packet.pdf
  python fullstack.py --full-pipeline https://example.com/packet.pdf --no-save --threshold 0.8
        """,
    )

    # Action flags (mutually exclusive)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--download-packet",
        metavar="URL",
        help="Download PDF packet from URL and save to file",
    )
    action_group.add_argument(
        "--download-process",
        metavar="URL",
        help="Download and process packet (extract/clean text) without summarizing",
    )
    action_group.add_argument(
        "--process-packet",
        metavar="FILE",
        help="Process a local PDF file (extract/clean text)",
    )
    action_group.add_argument(
        "--full-pipeline",
        metavar="URL",
        help="Complete pipeline: download → process → summarize",
    )

    # Optional parameters
    parser.add_argument(
        "--output",
        "-o",
        help="Output filename for downloaded packet (only with --download-packet)",
    )
    parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=0.7,
        help="English word threshold for text cleaning (0.0-1.0, default: 0.7)",
    )
    parser.add_argument(
        "--no-save", action="store_true", help="Do not save intermediate files"
    )
    parser.add_argument(
        "--api-key", help="Anthropic API key (or set ANTHROPIC_API_KEY env var)"
    )

    return parser


def main():
    """CLI main function"""
    parser = create_cli_parser()
    args = parser.parse_args()

    # Validate threshold
    if not 0.0 <= args.threshold <= 1.0:
        logger.error("Error: threshold must be between 0.0 and 1.0")
        sys.exit(1)

    try:
        # Initialize processor
        processor = AgendaProcessor(api_key=args.api_key)
        save_files = not args.no_save

        if args.download_packet:
            logger.info("=== DOWNLOADING PACKET ===")
            output_path = processor.download_packet(args.download_packet, args.output)
            logger.info(f"Success! Packet saved to: {output_path}")

        elif args.download_process:
            logger.info("=== DOWNLOADING AND PROCESSING ===")
            result = processor.download_and_process(
                args.download_process, args.threshold, save_files
            )
            logger.info(
                f"Success! Extracted {len(result['cleaned_text'])} characters of cleaned text"
            )

        elif args.process_packet:
            logger.info("=== PROCESSING LOCAL PACKET ===")
            result = processor.process_packet(
                args.process_packet, args.threshold, save_files
            )
            logger.info(
                f"Success! Extracted {len(result['cleaned_text'])} characters of cleaned text"
            )

        elif args.full_pipeline:
            logger.info("=== FULL PIPELINE ===")
            result = processor.full_pipeline(
                args.full_pipeline, args.threshold, save_files
            )
            logger.info(
                f"Success! Generated summary with {len(result['summary'])} characters"
            )
            logger.info("=" * 50)
            logger.info("SUMMARY PREVIEW:")
            logger.info("=" * 50)
            # Show first 500 characters of summary
            preview = result["summary"][:500]
            if len(result["summary"]) > 500:
                preview += "...\n[truncated - see full summary in saved file]"
            logger.info(preview)

    except KeyboardInterrupt:
        logger.warning("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()