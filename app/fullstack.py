import requests
import tempfile
import os
import re
import time
import pytesseract
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
import anthropic
import argparse
import sys
import logging
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import threading
from multiprocessing import cpu_count
from database import MeetingDatabase, get_city_info

logger = logging.getLogger("engagic")


class AgendaProcessor:
    def __init__(self, api_key=None, db_path="/root/engagic/app/meetings.db"):
        """Initialize processor with optional API key and database"""
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable required")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.english_words = self._load_english_words()
        self.db = MeetingDatabase(db_path)
        
        # Cache compiled regex patterns for performance
        self.agenda_patterns = [
            re.compile(r"\n\s*\d+\.\s+[A-Z]"),  # "1. ITEM NAME"
            re.compile(r"\n\s*[A-Z]\.\s+[A-Z]"),  # "A. ITEM NAME"
            re.compile(r"\n\s*Item\s+\d+"),  # "Item 1"
            re.compile(r"\n\s*AGENDA\s+ITEM"),  # "AGENDA ITEM"
        ]
        
        # Cache other frequently used regex patterns
        self.text_cleaning_patterns = {
            'weird_chars': re.compile(r'[^\w\s\.,;:()"\'\-$%/]'),
            'multiple_spaces': re.compile(r"\s+"),
            'english_words': re.compile(r"\b[a-zA-Z]{2,}\b"),
            'numbered_items': re.compile(r"^\d+[\.\)]\s"),
            'lettered_items': re.compile(r"^[A-Z][\.\)]\s"),
            'time_patterns': re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)", re.IGNORECASE),
            'url_email': re.compile(r"(https?://|@.*\.)"),
            'meeting_info': re.compile(r"(Meeting ID|Phone:|Council Chambers)", re.IGNORECASE)
        }

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

    def download_and_extract_text(self, url: str) -> str:
        """Download PDF and extract text using smart extraction strategy"""
        logger.info(f"Downloading and processing PDF from: {url}")

        with tempfile.TemporaryDirectory() as temp_dir:
            # Download PDF
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
            except requests.RequestException as e:
                raise Exception(f"Failed to download PDF: {e}")

            pdf_path = os.path.join(temp_dir, "agenda.pdf")
            with open(pdf_path, "wb") as f:
                f.write(response.content)

            # Smart text extraction
            raw_text = self._extract_text_smart(pdf_path)

            # Normalize the formatting
            return self._normalize_text_formatting(raw_text)

    def _extract_text_smart(self, pdf_path: str) -> str:
        """Try PDFReader first, fall back to OCR for problematic pages"""
        logger.info("Attempting digital text extraction...")

        try:
            with open(pdf_path, "rb") as f:
                reader = PdfReader(f)
                total_pages = len(reader.pages)
                logger.info(f"Processing {total_pages} pages...")

                all_text = ""
                ocr_pages = []

                # For large documents, use parallel digital extraction
                if total_pages > 20:
                    logger.info(f"Using parallel digital extraction for {total_pages} pages")
                    all_text, ocr_pages = self._parallel_digital_extraction(reader, total_pages)
                else:
                    # Sequential processing for smaller documents
                    for page_num, page in enumerate(reader.pages, 1):
                        try:
                            page_text = page.extract_text()

                            # Check if extraction was successful
                            if self._is_good_digital_extraction(page_text):
                                all_text += f"\n--- PAGE {page_num} ---\n{page_text}\n"
                                if page_num % 10 == 0:
                                    logger.info(f"Digital extraction: {page_num}/{total_pages} pages...")
                            else:
                                # Mark for OCR
                                ocr_pages.append(page_num)
                                all_text += f"\n--- PAGE {page_num} ---\n[NEEDS_OCR]\n"

                        except Exception as e:
                            logger.warning(f"Error extracting page {page_num}: {e}")
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
            logger.error(f"Digital extraction failed: {e}")
            logger.info("Falling back to full OCR...")
            return self._full_ocr(pdf_path)

    def _normalize_text_formatting(self, raw_text: str) -> str:
        """Fix weird PDFReader formatting by reconstructing proper lines"""
        logger.info("Normalizing text formatting...")

        pages = raw_text.split("--- PAGE")
        page_contents = []
        page_numbers = []

        # Extract page data for processing
        for i, page in enumerate(pages):
            if i == 0 and not page.strip():
                continue

            page_match = re.match(r"\s*(\d+)\s*---\s*\n(.*)", page, re.DOTALL)
            if page_match:
                page_numbers.append(page_match.group(1))
                page_contents.append(page_match.group(2))

        # Use parallel processing for large documents
        if len(page_contents) > 10:
            logger.info(f"Using parallel normalization for {len(page_contents)} pages")
            normalized_contents = self._normalize_pages_parallel(page_contents)
        else:
            # Sequential for small documents
            normalized_contents = [self._normalize_page_content(content) for content in page_contents]

        # Reconstruct the text
        normalized_pages = []
        for page_num, normalized_content in zip(page_numbers, normalized_contents):
            normalized_pages.append(f"--- PAGE {page_num} ---\n{normalized_content}\n")

        return "\n".join(normalized_pages)

    def _normalize_pages_parallel(self, page_contents: List[str]) -> List[str]:
        """Normalize multiple pages in parallel using ProcessPoolExecutor for CPU-bound work"""
        max_workers = min(cpu_count(), len(page_contents))
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            normalized = list(executor.map(self._normalize_page_content, page_contents))
        
        return normalized

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

        # Check patterns using cached compiled regexes
        if self.text_cleaning_patterns['numbered_items'].match(line):
            return True

        if self.text_cleaning_patterns['lettered_items'].match(line):
            return True

        if self.text_cleaning_patterns['time_patterns'].match(line):
            return True

        if self.text_cleaning_patterns['url_email'].search(line):
            return True

        if self.text_cleaning_patterns['meeting_info'].search(line):
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
            logger.warning(f"Digital extraction appears fragmented: {single_word_lines}/{len(valid_lines)} single-word lines")
            return False

        # Check for reasonable sentence structure in first few lines
        sample_text = " ".join(valid_lines[:5])
        words = sample_text.split()
        if len(words) > 10:
            # Should have some longer words and reasonable punctuation
            long_words = sum(1 for word in words if len(word) > 3)
            if (long_words / len(words)) < 0.3:
                logger.warning("Digital extraction lacks proper word structure")
                return False

        return True

    def _extract_single_page_digital(self, page_data: tuple) -> tuple[int, str, bool]:
        """Extract text from a single page - thread-safe function
        Returns: (page_num, text, needs_ocr)
        """
        page_num, page = page_data
        try:
            page_text = page.extract_text()
            if self._is_good_digital_extraction(page_text):
                return page_num, page_text, False
            else:
                return page_num, "[NEEDS_OCR]", True
        except Exception as e:
            logger.warning(f"Error extracting page {page_num}: {e}")
            return page_num, "[NEEDS_OCR]", True

    def _parallel_digital_extraction(self, reader, total_pages: int) -> tuple[str, List[int]]:
        """Extract text from multiple pages in parallel"""
        all_text = ""
        ocr_pages = []
        
        # Prepare page data for parallel processing
        page_data = [(page_num, page) for page_num, page in enumerate(reader.pages, 1)]
        
        max_workers = min(6, total_pages)  # Limit concurrent threads
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all extraction tasks
            future_to_page = {
                executor.submit(self._extract_single_page_digital, data): data[0] 
                for data in page_data
            }
            
            # Collect results and maintain page order
            results = {}
            for future in as_completed(future_to_page):
                page_num, text, needs_ocr = future.result()
                results[page_num] = (text, needs_ocr)
                
                if page_num % 20 == 0:
                    logger.info(f"Digital extraction progress: {page_num}/{total_pages} pages...")
            
            # Reconstruct text in proper order and collect OCR pages
            for page_num in range(1, total_pages + 1):
                text, needs_ocr = results[page_num]
                all_text += f"\n--- PAGE {page_num} ---\n{text}\n"
                if needs_ocr:
                    ocr_pages.append(page_num)
        
        logger.info(f"Parallel digital extraction completed: {len(ocr_pages)} pages need OCR")
        return all_text, ocr_pages

    def _ocr_single_page(self, pdf_path: str, page_num: int) -> tuple[int, str]:
        """OCR a single page - thread-safe function"""
        try:
            pages = convert_from_path(
                pdf_path, dpi=200, first_page=page_num, last_page=page_num
            )
            ocr_text = pytesseract.image_to_string(pages[0])
            return page_num, ocr_text
        except Exception as e:
            logger.error(f"OCR failed for page {page_num}: {e}")
            return page_num, f"[OCR_ERROR: {str(e)}]"

    def _ocr_specific_pages(self, pdf_path: str, page_numbers: List[int]) -> dict:
        """OCR multiple pages in parallel"""
        logger.info(f"Starting parallel OCR for {len(page_numbers)} pages")
        ocr_results = {}
        
        # Use ThreadPoolExecutor for I/O bound OCR operations
        max_workers = min(4, len(page_numbers))  # Don't overwhelm the system
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all OCR tasks
            future_to_page = {
                executor.submit(self._ocr_single_page, pdf_path, page_num): page_num 
                for page_num in page_numbers
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_page):
                page_num, ocr_text = future.result()
                ocr_results[page_num] = ocr_text
                
        logger.info(f"Completed parallel OCR for {len(page_numbers)} pages")
        return ocr_results

    def _full_ocr(self, pdf_path: str) -> str:
        """Full OCR fallback for entire document using parallel processing"""
        logger.info("Running parallel full OCR...")

        with open(pdf_path, "rb") as f:
            reader = PdfReader(f)
            total_pages = len(reader.pages)

        page_numbers = list(range(1, total_pages + 1))
        ocr_results = self._ocr_specific_pages(pdf_path, page_numbers)
        
        # Reconstruct text in proper page order
        all_text = ""
        for page_num in page_numbers:
            ocr_text = ocr_results.get(page_num, f"[MISSING_PAGE: {page_num}]")
            all_text += f"\n--- PAGE {page_num} ---\n{ocr_text}\n"

        return all_text

    def clean_text(self, raw_text: str, english_threshold: float = 0.7) -> str:
        """Clean text using simple English word percentage check"""
        logger.info(f"Cleaning text with {english_threshold * 100}% English word threshold...")

        pages = raw_text.split("--- PAGE")
        cleaned_pages = []
        total_lines_kept = 0
        total_lines_processed = 0
        pages_kept = 0
        pages_skipped = 0

        for i, page in enumerate(pages):
            if i == 0 and not page.strip():
                continue

            # Extract page number and content
            page_match = re.match(r"\s*(\d+)\s*---\s*\n(.*)", page, re.DOTALL)
            if not page_match:
                continue

            page_num = page_match.group(1)
            page_content = page_match.group(2)

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
                    # Basic cleanup using cached patterns
                    cleaned_line = self.text_cleaning_patterns['weird_chars'].sub(" ", line)
                    cleaned_line = self.text_cleaning_patterns['multiple_spaces'].sub(" ", cleaned_line).strip()

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
        logger.info(f"Cleaning complete: {total_lines_kept}/{total_lines_processed} lines kept")
        logger.info(f"Pages: {pages_kept} kept, {pages_skipped} skipped")

        return result

    def _meets_english_threshold(self, line: str, threshold: float) -> bool:
        """Check if line meets the English word percentage threshold"""
        # Extract words using cached pattern
        words = self.text_cleaning_patterns['english_words'].findall(line.lower())

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
        # Find all potential split points using cached patterns
        split_points = [0]
        for pattern in self.agenda_patterns:
            for match in pattern.finditer(text):
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

    def summarize(self, text: str, adaptive_delay: bool = True) -> str:
        """Summarize text with optimized chunking and adaptive rate limiting"""
        chunks = self._chunk_by_agenda_items(text, max_chunk_size=120000)  # Larger chunks for efficiency
        logger.info(f"Split into {len(chunks)} chunks for processing")

        summaries = []
        start_time = time.time()

        for i, chunk in enumerate(chunks):
            chunk_start = time.time()
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

                # Adaptive rate limiting based on API response time
                if i < len(chunks) - 1 and adaptive_delay:
                    chunk_duration = time.time() - chunk_start
                    # Smart delay: minimum 1s, but adapt based on API response time
                    delay = max(1.0, min(3.0, chunk_duration * 0.5))
                    logger.info(f"Adaptive delay: {delay:.1f}s (chunk took {chunk_duration:.1f}s)")
                    time.sleep(delay)
                elif i < len(chunks) - 1:
                    # Fallback to shorter fixed delay
                    time.sleep(2.0)

            except Exception as e:
                logger.error(f"Error processing chunk {i + 1}: {e}")
                summaries.append(
                    f"--- SECTION {i + 1} SUMMARY ---\n[ERROR: Could not process this section - {str(e)}]\n"
                )

        total_time = time.time() - start_time
        logger.info(f"LLM processing completed in {total_time:.1f}s for {len(chunks)} chunks")
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
            city_info = get_city_info(city_slug) if city_slug else {}

            # Merge meeting data with city info
            full_meeting_data = {**meeting_data, **city_info}

            # Process the agenda
            summary = self.process_agenda(
                packet_url, save_raw=False, save_cleaned=False
            )
            processing_time = time.time() - start_time

            # Store in database
            vendor = meeting_data.get("vendor")
            meeting_id = self.db.store_meeting_summary(
                full_meeting_data, summary, processing_time, vendor
            )

            logger.info(f"Processed and cached agenda {packet_url} in {processing_time:.1f}s (ID: {meeting_id})")

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
        url: str,
        english_threshold: float = 0.7,
        save_raw: bool = True,
        save_cleaned: bool = True,
    ) -> str:
        """Complete pipeline: download → clean → summarize"""
        try:
            # Extract text
            raw_text = self.download_and_extract_text(url)

            if save_raw:
                self._save_text(raw_text, "raw_agenda.txt")

            # Clean text with configurable threshold
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
        with open(filename, "w", encoding="utf-8") as f:
            f.write(text)
        logger.info(f"Saved to {filename} ({len(text)} characters)")

    def download_packet(self, url: str, output_path: str = None) -> str:
        """Download PDF packet and save to file"""
        if not url.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")

        if not output_path:
            output_path = "downloaded_packet.pdf"

        logger.info(f"Downloading packet from: {url}")

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            raise Exception(f"Failed to download PDF: {e}")

        with open(output_path, "wb") as f:
            f.write(response.content)

        logger.info(f"Packet saved to {output_path} ({len(response.content)} bytes)")
        return output_path

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
        logger.info("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
