import requests
import tempfile
import os
import re
import time
import pytesseract
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
import anthropic
from typing import List

class AgendaProcessor:
    def __init__(self, api_key=None):
        """Initialize processor with optional API key"""
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable required")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.english_words = self._load_english_words()
    
    def _load_english_words(self):
        """Load English word set with comprehensive fallback for civic terms"""
        try:
            import nltk
            from nltk.corpus import words
            return set(word.lower() for word in words.words())
        except:
            # Comprehensive civic/municipal terms
            return set([
                'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
                'council', 'city', 'meeting', 'agenda', 'item', 'public', 'comment', 'session',
                'board', 'commission', 'appointment', 'ordinance', 'resolution', 'budget',
                'planning', 'zoning', 'development', 'traffic', 'safety', 'park', 'library',
                'police', 'fire', 'emergency', 'infrastructure', 'project', 'contract',
                'approval', 'review', 'hearing', 'closed', 'property', 'agreement', 'staff',
                'street', 'avenue', 'boulevard', 'road', 'drive', 'lane', 'court', 'place',
                'north', 'south', 'east', 'west', 'permit', 'variance', 'conditional', 'use',
                'environmental', 'impact', 'report', 'ceqa', 'downtown', 'residential',
                'commercial', 'industrial', 'mixed', 'density', 'housing', 'affordable',
                'transportation', 'transit', 'parking', 'bicycle', 'pedestrian', 'crosswalk'
            ])
    
    def download_and_extract_text(self, url: str) -> str:
        """Download PDF and extract text using smart extraction strategy"""
        print(f"Downloading and processing PDF from: {url}")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Download PDF
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
            except requests.RequestException as e:
                raise Exception(f"Failed to download PDF: {e}")
            
            pdf_path = os.path.join(temp_dir, "agenda.pdf")
            with open(pdf_path, 'wb') as f:
                f.write(response.content)
            
            # Smart text extraction
            raw_text = self._extract_text_smart(pdf_path)
            
            # Normalize the formatting
            return self._normalize_text_formatting(raw_text)
    
    def _extract_text_smart(self, pdf_path: str) -> str:
        """Try PDFReader first, fall back to OCR for problematic pages"""
        print("Attempting digital text extraction...")
        
        try:
            with open(pdf_path, 'rb') as f:
                reader = PdfReader(f)
                total_pages = len(reader.pages)
                print(f"Processing {total_pages} pages...")
                
                all_text = ""
                ocr_pages = []
                
                for page_num, page in enumerate(reader.pages, 1):
                    try:
                        page_text = page.extract_text()
                        
                        # Check if extraction was successful
                        if self._is_good_digital_extraction(page_text):
                            all_text += f"\n--- PAGE {page_num} ---\n{page_text}\n"
                            if page_num % 10 == 0:
                                print(f"Digital extraction: {page_num}/{total_pages} pages...")
                        else:
                            # Mark for OCR
                            ocr_pages.append(page_num)
                            all_text += f"\n--- PAGE {page_num} ---\n[NEEDS_OCR]\n"
                    
                    except Exception as e:
                        print(f"Error extracting page {page_num}: {e}")
                        ocr_pages.append(page_num)
                        all_text += f"\n--- PAGE {page_num} ---\n[NEEDS_OCR]\n"
                
                # OCR the problematic pages
                if ocr_pages:
                    print(f"Running OCR on {len(ocr_pages)} pages...")
                    ocr_text = self._ocr_specific_pages(pdf_path, ocr_pages)
                    
                    # Replace [NEEDS_OCR] markers with actual OCR text
                    for page_num in ocr_pages:
                        marker = f"--- PAGE {page_num} ---\n[NEEDS_OCR]"
                        if page_num in ocr_text:
                            replacement = f"--- PAGE {page_num} ---\n{ocr_text[page_num]}"
                            all_text = all_text.replace(marker, replacement)
                
                return all_text
            
        except Exception as e:
            print(f"Digital extraction failed: {e}")
            print("Falling back to full OCR...")
            return self._full_ocr(pdf_path)
    
    def _normalize_text_formatting(self, raw_text: str) -> str:
        """Fix weird PDFReader formatting by reconstructing proper lines"""
        print("Normalizing text formatting...")
        
        pages = raw_text.split("--- PAGE")
        normalized_pages = []
        
        for i, page in enumerate(pages):
            if i == 0 and not page.strip():
                continue
            
            # Extract page number and content
            page_match = re.match(r'\s*(\d+)\s*---\s*\n(.*)', page, re.DOTALL)
            if not page_match:
                continue
            
            page_num = page_match.group(1)
            page_content = page_match.group(2)
            
            # Normalize this page
            normalized_content = self._normalize_page_content(page_content)
            normalized_pages.append(f"--- PAGE {page_num} ---\n{normalized_content}\n")
        
        return "\n".join(normalized_pages)
    
    def _normalize_page_content(self, content: str) -> str:
        """Reconstruct proper paragraphs from weirdly formatted text"""
        lines = content.split('\n')
        
        # Group lines into logical blocks
        blocks = []
        current_block = []
        
        for line in lines:
            line = line.strip()
            
            if not line:
                # Empty line - end current block if it has content
                if current_block:
                    blocks.append(' '.join(current_block))
                    current_block = []
                continue
            
            # Check if this line should start a new block
            if self._should_start_new_block(line, current_block):
                if current_block:
                    blocks.append(' '.join(current_block))
                current_block = [line]
            else:
                # Add to current block
                current_block.append(line)
        
        # Don't forget the last block
        if current_block:
            blocks.append(' '.join(current_block))
        
        # Clean up each block
        cleaned_blocks = []
        for block in blocks:
            # Remove excessive spaces
            cleaned_block = re.sub(r'\s+', ' ', block).strip()
            if cleaned_block:
                cleaned_blocks.append(cleaned_block)
        
        return '\n\n'.join(cleaned_blocks)
    
    def _should_start_new_block(self, line: str, current_block: list) -> bool:
        """Determine if this line should start a new paragraph/block"""
        if not current_block:
            return True
        
        # Section headers (all caps, short)
        if line.isupper() and len(line) < 50:
            return True
        
        # Numbered items
        if re.match(r'^\d+[\.\)]\s', line):
            return True
        
        # Lettered items  
        if re.match(r'^[A-Z][\.\)]\s', line):
            return True
        
        # Time patterns
        if re.match(r'^\d{1,2}:\d{2}\s*(AM|PM)', line, re.IGNORECASE):
            return True
        
        # URLs or email addresses
        if re.search(r'(https?://|@.*\.)', line):
            return True
        
        # Meeting info patterns
        if re.search(r'(Meeting ID|Phone:|Council Chambers)', line, re.IGNORECASE):
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
        lines = text.split('\n')
        valid_lines = [line.strip() for line in lines if line.strip()]
        
        if not valid_lines:
            return False
        
        # Check for excessive single-word lines (sign of fragmented extraction)
        single_word_lines = sum(1 for line in valid_lines if len(line.split()) == 1)
        if len(valid_lines) > 10 and (single_word_lines / len(valid_lines)) > 0.5:
            print(f"Digital extraction appears fragmented: {single_word_lines}/{len(valid_lines)} single-word lines")
            return False
        
        # Check for reasonable sentence structure in first few lines
        sample_text = ' '.join(valid_lines[:5])
        words = sample_text.split()
        if len(words) > 10:
            # Should have some longer words and reasonable punctuation
            long_words = sum(1 for word in words if len(word) > 3)
            if (long_words / len(words)) < 0.3:
                print("Digital extraction lacks proper word structure")
                return False
        
        return True
    
    def _ocr_specific_pages(self, pdf_path: str, page_numbers: List[int]) -> dict:
        """OCR only specific pages"""
        ocr_results = {}
        
        for page_num in page_numbers:
            try:
                pages = convert_from_path(pdf_path, dpi=200, first_page=page_num, last_page=page_num)
                ocr_text = pytesseract.image_to_string(pages[0])
                ocr_results[page_num] = ocr_text
            except Exception as e:
                print(f"OCR failed for page {page_num}: {e}")
                ocr_results[page_num] = f"[OCR_ERROR: {str(e)}]"
        
        return ocr_results
    
    def _full_ocr(self, pdf_path: str) -> str:
        """Full OCR fallback for entire document"""
        print("Running full OCR...")
        
        with open(pdf_path, 'rb') as f:
            reader = PdfReader(f)
            total_pages = len(reader.pages)
        
        all_text = ""
        
        for page_num in range(1, total_pages + 1):
            try:
                pages = convert_from_path(pdf_path, dpi=200, first_page=page_num, last_page=page_num)
                ocr_text = pytesseract.image_to_string(pages[0])
                all_text += f"\n--- PAGE {page_num} ---\n{ocr_text}\n"
                
                if page_num % 10 == 0:
                    print(f"OCR progress: {page_num}/{total_pages} pages...")
            
            except Exception as e:
                print(f"OCR error on page {page_num}: {e}")
                all_text += f"\n--- PAGE {page_num} ---\n[OCR_ERROR: {str(e)}]\n"
        
        return all_text
    
    def clean_text(self, raw_text: str, english_threshold: float = 0.7) -> str:
        """Clean text using simple English word percentage check"""
        print(f"Cleaning text with {english_threshold*100}% English word threshold...")
        
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
            page_match = re.match(r'\s*(\d+)\s*---\s*\n(.*)', page, re.DOTALL)
            if not page_match:
                continue
            
            page_num = page_match.group(1)
            page_content = page_match.group(2)
            
            # Process lines
            lines = page_content.split('\n')
            cleaned_lines = []
            
            for line in lines:
                total_lines_processed += 1
                line = line.strip()
                
                if not line:
                    continue
                
                # Check if line meets English word threshold
                if self._meets_english_threshold(line, english_threshold):
                    # Basic cleanup - remove weird characters but keep punctuation
                    cleaned_line = re.sub(r'[^\w\s\.,;:()"\'\-$%/]', ' ', line)
                    cleaned_line = re.sub(r'\s+', ' ', cleaned_line).strip()
                    
                    if cleaned_line:
                        cleaned_lines.append(cleaned_line)
                        total_lines_kept += 1
            
            # Keep page if it has any valid content
            if cleaned_lines:
                cleaned_content = '\n'.join(cleaned_lines)
                cleaned_pages.append(f"--- PAGE {page_num} ---\n{cleaned_content}\n")
                pages_kept += 1
            else:
                pages_skipped += 1
        
        result = "\n".join(cleaned_pages)
        print(f"Cleaning complete: {total_lines_kept}/{total_lines_processed} lines kept")
        print(f"Pages: {pages_kept} kept, {pages_skipped} skipped")
        
        return result
    
    def _meets_english_threshold(self, line: str, threshold: float) -> bool:
        """Check if line meets the English word percentage threshold"""
        # Extract words (2+ letters)
        words = re.findall(r'\b[a-zA-Z]{2,}\b', line.lower())
        
        if len(words) == 0:
            # No words found - keep very short lines, skip long ones
            return len(line.strip()) < 20
        
        # Count valid English words
        valid_words = sum(1 for word in words if word in self.english_words)
        
        # Calculate percentage
        percentage = valid_words / len(words)
        
        return percentage >= threshold
    
    def _chunk_by_agenda_items(self, text: str, max_chunk_size: int = 75000) -> List[str]:
        """Smart chunking that respects agenda item boundaries"""
        # Look for agenda item patterns
        agenda_patterns = [
            r'\n\s*\d+\.\s+[A-Z]',  # "1. ITEM NAME"
            r'\n\s*[A-Z]\.\s+[A-Z]',  # "A. ITEM NAME"
            r'\n\s*Item\s+\d+',  # "Item 1"
            r'\n\s*AGENDA\s+ITEM',  # "AGENDA ITEM"
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
                chunk_text = text[current_chunk_start:split_points[i-1]]
                chunks.append(chunk_text)
                current_chunk_start = split_points[i-1]
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
    
    def summarize(self, text: str, rate_limit_delay: int = 5) -> str:
        """Summarize text with improved prompting"""
        chunks = self._chunk_by_agenda_items(text)
        print(f"Split into {len(chunks)} chunks for processing")
        
        summaries = []
        
        for i, chunk in enumerate(chunks):
            print(f"Processing chunk {i+1}/{len(chunks)}...")
            
            try:
                response = self.client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=4000,
                    messages=[{
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
                        {chunk}"""
                    }]
                )
                
                summaries.append(f"--- SECTION {i+1} SUMMARY ---\n{response.content[0].text}\n")
                
                # Rate limiting
                if i < len(chunks) - 1:
                    print(f"Waiting {rate_limit_delay} seconds...")
                    time.sleep(rate_limit_delay)
                    
            except Exception as e:
                print(f"Error processing chunk {i+1}: {e}")
                summaries.append(f"--- SECTION {i+1} SUMMARY ---\n[ERROR: Could not process this section - {str(e)}]\n")
        
        return "\n".join(summaries)
    
    def process_agenda(self, url: str, english_threshold: float = 0.7, save_raw: bool = True, save_cleaned: bool = True) -> str:
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
            print("Starting summarization...")
            summary = self.summarize(cleaned_text)
            
            self._save_text(summary, "agenda_summary.txt")
            print("Complete! Summary saved to agenda_summary.txt")
            
            return summary
        
        except Exception as e:
            print(f"Error processing agenda: {e}")
            raise
    
    def _save_text(self, text: str, filename: str) -> None:
        """Save text to file with UTF-8 encoding"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"Saved to {filename} ({len(text)} characters)")

def main():
    """Example usage"""
    try:
        processor = AgendaProcessor()

        #url = "https://cityofpaloalto.primegov.com/Public/CompiledDocument?meetingTemplateId=16124&compileOutputType=1"

        '''raw_text = processor.download_and_extract_text(url)
        processor._save_text(raw_text, "raw_agenda.txt")

        cleaned_text = processor.clean_text(raw_text, 0.7)
        processor._save_text(cleaned_text, "cleaned_agenda.txt")'''

        with open("cleaned_agenda.txt", 'r', encoding='utf-8') as f:
            cleaned_text = f.read()
    
        summary = processor.summarize(cleaned_text)
        processor._save_text(summary, "agenda_summary.txt")

    except Exception as e:
        print(f"Error in main: {e}")

if __name__ == "__main__":
    main()