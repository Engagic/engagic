import requests
import tempfile
import os
import re
import time
import logging
import pytesseract
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
from typing import List, Dict, Any, Union
from urllib.parse import urlparse
import ipaddress
import socket
import shutil
import psutil
import resource
import gc
from PIL import Image
from contextlib import contextmanager

logger = logging.getLogger("engagic")

# Security constants
MAX_PDF_SIZE = 200 * 1024 * 1024  # 200MB max PDF size
MAX_PAGES = 1000  # Maximum pages to process
MAX_OCR_PAGES = 200  # Maximum pages to OCR (OCR is slow and resource intensive)
OCR_BATCH_SIZE = 10  # Process pages in batches to manage memory
MAX_MEMORY_MB = 1500  # Maximum memory usage in MB
MAX_DISK_PERCENT = 85  # Maximum disk usage percentage
MAX_IMAGE_PIXELS = 50_000_000  # 50MP limit for PIL

# Set PIL decompression bomb limit
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
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


class ResourceGuard:
    """Monitor and limit resource usage during OCR processing"""
    
    def __init__(self, max_memory_mb=MAX_MEMORY_MB, max_disk_percent=MAX_DISK_PERCENT):
        self.max_memory_mb = max_memory_mb
        self.max_disk_percent = max_disk_percent
        self.initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
    
    def check_resources(self):
        """Check if resources are within safe limits"""
        # Memory check
        mem = psutil.virtual_memory()
        process_mem = psutil.Process().memory_info().rss / 1024 / 1024
        
        if mem.percent > 80:
            raise RuntimeError(f"System memory usage critical: {mem.percent:.1f}%")
        
        if process_mem > self.max_memory_mb:
            raise RuntimeError(f"Process memory usage too high: {process_mem:.1f}MB > {self.max_memory_mb}MB")
        
        # Disk check
        disk = psutil.disk_usage('/')
        if disk.percent > self.max_disk_percent:
            raise RuntimeError(f"Disk usage critical: {disk.percent:.1f}%")
        
        # Temp disk check
        try:
            tmp_disk = psutil.disk_usage('/tmp')
            if tmp_disk.percent > 90:
                logger.warning(f"/tmp usage high: {tmp_disk.percent:.1f}%")
        except:
            pass
    
    def set_limits(self):
        """Set process resource limits"""
        try:
            # Limit process memory
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            resource.setrlimit(resource.RLIMIT_AS, 
                              (self.max_memory_mb * 1024 * 1024, hard))
        except Exception as e:
            logger.warning(f"Could not set memory limit: {e}")


@contextmanager
def safe_temp_directory():
    """Create and clean up temporary directory safely"""
    tmpdir = tempfile.mkdtemp()
    try:
        yield tmpdir
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Failed to clean up temp directory {tmpdir}: {e}")


class PDFOCRExtractor:
    """Extract text from PDFs using OCR and digital extraction"""
    
    def __init__(self, english_words=None):
        self.english_words = english_words or self._load_english_words()
        self.resource_guard = ResourceGuard()
    
    def _load_english_words(self):
        """Load English word set with comprehensive fallback for civic terms"""
        try:
            from nltk.corpus import words
            return set(word.lower() for word in words.words())
        except:
            # Comprehensive civic/municipal terms
            return set([
                "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by",
                "council", "city", "meeting", "agenda", "item", "public", "comment", "session",
                "board", "commission", "appointment", "ordinance", "resolution", "budget",
                "planning", "zoning", "development", "traffic", "safety", "park", "library",
                "police", "fire", "emergency", "infrastructure", "project", "contract",
                "approval", "review", "hearing", "closed", "property", "agreement", "staff",
                "street", "avenue", "boulevard", "road", "drive", "lane", "court", "place",
                "north", "south", "east", "west", "permit", "variance", "conditional", "use",
                "environmental", "impact", "report", "ceqa", "downtown", "residential",
                "commercial", "industrial", "mixed", "density", "housing", "affordable",
                "transportation", "transit", "parking", "bicycle", "pedestrian", "crosswalk"
            ])
    
    def download_and_extract_text(self, url: Union[str, List[str]]) -> str:
        """Download PDF(s) and extract text using smart extraction strategy"""
        # Handle list of URLs
        if isinstance(url, list):
            logger.info(f"Processing {len(url)} PDFs via OCR")
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
            
        # Check if text is mostly numbers (page numbers, etc)
        all_text = " ".join(valid_lines)
        words = all_text.split()
        if words:
            # Count how many "words" are just numbers
            number_words = sum(1 for word in words if word.isdigit())
            if len(words) > 5 and (number_words / len(words)) > 0.5:
                logger.info(f"Digital extraction is mostly numbers: {number_words}/{len(words)} numeric tokens")
                return False

        # Check for excessive single-word lines (sign of fragmented extraction)
        single_word_lines = sum(1 for line in valid_lines if len(line.split()) == 1)
        if len(valid_lines) > 10 and (single_word_lines / len(valid_lines)) > 0.5:
            logger.info(
                f"Digital extraction appears fragmented: {single_word_lines}/{len(valid_lines)} single-word lines"
            )
            return False

        # Check for reasonable sentence structure in first few lines
        sample_text = " ".join(valid_lines[:10])  # Check more lines
        words = sample_text.split()
        if len(words) > 10:
            # Should have some longer words and reasonable punctuation
            long_words = sum(1 for word in words if len(word) > 3 and not word.isdigit())
            if (long_words / len(words)) < 0.3:
                logger.info("Digital extraction lacks proper word structure")
                return False
                
        # Check for common agenda/meeting words to ensure we have real content
        common_words = ['meeting', 'agenda', 'council', 'item', 'public', 'board', 
                       'city', 'approval', 'discussion', 'report', 'minutes', 'call',
                       'the', 'and', 'to', 'of', 'for', 'in', 'on', 'at']
        text_lower = all_text.lower()
        found_common_words = sum(1 for word in common_words if word in text_lower)
        if found_common_words < 3:
            logger.info(f"Digital extraction lacks common meeting words (found only {found_common_words})")
            return False

        return True

    def _ocr_specific_pages(self, pdf_path: str, page_numbers: List[int]) -> dict:
        """OCR only specific pages with resource management"""
        ocr_results = {}
        
        # Check resources before starting
        try:
            self.resource_guard.check_resources()
        except RuntimeError as e:
            logger.error(f"Insufficient resources for OCR: {e}")
            return {page: f"[RESOURCE_ERROR: {e}]" for page in page_numbers}
        
        # Process pages in batches
        for i in range(0, len(page_numbers), OCR_BATCH_SIZE):
            batch_pages = page_numbers[i:i + OCR_BATCH_SIZE]
            
            with safe_temp_directory() as batch_temp_dir:
                for page_num in batch_pages:
                    try:
                        # Check if PDF still exists
                        if not os.path.exists(pdf_path):
                            logger.error(f"PDF file disappeared during processing: {pdf_path}")
                            ocr_results[page_num] = f"[ERROR: PDF file no longer exists]"
                            continue
                        
                        # Adjust DPI based on memory
                        mem_percent = psutil.virtual_memory().percent
                        dpi = 150 if mem_percent > 70 else 200
                        
                        pages = convert_from_path(
                            pdf_path, 
                            dpi=dpi, 
                            first_page=page_num, 
                            last_page=page_num,
                            output_folder=batch_temp_dir,
                            fmt='jpeg',
                            jpegopt={'quality': 85, 'optimize': True}
                        )
                        
                        if pages and len(pages) > 0:
                            try:
                                img = pages[0]
                                # Downsample if too large
                                if img.width * img.height > 10_000_000:
                                    scale = (10_000_000 / (img.width * img.height)) ** 0.5
                                    new_size = (int(img.width * scale), int(img.height * scale))
                                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                                
                                ocr_text = pytesseract.image_to_string(img)
                                ocr_results[page_num] = ocr_text
                                
                                # Clean up immediately
                                del img
                                del pages[0]
                            except Exception as ocr_error:
                                logger.warning(f"OCR failed for page {page_num}: {ocr_error}")
                                ocr_results[page_num] = f"[OCR_FAILED: {str(ocr_error)}]"
                        else:
                            logger.warning(f"No image generated for page {page_num}")
                            ocr_results[page_num] = f"[NO_IMAGE: Page {page_num}]"
                    except Exception as e:
                        logger.error(f"OCR failed for page {page_num}: {e}")
                        ocr_results[page_num] = f"[OCR_ERROR: {str(e)}]"
                    
                    # Force garbage collection
                    gc.collect()
            
            # Check resources between batches
            try:
                self.resource_guard.check_resources()
            except RuntimeError as e:
                logger.warning(f"Resource limit reached, stopping OCR: {e}")
                # Mark remaining pages as not processed
                for page in page_numbers[i + OCR_BATCH_SIZE:]:
                    ocr_results[page] = f"[NOT_PROCESSED: Resource limit reached]"
                break

        return ocr_results

    def _full_ocr(self, pdf_path: str) -> str:
        """Full OCR fallback for entire document with batch processing and resource management"""
        logger.info("Running full OCR with resource management...")
        
        # Set resource limits
        self.resource_guard.set_limits()
        
        # Initial resource check
        self.resource_guard.check_resources()

        with open(pdf_path, "rb") as f:
            reader = PdfReader(f)
            total_pages = len(reader.pages)
            
            # Check page count limit
            if total_pages > MAX_PAGES:
                raise ValueError(f"PDF has {total_pages} pages, exceeds maximum of {MAX_PAGES} pages")
            
            # Auto-limit based on available memory
            mem_available_mb = psutil.virtual_memory().available / 1024 / 1024
            auto_limit = int(mem_available_mb / 20)  # ~20MB per page estimate
            
            # Apply limits
            if total_pages > MAX_OCR_PAGES:
                logger.warning(f"PDF has {total_pages} pages, limiting to {MAX_OCR_PAGES} pages for OCR")
                pages_to_ocr = MAX_OCR_PAGES
            elif total_pages > auto_limit:
                logger.warning(f"Limited memory available, processing only {auto_limit} of {total_pages} pages")
                pages_to_ocr = auto_limit
            else:
                pages_to_ocr = total_pages

        all_text = ""
        processed_pages = 0
        
        # Process in batches to manage memory
        for batch_start in range(1, pages_to_ocr + 1, OCR_BATCH_SIZE):
            batch_end = min(batch_start + OCR_BATCH_SIZE - 1, pages_to_ocr)
            
            # Check resources before each batch
            try:
                self.resource_guard.check_resources()
            except RuntimeError as e:
                logger.error(f"Resource limit reached after {processed_pages} pages: {e}")
                all_text += f"\n\n[STOPPED: {e}. Processed {processed_pages} of {total_pages} pages]\n"
                break
            
            # Process batch in isolated temp directory
            with safe_temp_directory() as batch_temp_dir:
                logger.info(f"Processing pages {batch_start}-{batch_end} of {pages_to_ocr}...")
                
                for page_num in range(batch_start, batch_end + 1):
                    try:
                        # Check if PDF still exists
                        if not os.path.exists(pdf_path):
                            logger.error(f"PDF file disappeared during processing: {pdf_path}")
                            all_text += f"\n--- PAGE {page_num} ---\n[ERROR: PDF file no longer exists]\n"
                            continue
                        
                        # Convert with lower DPI if memory is tight
                        mem_percent = psutil.virtual_memory().percent
                        dpi = 150 if mem_percent > 70 else 200
                        
                        pages = convert_from_path(
                            pdf_path, 
                            dpi=dpi, 
                            first_page=page_num, 
                            last_page=page_num,
                            output_folder=batch_temp_dir,
                            fmt='jpeg',  # JPEG uses less memory than PPM
                            jpegopt={'quality': 85, 'optimize': True}
                        )
                        
                        if pages and len(pages) > 0:
                            try:
                                # Downsample large images
                                img = pages[0]
                                if img.width * img.height > 10_000_000:  # 10MP
                                    scale = (10_000_000 / (img.width * img.height)) ** 0.5
                                    new_size = (int(img.width * scale), int(img.height * scale))
                                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                                
                                ocr_text = pytesseract.image_to_string(img)
                                all_text += f"\n--- PAGE {page_num} ---\n{ocr_text}\n"
                                processed_pages += 1
                                
                                # Clean up image immediately
                                del img
                                if 'pages' in locals():
                                    del pages[0]
                                    
                            except Exception as ocr_error:
                                logger.warning(f"OCR failed for page {page_num}: {ocr_error}")
                                all_text += f"\n--- PAGE {page_num} ---\n[OCR_FAILED: {str(ocr_error)}]\n"
                        else:
                            logger.warning(f"No image generated for page {page_num}")
                            all_text += f"\n--- PAGE {page_num} ---\n[NO_IMAGE: conversion failed]\n"

                    except Exception as e:
                        logger.warning(f"OCR error on page {page_num}: {e}")
                        all_text += f"\n--- PAGE {page_num} ---\n[OCR_ERROR: {str(e)}]\n"
                    
                    # Force garbage collection after each page
                    gc.collect()
            
            # Log progress
            logger.info(f"OCR progress: {min(batch_end, pages_to_ocr)}/{pages_to_ocr} pages processed")
            
            # Force garbage collection after each batch
            gc.collect()

        # Add summary note
        if processed_pages < total_pages:
            all_text += f"\n\n[NOTE: Document has {total_pages} pages total. Processed {processed_pages} pages due to resource limits.]\n"

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

    def process(self, url: Union[str, List[str]], english_threshold: float = 0.7) -> str:
        """Complete pipeline: download → extract → clean"""
        # Extract text (handles both single URLs and lists)
        raw_text = self.download_and_extract_text(url)
        
        # Clean text with configurable threshold
        logger.info(f"Cleaning text for url: {url}")
        cleaned_text = self.clean_text(raw_text, english_threshold)
        
        return cleaned_text