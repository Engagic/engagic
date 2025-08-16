"""PDF Chunking for Large Documents

This module provides chunking functionality for PDFs that exceed the API size limit.
It splits large PDFs into smaller chunks that can be processed separately.
"""

import logging
import io
from typing import List, Optional
import PyPDF2
import requests
from dataclasses import dataclass

logger = logging.getLogger("engagic")

# Maximum size for each chunk (leave some buffer for request overhead)
MAX_CHUNK_SIZE = 30 * 1024 * 1024  # 30MB per chunk (under 32MB limit)
MAX_PAGES_PER_CHUNK = 90  # Stay under 100 page limit


@dataclass
class PDFChunk:
    """Represents a chunk of a PDF document"""
    content: bytes
    start_page: int
    end_page: int
    chunk_number: int
    total_chunks: int
    size_bytes: int


class PDFChunker:
    """Handles splitting large PDFs into processable chunks"""
    
    def __init__(self):
        self.logger = logger
    
    def download_pdf(self, url: str, max_size: Optional[int] = None) -> bytes:
        """Download PDF with optional size limit"""
        try:
            response = requests.get(
                url,
                timeout=60,
                stream=True,
                headers={"User-Agent": "Engagic-PDF-Chunker/1.0"},
            )
            response.raise_for_status()
            
            pdf_content = b""
            downloaded = 0
            
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded += len(chunk)
                    if max_size and downloaded > max_size:
                        raise ValueError(f"PDF size exceeds limit of {max_size} bytes")
                    pdf_content += chunk
            
            self.logger.info(f"Downloaded PDF: {downloaded:,} bytes")
            return pdf_content
            
        except requests.RequestException as e:
            raise Exception(f"Failed to download PDF: {e}")
    
    def split_pdf_by_size(self, pdf_content: bytes) -> List[PDFChunk]:
        """Split PDF into chunks based on size and page limits"""
        try:
            # Load PDF
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
            total_pages = len(pdf_reader.pages)
            
            self.logger.info(f"PDF has {total_pages} pages, {len(pdf_content):,} bytes")
            
            chunks = []
            current_chunk_pages = []
            current_chunk_size = 0
            start_page = 0
            chunk_number = 0
            
            for page_num in range(total_pages):
                # Extract page
                page = pdf_reader.pages[page_num]
                
                # Create a temporary PDF with just this page to estimate size
                temp_writer = PyPDF2.PdfWriter()
                temp_writer.add_page(page)
                
                # Get page size
                page_buffer = io.BytesIO()
                temp_writer.write(page_buffer)
                page_size = page_buffer.tell()
                
                # Check if adding this page would exceed limits
                pages_in_chunk = len(current_chunk_pages)
                would_exceed_size = (current_chunk_size + page_size) > MAX_CHUNK_SIZE
                would_exceed_pages = pages_in_chunk >= MAX_PAGES_PER_CHUNK
                
                if current_chunk_pages and (would_exceed_size or would_exceed_pages):
                    # Save current chunk
                    chunk_content = self._create_pdf_from_pages(pdf_reader, current_chunk_pages)
                    chunks.append(PDFChunk(
                        content=chunk_content,
                        start_page=start_page,
                        end_page=start_page + len(current_chunk_pages) - 1,
                        chunk_number=chunk_number,
                        total_chunks=0,  # Will be updated later
                        size_bytes=len(chunk_content)
                    ))
                    
                    # Start new chunk
                    chunk_number += 1
                    start_page = page_num
                    current_chunk_pages = [page_num]
                    current_chunk_size = page_size
                    
                    self.logger.info(f"Created chunk {chunk_number} with {len(chunks[-1].content):,} bytes")
                else:
                    # Add page to current chunk
                    current_chunk_pages.append(page_num)
                    current_chunk_size += page_size
            
            # Don't forget the last chunk
            if current_chunk_pages:
                chunk_content = self._create_pdf_from_pages(pdf_reader, current_chunk_pages)
                chunks.append(PDFChunk(
                    content=chunk_content,
                    start_page=start_page,
                    end_page=start_page + len(current_chunk_pages) - 1,
                    chunk_number=chunk_number,
                    total_chunks=0,
                    size_bytes=len(chunk_content)
                ))
                self.logger.info(f"Created final chunk {chunk_number + 1} with {len(chunk_content):,} bytes")
            
            # Update total_chunks for all chunks
            total_chunks = len(chunks)
            for chunk in chunks:
                chunk.total_chunks = total_chunks
            
            self.logger.info(f"Split PDF into {total_chunks} chunks")
            return chunks
            
        except Exception as e:
            self.logger.error(f"Failed to split PDF: {e}")
            raise
    
    def _create_pdf_from_pages(self, pdf_reader: PyPDF2.PdfReader, page_numbers: List[int]) -> bytes:
        """Create a new PDF containing only specified pages"""
        writer = PyPDF2.PdfWriter()
        
        for page_num in page_numbers:
            writer.add_page(pdf_reader.pages[page_num])
        
        # Write to bytes
        output_buffer = io.BytesIO()
        writer.write(output_buffer)
        output_buffer.seek(0)
        return output_buffer.read()
    
    def create_chunk_summary_prompt(self, chunk: PDFChunk) -> str:
        """Create a prompt for processing a PDF chunk"""
        if chunk.total_chunks == 1:
            # Single chunk, use normal prompt
            return ""
        
        return f"""This is chunk {chunk.chunk_number + 1} of {chunk.total_chunks} from a larger document.
Pages {chunk.start_page + 1} to {chunk.end_page + 1} of the original document.
Please analyze this portion and provide details about the content in this chunk.
Focus on extracting all specific information, as the chunks will be combined later."""
    
    def combine_chunk_summaries(self, summaries: List[str], chunk_info: List[PDFChunk]) -> str:
        """Combine summaries from multiple chunks into a coherent summary"""
        if len(summaries) == 1:
            return summaries[0]
        
        combined = []
        combined.append("**Document Overview:**")
        combined.append(f"This document was processed in {len(summaries)} chunks due to its size.")
        combined.append("")
        
        # Add each chunk summary with context
        for i, (summary, chunk) in enumerate(zip(summaries, chunk_info)):
            combined.append(f"**Section {i + 1} (Pages {chunk.start_page + 1}-{chunk.end_page + 1}):**")
            combined.append(summary)
            combined.append("")
        
        return "\n".join(combined)
    
    def estimate_chunk_tokens(self, chunk: PDFChunk) -> int:
        """Estimate token count for a chunk"""
        # Rough estimates
        pages = chunk.end_page - chunk.start_page + 1
        base_tokens = pages * 2000  # ~2000 tokens per page
        
        # Add overhead for prompt
        prompt_tokens = 500
        
        return base_tokens + prompt_tokens