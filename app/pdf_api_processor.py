import logging
import requests
import base64
import os
import tempfile
from typing import List, Dict, Any, Union, Optional, Tuple
import anthropic
from urllib.parse import urlparse
import time

logger = logging.getLogger("engagic")

# PDF API limits
MAX_PDF_API_SIZE = 32 * 1024 * 1024  # 32MB
MAX_PDF_API_PAGES = 100
MAX_REQUEST_SIZE = 32 * 1024 * 1024  # 32MB total request size

# Cost estimation (approximate)
TOKENS_PER_PAGE_TEXT = 2000  # Average text tokens per page
TOKENS_PER_PAGE_IMAGE = 1500  # Average image tokens per page


class PDFAPIProcessor:
    """Process PDFs using Claude's native PDF support API with full feature support"""
    
    def __init__(self, api_key: str, use_files_api: bool = False):
        self.api_key = api_key
        self.client = anthropic.Anthropic(api_key=api_key)
        self.use_files_api = use_files_api
        self._file_cache = {}  # Cache for Files API uploads
    
    def estimate_tokens(self, page_count: int) -> Dict[str, int]:
        """Estimate token usage for a PDF"""
        text_tokens = page_count * TOKENS_PER_PAGE_TEXT
        image_tokens = page_count * TOKENS_PER_PAGE_IMAGE
        total_tokens = text_tokens + image_tokens
        
        return {
            "text_tokens": text_tokens,
            "image_tokens": image_tokens,
            "total_tokens": total_tokens,
            "estimated_pages": page_count
        }
    
    def validate_pdf_for_api(self, url: str) -> Tuple[bool, Optional[str], Optional[int]]:
        """Check if PDF meets API requirements and get metadata"""
        try:
            # Make HEAD request to check size
            response = requests.head(url, timeout=10, headers={
                'User-Agent': 'Engagic-PDF-Validator/1.0'
            }, allow_redirects=True)
            
            content_length = response.headers.get('content-length')
            if content_length:
                size = int(content_length)
                if size > MAX_PDF_API_SIZE:
                    return False, f"PDF size {size:,} bytes exceeds API limit of {MAX_PDF_API_SIZE:,} bytes", size
                return True, None, size
            
            return True, None, None
                
        except requests.RequestException as e:
            logger.warning(f"Could not validate PDF size: {e}")
            return True, None, None  # Continue anyway - let the API handle it
    
    def _download_pdf(self, url: str) -> bytes:
        """Download PDF content with size validation"""
        try:
            response = requests.get(url, timeout=30, stream=True, headers={
                'User-Agent': 'Engagic-PDF-Processor/1.0'
            })
            response.raise_for_status()
            
            # Download with size checking
            pdf_content = b''
            downloaded = 0
            
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded > MAX_PDF_API_SIZE:
                        raise ValueError(f"PDF size exceeds maximum allowed size of {MAX_PDF_API_SIZE} bytes")
                    pdf_content += chunk
            
            return pdf_content
            
        except requests.RequestException as e:
            raise Exception(f"Failed to download PDF: {e}")
    
    def _upload_to_files_api(self, pdf_content: bytes, filename: str = "document.pdf") -> str:
        """Upload PDF to Files API and return file_id"""
        try:
            # Create a temporary file for upload
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
                tmp_file.write(pdf_content)
                tmp_file_path = tmp_file.name
            
            try:
                # Upload to Files API
                with open(tmp_file_path, "rb") as f:
                    file_upload = self.client.beta.files.upload(
                        file=(filename, f, "application/pdf")
                    )
                
                logger.info(f"Uploaded PDF to Files API: {file_upload.id}")
                return file_upload.id
                
            finally:
                # Clean up temp file
                os.unlink(tmp_file_path)
                
        except Exception as e:
            logger.error(f"Failed to upload to Files API: {e}")
            raise
    
    def _create_document_block_url(self, pdf_url: str) -> Dict[str, Any]:
        """Create document block for URL-based PDF"""
        return {
            "type": "document",
            "source": {
                "type": "url",
                "url": pdf_url
            }
        }
    
    def _create_document_block_base64(self, pdf_content: bytes) -> Dict[str, Any]:
        """Create document block for base64-encoded PDF"""
        pdf_base64 = base64.standard_b64encode(pdf_content).decode("utf-8")
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": pdf_base64
            }
        }
    
    def _create_document_block_file(self, file_id: str) -> Dict[str, Any]:
        """Create document block for Files API PDF"""
        return {
            "type": "document",
            "source": {
                "type": "file",
                "file_id": file_id
            }
        }
    
    def _create_document_block_with_cache(self, pdf_content: bytes) -> Dict[str, Any]:
        """Create document block with prompt caching enabled"""
        pdf_base64 = base64.standard_b64encode(pdf_content).decode("utf-8")
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": pdf_base64
            },
            "cache_control": {"type": "ephemeral"}
        }
    
    def _get_agenda_analysis_prompt(self) -> str:
        """Get the prompt for analyzing city council agendas"""
        return """Analyze this city council meeting agenda and provide a comprehensive summary that covers:

**Key Agenda Items:**
- List all major topics, proposals, and issues being discussed
- Include any public hearings, votes, or decisions
- Note all budget items, contracts, or financial matters
- Identify any zoning, development, or land use items

**Important Details:**
- Specific addresses for any property-related items
- Exact dollar amounts for financial items (contracts, budgets, grants)
- Ordinance/resolution numbers and titles
- Names of key people, organizations, or businesses mentioned
- Important dates, deadlines, or timelines
- Any policy changes or new regulations

**Public Participation:**
- Public comment opportunities and procedures
- How citizens can participate or provide input
- Any items requiring community feedback
- Contact information for follow-up

**Meeting Logistics:**
- Date, time, and location of the meeting
- Virtual participation options if available
- How to access meeting materials or recordings

**Action Items:**
- What decisions will be made at this meeting
- Items that are informational vs requiring a vote
- Any items being postponed or tabled

Format your response with clear sections and bullet points. Be thorough but concise.
Focus on information that would be most relevant to citizens wanting to understand and potentially participate in local government.
If there are supporting documents or attachments mentioned, note what additional information they contain."""
    
    def process_single_pdf_url(self, pdf_url: str, use_cache: bool = False) -> str:
        """Process a single PDF using URL-based approach"""
        logger.info(f"Processing PDF via URL API: {pdf_url[:80]}...")
        
        # Validate PDF
        valid, error_msg, size = self.validate_pdf_for_api(pdf_url)
        if not valid:
            raise ValueError(error_msg)
        
        try:
            # Build content blocks
            content_blocks = [
                self._create_document_block_url(pdf_url),
                {
                    "type": "text",
                    "text": self._get_agenda_analysis_prompt()
                }
            ]
            
            # Add model selection based on PDF complexity
            model = "claude-3-5-sonnet-20241022"  # Default model
            
            # Use newer models if available and PDF is complex
            if size and size > 10 * 1024 * 1024:  # >10MB PDFs might be complex
                model = "claude-3-5-sonnet-20241022"  # Could upgrade to claude-opus-4 if needed
            
            response = self.client.messages.create(
                model=model,
                max_tokens=4000,
                messages=[{
                    "role": "user",
                    "content": content_blocks
                }]
            )
            
            summary = response.content[0].text
            logger.info("Successfully processed PDF via URL API")
            return summary
            
        except anthropic.APIError as e:
            error_str = str(e)
            if "file_size_exceeded" in error_str:
                raise ValueError(f"PDF exceeds API size limit: {e}")
            elif "page_limit_exceeded" in error_str:
                raise ValueError(f"PDF exceeds API page limit of {MAX_PDF_API_PAGES} pages: {e}")
            elif "invalid_document" in error_str:
                raise ValueError(f"Invalid PDF document: {e}")
            else:
                raise Exception(f"API error processing PDF: {e}")
        except Exception as e:
            logger.error(f"Failed to process PDF via API: {e}")
            raise
    
    def process_single_pdf_base64(self, pdf_url: str, use_cache: bool = True) -> str:
        """Process a single PDF by downloading and using base64 encoding"""
        logger.info(f"Processing PDF via base64 API: {pdf_url[:80]}...")
        
        # Download PDF
        pdf_content = self._download_pdf(pdf_url)
        logger.info(f"Downloaded PDF: {len(pdf_content):,} bytes")
        
        try:
            # Build content blocks with or without caching
            if use_cache:
                document_block = self._create_document_block_with_cache(pdf_content)
            else:
                document_block = self._create_document_block_base64(pdf_content)
            
            content_blocks = [
                document_block,
                {
                    "type": "text",
                    "text": self._get_agenda_analysis_prompt()
                }
            ]
            
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                messages=[{
                    "role": "user",
                    "content": content_blocks
                }]
            )
            
            summary = response.content[0].text
            logger.info("Successfully processed PDF via base64 API")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to process PDF via base64 API: {e}")
            raise
    
    def process_single_pdf_files_api(self, pdf_url: str) -> str:
        """Process a single PDF using Files API for reusability"""
        logger.info(f"Processing PDF via Files API: {pdf_url[:80]}...")
        
        # Check if we already uploaded this URL
        if pdf_url in self._file_cache:
            file_id = self._file_cache[pdf_url]
            logger.info(f"Using cached file upload: {file_id}")
        else:
            # Download and upload PDF
            pdf_content = self._download_pdf(pdf_url)
            file_id = self._upload_to_files_api(pdf_content, f"agenda_{len(self._file_cache)}.pdf")
            self._file_cache[pdf_url] = file_id
        
        try:
            content_blocks = [
                self._create_document_block_file(file_id),
                {
                    "type": "text",
                    "text": self._get_agenda_analysis_prompt()
                }
            ]
            
            response = self.client.beta.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                messages=[{
                    "role": "user",
                    "content": content_blocks
                }],
                betas=["files-api-2025-04-14"]
            )
            
            summary = response.content[0].text
            logger.info("Successfully processed PDF via Files API")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to process PDF via Files API: {e}")
            raise
    
    def process_multiple_pdfs(self, pdf_urls: List[str], method: str = "url") -> str:
        """Process multiple PDFs and combine summaries"""
        logger.info(f"Processing {len(pdf_urls)} PDFs via {method} method")
        
        summaries = []
        
        for i, pdf_url in enumerate(pdf_urls, 1):
            try:
                logger.info(f"Processing PDF {i}/{len(pdf_urls)}")
                
                if method == "base64":
                    summary = self.process_single_pdf_base64(pdf_url, use_cache=True)
                elif method == "files":
                    summary = self.process_single_pdf_files_api(pdf_url)
                else:  # Default to URL
                    summary = self.process_single_pdf_url(pdf_url)
                
                summaries.append(f"=== DOCUMENT {i} ===\n{summary}\n")
                
                # Rate limiting between requests
                if i < len(pdf_urls):
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"Failed to process PDF {i}: {e}")
                summaries.append(f"=== DOCUMENT {i} ===\n[Failed to process: {str(e)}]\n")
        
        if not any("Failed to process" not in s for s in summaries):
            raise Exception("All PDFs failed to process")
            
        return "\n".join(summaries)
    
    def process_batch(self, pdf_requests: List[Dict[str, Any]]) -> str:
        """Process PDFs using batch API for high-volume workflows"""
        logger.info(f"Processing {len(pdf_requests)} PDFs via batch API")
        
        # Prepare batch requests
        batch_requests = []
        for i, req in enumerate(pdf_requests):
            pdf_url = req.get("url")
            custom_prompt = req.get("prompt", self._get_agenda_analysis_prompt())
            
            batch_requests.append({
                "custom_id": f"pdf_{i}",
                "params": {
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 4000,
                    "messages": [{
                        "role": "user",
                        "content": [
                            self._create_document_block_url(pdf_url),
                            {
                                "type": "text",
                                "text": custom_prompt
                            }
                        ]
                    }]
                }
            })
        
        try:
            # Create batch job
            batch = self.client.beta.messages.batches.create(requests=batch_requests)
            logger.info(f"Created batch job: {batch.id}")
            
            # Note: In production, you would poll for batch completion
            # For now, return batch ID for tracking
            return f"Batch job created: {batch.id}. Check status separately."
            
        except Exception as e:
            logger.error(f"Failed to create batch job: {e}")
            raise
    
    def process(self, url: Union[str, List[str]], method: str = "url") -> str:
        """Main entry point - process single or multiple PDFs with specified method"""
        if isinstance(url, list):
            return self.process_multiple_pdfs(url, method)
        else:
            if method == "base64":
                return self.process_single_pdf_base64(url)
            elif method == "files" or self.use_files_api:
                return self.process_single_pdf_files_api(url)
            else:
                return self.process_single_pdf_url(url)