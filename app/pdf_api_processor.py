import logging
import requests
import base64
import os
import tempfile
from typing import List, Dict, Any, Union, Optional, Tuple
import anthropic
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading
from collections import defaultdict
import json
from pathlib import Path
from anthropic_rate_limiter import AnthropicRateLimiter

logger = logging.getLogger("engagic")

# PDF API limits
MAX_PDF_API_SIZE = 32 * 1024 * 1024  # 32MB
MAX_PDF_API_PAGES = 100
MAX_REQUEST_SIZE = 32 * 1024 * 1024  # 32MB total request size

# Cost estimation (approximate)
TOKENS_PER_PAGE_TEXT = 2000  # Average text tokens per page
TOKENS_PER_PAGE_IMAGE = 1500  # Average image tokens per page

# Batch processing constants
BATCH_MAX_REQUESTS = 100000  # Max requests per batch
BATCH_MAX_SIZE_MB = 256  # Max batch size in MB
BATCH_POLL_INTERVAL = 10  # Seconds between status checks
BATCH_MAX_WAIT_TIME = 86400  # 24 hours max wait
BATCH_RESULT_EXPIRY = 29 * 24 * 3600  # 29 days in seconds

# Model complexity thresholds
MODEL_COMPLEXITY_THRESHOLDS = {
    "simple": {"pages": 10, "size_mb": 5, "model": "claude-3-5-haiku-20241022"},
    "moderate": {"pages": 50, "size_mb": 20, "model": "claude-3-5-sonnet-20241022"},
    "complex": {"pages": 100, "size_mb": 32, "model": "claude-sonnet-4-20250514"},
    "extreme": {"pages": 100, "size_mb": 32, "model": "claude-opus-4-20250514"},
}


class BatchStatus(Enum):
    """Batch processing status"""

    CREATED = "created"
    IN_PROGRESS = "in_progress"
    ENDED = "ended"
    EXPIRED = "expired"
    CANCELED = "canceled"


class ResultType(Enum):
    """Batch result types"""

    SUCCEEDED = "succeeded"
    ERRORED = "errored"
    CANCELED = "canceled"
    EXPIRED = "expired"


@dataclass
class BatchResult:
    """Structured batch result"""

    custom_id: str
    result_type: ResultType
    message: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, int]] = None


@dataclass
class TokenUsage:
    """Track token usage and costs"""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    estimated_cost: float = 0.0
    model: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


class CostTracker:
    """Track API costs and token usage"""

    def __init__(self):
        self.usage_history: List[TokenUsage] = []
        self.batch_savings: float = 0.0
        self.cache_savings: float = 0.0
        self._lock = threading.Lock()

    def add_usage(self, usage: Dict[str, int], model: str, is_batch: bool = False):
        """Add token usage record"""
        with self._lock:
            # Calculate cost based on model and batch discount
            base_cost = self._calculate_cost(usage, model)
            if is_batch:
                actual_cost = base_cost * 0.5  # 50% batch discount
                self.batch_savings += base_cost - actual_cost
            else:
                actual_cost = base_cost

            # Track cache savings
            if usage.get("cache_read_input_tokens", 0) > 0:
                cache_discount = self._calculate_cache_savings(usage, model)
                self.cache_savings += cache_discount
                actual_cost -= cache_discount

            record = TokenUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cached_input_tokens=usage.get("cache_read_input_tokens", 0),
                estimated_cost=actual_cost,
                model=model,
            )
            self.usage_history.append(record)

    def _calculate_cost(self, usage: Dict[str, int], model: str) -> float:
        """Calculate base cost for token usage"""
        # Pricing per million tokens (approximate)
        pricing = {
            "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
            "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
            "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
            "claude-3-5-haiku-20241022": {"input": 0.8, "output": 4.0},
        }

        rates = pricing.get(model, {"input": 3.0, "output": 15.0})
        input_cost = (usage.get("input_tokens", 0) / 1_000_000) * rates["input"]
        output_cost = (usage.get("output_tokens", 0) / 1_000_000) * rates["output"]

        return input_cost + output_cost

    def _calculate_cache_savings(self, usage: Dict[str, int], model: str) -> float:
        """Calculate savings from cache hits"""
        cached_tokens = usage.get("cache_read_input_tokens", 0)
        if cached_tokens == 0:
            return 0.0

        # Cache provides 90% discount on input tokens
        pricing = {
            "claude-opus-4-20250514": 15.0,
            "claude-sonnet-4-20250514": 3.0,
            "claude-3-5-sonnet-20241022": 3.0,
            "claude-3-5-haiku-20241022": 0.8,
        }

        rate = pricing.get(model, 3.0)
        return (cached_tokens / 1_000_000) * rate * 0.9

    def get_summary(self) -> Dict[str, Any]:
        """Get cost tracking summary"""
        with self._lock:
            total_input = sum(u.input_tokens for u in self.usage_history)
            total_output = sum(u.output_tokens for u in self.usage_history)
            total_cached = sum(u.cached_input_tokens for u in self.usage_history)
            total_cost = sum(u.estimated_cost for u in self.usage_history)

            return {
                "total_requests": len(self.usage_history),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_cached_tokens": total_cached,
                "total_estimated_cost": round(total_cost, 2),
                "batch_savings": round(self.batch_savings, 2),
                "cache_savings": round(self.cache_savings, 2),
                "total_savings": round(self.batch_savings + self.cache_savings, 2),
                "cache_hit_rate": round(total_cached / total_input * 100, 1)
                if total_input > 0
                else 0,
            }


class PDFAPIProcessor:
    """Process PDFs using Claude's native PDF support API with full feature support"""

    def __init__(self, api_key: str, use_files_api: bool = False):
        self.api_key = api_key
        self.client = anthropic.Anthropic(api_key=api_key)
        self.use_files_api = use_files_api
        self._file_cache = {}  # Cache for Files API uploads
        self._batch_cache = {}  # Cache for batch job tracking
        self.cost_tracker = CostTracker()
        self._prompt_cache = {}  # Cache for prompts to maximize cache hits
        self.rate_limiter = AnthropicRateLimiter()  # Add intelligent rate limiting

    def estimate_tokens(self, page_count: int) -> Dict[str, int]:
        """Estimate token usage for a PDF"""
        text_tokens = page_count * TOKENS_PER_PAGE_TEXT
        image_tokens = page_count * TOKENS_PER_PAGE_IMAGE
        total_tokens = text_tokens + image_tokens

        return {
            "text_tokens": text_tokens,
            "image_tokens": image_tokens,
            "total_tokens": total_tokens,
            "estimated_pages": page_count,
        }

    def select_optimal_model(self, pdf_metadata: Dict[str, Any]) -> str:
        """Select optimal model based on PDF complexity"""
        pages = pdf_metadata.get("pages", 0)
        size_mb = pdf_metadata.get("size_bytes", 0) / (1024 * 1024)
        has_images = pdf_metadata.get("has_images", False)
        has_tables = pdf_metadata.get("has_tables", False)

        # Determine complexity level
        if (
            pages <= MODEL_COMPLEXITY_THRESHOLDS["simple"]["pages"]
            and size_mb <= MODEL_COMPLEXITY_THRESHOLDS["simple"]["size_mb"]
        ):
            if not has_images and not has_tables:
                return MODEL_COMPLEXITY_THRESHOLDS["simple"]["model"]

        if (
            pages <= MODEL_COMPLEXITY_THRESHOLDS["moderate"]["pages"]
            and size_mb <= MODEL_COMPLEXITY_THRESHOLDS["moderate"]["size_mb"]
        ):
            return MODEL_COMPLEXITY_THRESHOLDS["moderate"]["model"]

        if has_images or has_tables or pages > 75:
            # Use more capable models for complex documents
            if size_mb > 25 or pages > 90:
                return MODEL_COMPLEXITY_THRESHOLDS["extreme"]["model"]
            return MODEL_COMPLEXITY_THRESHOLDS["complex"]["model"]

        return MODEL_COMPLEXITY_THRESHOLDS["moderate"]["model"]

    def analyze_pdf_complexity(self, pdf_content: bytes) -> Dict[str, Any]:
        """Analyze PDF to determine complexity for model selection"""
        # This is a simplified analysis - in production you'd use a PDF library
        size_bytes = len(pdf_content)

        # Basic heuristics
        has_images = b"/Image" in pdf_content or b"/XObject" in pdf_content
        has_tables = b"/Table" in pdf_content or b"<table" in pdf_content.lower()

        # Estimate pages (very rough)
        page_count = pdf_content.count(b"/Page") // 2  # Rough estimate
        if page_count < 1:
            page_count = max(1, size_bytes // 50000)  # Fallback estimate

        return {
            "size_bytes": size_bytes,
            "pages": min(page_count, MAX_PDF_API_PAGES),
            "has_images": has_images,
            "has_tables": has_tables,
        }

    def validate_pdf_for_api(
        self, url: str
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """Check if PDF meets API requirements and get metadata"""
        try:
            # Make HEAD request to check size
            response = requests.head(
                url,
                timeout=10,
                headers={"User-Agent": "Engagic-PDF-Validator/1.0"},
                allow_redirects=True,
            )

            content_length = response.headers.get("content-length")
            if content_length:
                size = int(content_length)
                if size > MAX_PDF_API_SIZE:
                    return (
                        False,
                        f"PDF size {size:,} bytes exceeds API limit of {MAX_PDF_API_SIZE:,} bytes",
                        size,
                    )
                return True, None, size

            return True, None, None

        except requests.RequestException as e:
            logger.warning(f"Could not validate PDF size: {e}")
            return True, None, None  # Continue anyway - let the API handle it

    def _download_pdf(self, url: str) -> bytes:
        """Download PDF content with size validation"""
        try:
            response = requests.get(
                url,
                timeout=30,
                stream=True,
                headers={"User-Agent": "Engagic-PDF-Processor/1.0"},
            )
            response.raise_for_status()

            # Download with size checking
            pdf_content = b""
            downloaded = 0

            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded > MAX_PDF_API_SIZE:
                        raise ValueError(
                            f"PDF size exceeds maximum allowed size of {MAX_PDF_API_SIZE} bytes"
                        )
                    pdf_content += chunk

            return pdf_content

        except requests.RequestException as e:
            raise Exception(f"Failed to download PDF: {e}")

    def _upload_to_files_api(
        self, pdf_content: bytes, filename: str = "document.pdf"
    ) -> str:
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
        return {"type": "document", "source": {"type": "url", "url": pdf_url}}

    def _create_document_block_base64(self, pdf_content: bytes) -> Dict[str, Any]:
        """Create document block for base64-encoded PDF"""
        pdf_base64 = base64.standard_b64encode(pdf_content).decode("utf-8")
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": pdf_base64,
            },
        }

    def _create_document_block_file(self, file_id: str) -> Dict[str, Any]:
        """Create document block for Files API PDF"""
        return {"type": "document", "source": {"type": "file", "file_id": file_id}}

    def _create_document_block_with_cache(self, pdf_content: bytes) -> Dict[str, Any]:
        """Create document block with prompt caching enabled"""
        pdf_base64 = base64.standard_b64encode(pdf_content).decode("utf-8")
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": pdf_base64,
            },
            "cache_control": {"type": "ephemeral"},
        }

    def _get_agenda_analysis_prompt(self, use_caching: bool = True) -> Dict[str, Any]:
        """Get the prompt for analyzing city council agendas with optional caching"""
        prompt_text = """Analyze this city council meeting agenda and provide a comprehensive summary that covers:

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

        if use_caching:
            # Return as a content block with cache control
            return {
                "type": "text",
                "text": prompt_text,
                "cache_control": {"type": "ephemeral"},
            }
        else:
            return {"type": "text", "text": prompt_text}

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
                self._get_agenda_analysis_prompt(use_caching=use_cache),
            ]

            # Intelligent model selection based on PDF complexity
            pdf_metadata = {
                "size_bytes": size or 0,
                "pages": min((size or 0) // 50000, MAX_PDF_API_PAGES) if size else 10,
            }
            model = self.select_optimal_model(pdf_metadata)
            logger.info(f"Selected model {model} for PDF processing")

            # Make API call with rate limiting
            response = self.rate_limiter.wrap_request(
                self.client.messages.create,
                model=model,
                max_tokens=4000,
                messages=[{"role": "user", "content": content_blocks}],
            )

            summary = response.content[0].text

            # Track token usage
            if hasattr(response, "usage") and response.usage:
                self.cost_tracker.add_usage(response.usage.model_dump(), model)

            logger.info(f"Successfully processed PDF via URL API using {model}")
            return summary

        except anthropic.APIError as e:
            error_str = str(e)
            if "file_size_exceeded" in error_str:
                raise ValueError(f"PDF exceeds API size limit: {e}")
            elif "page_limit_exceeded" in error_str:
                raise ValueError(
                    f"PDF exceeds API page limit of {MAX_PDF_API_PAGES} pages: {e}"
                )
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

            # Analyze PDF complexity for model selection
            pdf_metadata = self.analyze_pdf_complexity(pdf_content)
            model = self.select_optimal_model(pdf_metadata)
            logger.info(f"Selected model {model} for {len(pdf_content):,} byte PDF")

            content_blocks = [
                document_block,
                self._get_agenda_analysis_prompt(use_caching=use_cache),
            ]

            # Make API call with rate limiting
            response = self.rate_limiter.wrap_request(
                self.client.messages.create,
                model=model,
                max_tokens=4000,
                messages=[{"role": "user", "content": content_blocks}],
            )

            summary = response.content[0].text

            # Track token usage
            if hasattr(response, "usage") and response.usage:
                self.cost_tracker.add_usage(response.usage.model_dump(), model)

            logger.info(f"Successfully processed PDF via base64 API using {model}")
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
            file_id = self._upload_to_files_api(
                pdf_content, f"agenda_{len(self._file_cache)}.pdf"
            )
            self._file_cache[pdf_url] = file_id

        try:
            # Get PDF metadata for model selection
            pdf_content = self._download_pdf(pdf_url)
            pdf_metadata = self.analyze_pdf_complexity(pdf_content)
            model = self.select_optimal_model(pdf_metadata)

            content_blocks = [
                self._create_document_block_file(file_id),
                self._get_agenda_analysis_prompt(use_caching=True),
            ]

            # Make API call with rate limiting
            response = self.rate_limiter.wrap_request(
                self.client.beta.messages.create,
                model=model,
                max_tokens=4000,
                messages=[{"role": "user", "content": content_blocks}],
                betas=["files-api-2025-04-14"],
            )

            summary = response.content[0].text

            # Track token usage
            if hasattr(response, "usage") and response.usage:
                self.cost_tracker.add_usage(response.usage.model_dump(), model)

            logger.info(f"Successfully processed PDF via Files API using {model}")
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
                summaries.append(
                    f"=== DOCUMENT {i} ===\n[Failed to process: {str(e)}]\n"
                )

        if not any("Failed to process" not in s for s in summaries):
            raise Exception("All PDFs failed to process")

        return "\n".join(summaries)

    def submit_batch(self, pdf_requests: List[Dict[str, Any]]) -> str:
        """Submit a batch without waiting for results"""
        logger.info(f"Submitting batch with {len(pdf_requests)} PDFs")
        
        # Build batch requests
        batch_requests = []
        for req in pdf_requests:
            pdf_url = req.get("url")
            custom_id = req.get("custom_id", f"pdf_{int(time.time() * 1000)}")
            prompt = req.get("prompt") or self._get_agenda_analysis_prompt(use_caching=True)
            model = req.get("model", "claude-3-5-sonnet-20241022")
            
            # Create document block
            content = [
                self._create_document_block_url(pdf_url),
                prompt
            ]
            
            batch_request = {
                "custom_id": custom_id,
                "params": {
                    "model": model,
                    "max_tokens": 4000,
                    "messages": [{"role": "user", "content": content}]
                }
            }
            batch_requests.append(batch_request)
        
        try:
            # Submit batch with rate limiting
            batch = self.rate_limiter.wrap_request(
                self.client.messages.batches.create,
                requests=batch_requests
            )
            logger.info(f"Batch submitted with ID: {batch.id}")
            
            # Cache batch info
            self._batch_cache[batch.id] = {
                "id": batch.id,
                "status": batch.processing_status,
                "created_at": datetime.now(),
                "request_count": len(batch_requests),
                "custom_ids": [r["custom_id"] for r in batch_requests]
            }
            
            return batch.id
            
        except Exception as e:
            logger.error(f"Failed to submit batch: {e}")
            raise
    
    def get_batch_results(self, batch_id: str) -> List[Dict[str, Any]]:
        """Get results from a completed batch"""
        try:
            results = []
            
            # Stream results efficiently
            for result in self.client.messages.batches.results(batch_id):
                result_dict = {
                    "custom_id": result.custom_id,
                    "status": result.result.type
                }
                
                if result.result.type == "succeeded":
                    # Extract message content
                    message = result.result.message
                    content = message.content[0].text if message.content else ""
                    result_dict["summary"] = content
                    result_dict["usage"] = {
                        "input_tokens": message.usage.input_tokens,
                        "output_tokens": message.usage.output_tokens
                    }
                elif result.result.type == "errored":
                    result_dict["error"] = result.result.error
                
                results.append(result_dict)
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get batch results: {e}")
            raise
    
    def process_batch(
        self,
        pdf_requests: List[Dict[str, Any]],
        wait_for_completion: bool = True,
        use_prompt_caching: bool = True,
    ) -> Union[str, List[BatchResult]]:
        """Process PDFs using batch API with full support for polling and result streaming"""
        logger.info(f"Processing {len(pdf_requests)} PDFs via batch API")

        # Prepare batch requests with intelligent model selection and caching
        batch_requests = []
        model_distribution = defaultdict(int)

        for i, req in enumerate(pdf_requests):
            pdf_url = req.get("url")
            custom_prompt = req.get("prompt")

            # Analyze PDF for model selection
            try:
                valid, error_msg, size = self.validate_pdf_for_api(pdf_url)
                if not valid:
                    logger.warning(f"Skipping invalid PDF {pdf_url}: {error_msg}")
                    continue

                pdf_metadata = {
                    "size_bytes": size or 0,
                    "pages": min((size or 0) // 50000, MAX_PDF_API_PAGES)
                    if size
                    else 10,
                }
                model = req.get("model") or self.select_optimal_model(pdf_metadata)
                model_distribution[model] += 1

            except Exception as e:
                logger.warning(f"Error analyzing PDF {pdf_url}: {e}")
                model = "claude-3-5-sonnet-20241022"  # Default fallback

            # Build content blocks with caching
            content_blocks = [self._create_document_block_url(pdf_url)]

            if custom_prompt:
                prompt_block = {"type": "text", "text": custom_prompt}
                if use_prompt_caching:
                    prompt_block["cache_control"] = {"type": "ephemeral"}
                content_blocks.append(prompt_block)
            else:
                content_blocks.append(
                    self._get_agenda_analysis_prompt(use_caching=use_prompt_caching)
                )

            batch_requests.append(
                {
                    "custom_id": req.get("custom_id", f"pdf_{i}"),
                    "params": {
                        "model": model,
                        "max_tokens": req.get("max_tokens", 4000),
                        "messages": [{"role": "user", "content": content_blocks}],
                    },
                }
            )

        if not batch_requests:
            raise ValueError("No valid PDFs to process in batch")

        logger.info(f"Model distribution for batch: {dict(model_distribution)}")

        try:
            # Create batch job with rate limiting
            batch = self.rate_limiter.wrap_request(
                self.client.beta.messages.batches.create,
                requests=batch_requests
            )
            logger.info(
                f"Created batch job: {batch.id} with {len(batch_requests)} requests"
            )

            # Store batch info for tracking
            self._batch_cache[batch.id] = {
                "created_at": datetime.now(),
                "request_count": len(batch_requests),
                "status": BatchStatus.CREATED,
                "custom_ids": [req["custom_id"] for req in batch_requests],
            }

            if wait_for_completion:
                # Poll and wait for results
                return self.poll_batch_until_complete(batch.id)
            else:
                # Return batch ID for async processing
                return batch.id

        except Exception as e:
            logger.error(f"Failed to create batch job: {e}")
            raise

    def poll_batch_until_complete(
        self, batch_id: str, timeout: int = BATCH_MAX_WAIT_TIME
    ) -> List[BatchResult]:
        """Poll batch status until completion and return results"""
        logger.info(f"Polling batch {batch_id} until completion (timeout: {timeout}s)")

        start_time = time.time()
        last_status = None

        while time.time() - start_time < timeout:
            try:
                # Get batch status
                batch = self.client.beta.messages.batches.retrieve(batch_id)

                if batch.processing_status != last_status:
                    logger.info(f"Batch {batch_id} status: {batch.processing_status}")
                    logger.info(f"Progress: {batch.request_counts}")
                    last_status = batch.processing_status

                # Update cache
                if batch_id in self._batch_cache:
                    self._batch_cache[batch_id]["status"] = BatchStatus(
                        batch.processing_status
                    )
                    self._batch_cache[batch_id]["request_counts"] = batch.request_counts

                if batch.processing_status == "ended":
                    logger.info(
                        f"Batch {batch_id} completed after {time.time() - start_time:.1f}s"
                    )
                    # Process results
                    return self.process_batch_results(batch_id)

                elif batch.processing_status in ["expired", "canceled"]:
                    raise Exception(f"Batch {batch_id} {batch.processing_status}")

                # Wait before next poll
                time.sleep(BATCH_POLL_INTERVAL)

            except Exception as e:
                logger.error(f"Error polling batch {batch_id}: {e}")
                raise

        raise TimeoutError(
            f"Batch {batch_id} did not complete within {timeout} seconds"
        )

    def process_batch_results(self, batch_id: str) -> List[BatchResult]:
        """Stream and process batch results with comprehensive error handling"""
        logger.info(f"Processing results for batch {batch_id}")

        results = []
        success_count = 0
        error_count = 0
        total_cost = 0.0

        try:
            # Stream results efficiently
            for result in self.client.beta.messages.batches.results(batch_id):
                try:
                    # Parse result based on type
                    result_type = ResultType(result.result.type)

                    if result_type == ResultType.SUCCEEDED:
                        message = result.result.message
                        usage = (
                            message.usage.model_dump()
                            if hasattr(message, "usage")
                            else None
                        )

                        # Track token usage with batch discount
                        if usage:
                            model = (
                                message.model
                                if hasattr(message, "model")
                                else "claude-3-5-sonnet-20241022"
                            )
                            self.cost_tracker.add_usage(usage, model, is_batch=True)

                        batch_result = BatchResult(
                            custom_id=result.custom_id,
                            result_type=result_type,
                            message=message.model_dump()
                            if hasattr(message, "model_dump")
                            else dict(message),
                            usage=usage,
                        )
                        success_count += 1

                    elif result_type == ResultType.ERRORED:
                        error = result.result.error
                        logger.error(f"Request {result.custom_id} failed: {error}")

                        batch_result = BatchResult(
                            custom_id=result.custom_id,
                            result_type=result_type,
                            error=error.model_dump()
                            if hasattr(error, "model_dump")
                            else dict(error),
                        )
                        error_count += 1

                    else:
                        # CANCELED or EXPIRED
                        batch_result = BatchResult(
                            custom_id=result.custom_id, result_type=result_type
                        )
                        error_count += 1

                    results.append(batch_result)

                except Exception as e:
                    logger.error(f"Error processing result {result.custom_id}: {e}")
                    results.append(
                        BatchResult(
                            custom_id=result.custom_id,
                            result_type=ResultType.ERRORED,
                            error={"type": "processing_error", "message": str(e)},
                        )
                    )
                    error_count += 1

            # Log summary
            cost_summary = self.cost_tracker.get_summary()
            logger.info(
                f"Batch {batch_id} complete: {success_count} succeeded, {error_count} failed"
            )
            logger.info(f"Cost tracking: {cost_summary}")

            # Update batch cache
            if batch_id in self._batch_cache:
                self._batch_cache[batch_id]["completed_at"] = datetime.now()
                self._batch_cache[batch_id]["success_count"] = success_count
                self._batch_cache[batch_id]["error_count"] = error_count

            return results

        except Exception as e:
            logger.error(f"Failed to process batch results: {e}")
            raise

    def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        """Get current status of a batch job"""
        try:
            batch = self.client.beta.messages.batches.retrieve(batch_id)

            status = {
                "id": batch.id,
                "status": batch.processing_status,
                "created_at": batch.created_at,
                "expires_at": batch.expires_at,
                "request_counts": batch.request_counts,
                "results_available": batch.processing_status == "ended",
            }

            # Add cached info if available
            if batch_id in self._batch_cache:
                status.update(self._batch_cache[batch_id])

            return status

        except Exception as e:
            logger.error(f"Failed to get batch status: {e}")
            raise

    def cancel_batch(self, batch_id: str) -> bool:
        """Cancel a batch job"""
        try:
            self.client.beta.messages.batches.cancel(batch_id)
            logger.info(f"Cancelled batch {batch_id}")

            if batch_id in self._batch_cache:
                self._batch_cache[batch_id]["status"] = BatchStatus.CANCELED
                self._batch_cache[batch_id]["canceled_at"] = datetime.now()

            return True

        except Exception as e:
            logger.error(f"Failed to cancel batch: {e}")
            return False
    
    def smart_batch_pdfs(self, pdf_urls: List[str], max_wait_time: int = 3600) -> Dict[str, str]:
        """Process PDFs using batching with smart fallback for urgent needs"""
        results = {}
        
        # Check if we should use batching
        use_batch = len(pdf_urls) > 3  # Batch if more than 3 PDFs
        
        if use_batch:
            logger.info(f"Using batch processing for {len(pdf_urls)} PDFs")
            
            # Prepare batch requests
            batch_requests = [
                {"url": url, "custom_id": f"pdf_{i}"} 
                for i, url in enumerate(pdf_urls)
            ]
            
            try:
                # Submit batch
                batch_id = self.submit_batch(batch_requests)
                
                # Wait for batch with timeout
                start_time = time.time()
                while time.time() - start_time < max_wait_time:
                    status = self.get_batch_status(batch_id)
                    
                    if status["processing_status"] == "ended":
                        # Get results
                        batch_results = self.get_batch_results(batch_id)
                        
                        # Map results back to URLs
                        for i, url in enumerate(pdf_urls):
                            custom_id = f"pdf_{i}"
                            result = next((r for r in batch_results if r["custom_id"] == custom_id), None)
                            
                            if result and result["status"] == "succeeded":
                                results[url] = result["summary"]
                            else:
                                # Fallback to direct processing for failed items
                                logger.warning(f"Batch processing failed for {url}, using direct API")
                                try:
                                    results[url] = self.process_single_pdf_url(url)
                                except:
                                    results[url] = "Failed to process PDF"
                        
                        return results
                    
                    # Check periodically
                    time.sleep(30)
                
                # Timeout - cancel batch and fallback
                logger.warning(f"Batch {batch_id} timed out after {max_wait_time}s")
                self.cancel_batch(batch_id)
                
            except Exception as e:
                logger.error(f"Batch processing failed: {e}")
        
        # Fallback to direct processing
        logger.info("Using direct API processing")
        for url in pdf_urls:
            try:
                results[url] = self.process_single_pdf_url(url)
            except Exception as e:
                logger.error(f"Failed to process {url}: {e}")
                results[url] = f"Error: {str(e)}"
        
        return results

    def process_single_pdf_chunked(self, pdf_url: str) -> str:
        """Process large PDF by chunking it into smaller pieces"""
        from pdf_chunker import PDFChunker
        
        logger.info(f"Processing large PDF via chunking: {pdf_url[:80]}...")
        
        chunker = PDFChunker()
        try:
            # Download the PDF
            pdf_content = chunker.download_pdf(pdf_url)
            
            # Split into chunks
            chunks = chunker.split_pdf_by_size(pdf_content)
            logger.info(f"Split PDF into {len(chunks)} chunks")
            
            # Process each chunk
            chunk_summaries = []
            for chunk in chunks:
                logger.info(f"Processing chunk {chunk.chunk_number + 1}/{chunk.total_chunks} "
                          f"(pages {chunk.start_page + 1}-{chunk.end_page + 1}, {chunk.size_bytes:,} bytes)")
                
                # Create document block for chunk
                document_block = self._create_document_block_base64(chunk.content)
                
                # Add chunk context to prompt if multiple chunks
                prompt_blocks = [document_block]
                
                if chunk.total_chunks > 1:
                    chunk_prompt = chunker.create_chunk_summary_prompt(chunk)
                    prompt_blocks.append({"type": "text", "text": chunk_prompt})
                
                prompt_blocks.append(self._get_agenda_analysis_prompt(use_caching=True))
                
                # Process chunk with rate limiting
                response = self.rate_limiter.wrap_request(
                    self.client.messages.create,
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=4000,
                    messages=[{"role": "user", "content": prompt_blocks}],
                )
                
                chunk_summaries.append(response.content[0].text)
                
                # Track usage
                if hasattr(response, "usage") and response.usage:
                    self.cost_tracker.add_usage(response.usage.model_dump(), "claude-3-5-sonnet-20241022")
            
            # Combine summaries
            final_summary = chunker.combine_chunk_summaries(chunk_summaries, chunks)
            logger.info(f"Successfully processed PDF via chunking ({len(chunks)} chunks)")
            return final_summary
            
        except Exception as e:
            logger.error(f"Failed to process PDF via chunking: {e}")
            raise

    def process(self, url: Union[str, List[str]], method: str = "url") -> str:
        """Main entry point - process single or multiple PDFs with specified method"""
        if isinstance(url, list):
            return self.process_multiple_pdfs(url, method)
        else:
            if method == "chunked":
                return self.process_single_pdf_chunked(url)
            elif method == "base64":
                return self.process_single_pdf_base64(url)
            elif method == "files" or self.use_files_api:
                return self.process_single_pdf_files_api(url)
            else:
                return self.process_single_pdf_url(url)


class BatchAccumulator:
    """Accumulate requests for efficient batch processing"""

    def __init__(
        self,
        processor: PDFAPIProcessor,
        batch_size: int = 100,
        wait_time: int = 300,  # 5 minutes
        auto_submit: bool = True,
    ):
        self.processor = processor
        self.batch_size = batch_size
        self.wait_time = wait_time
        self.auto_submit = auto_submit

        self.pending_requests = []
        self.submitted_batches = {}
        self._lock = threading.Lock()
        self._last_add_time = None
        self._submit_timer = None

    def add_request(
        self, pdf_url: str, custom_id: str = None, prompt: str = None, model: str = None
    ) -> str:
        """Add a request to the accumulator"""
        with self._lock:
            request = {
                "url": pdf_url,
                "custom_id": custom_id
                or f"acc_{len(self.pending_requests)}_{int(time.time())}",
                "prompt": prompt,
                "model": model,
            }

            self.pending_requests.append(request)
            self._last_add_time = time.time()

            logger.info(
                f"Added request to accumulator: {request['custom_id']} (total: {len(self.pending_requests)})"
            )

            # Check if we should submit
            if len(self.pending_requests) >= self.batch_size:
                self._submit_batch("size_limit")
            elif self.auto_submit and not self._submit_timer:
                # Start timer for auto-submission
                self._start_submit_timer()

            return request["custom_id"]

    def _start_submit_timer(self):
        """Start timer for auto-submission"""
        if self._submit_timer:
            self._submit_timer.cancel()

        self._submit_timer = threading.Timer(
            self.wait_time, lambda: self._submit_batch("timeout")
        )
        self._submit_timer.start()

    def _submit_batch(self, reason: str):
        """Submit accumulated requests as a batch"""
        with self._lock:
            if not self.pending_requests:
                return

            # Cancel timer
            if self._submit_timer:
                self._submit_timer.cancel()
                self._submit_timer = None

            # Submit batch
            requests_to_submit = self.pending_requests[: self.batch_size]
            self.pending_requests = self.pending_requests[self.batch_size :]

            logger.info(
                f"Submitting batch of {len(requests_to_submit)} requests (reason: {reason})"
            )

            try:
                batch_id = self.processor.process_batch(
                    requests_to_submit,
                    wait_for_completion=False,
                    use_prompt_caching=True,
                )

                # Track submitted batch
                self.submitted_batches[batch_id] = {
                    "submitted_at": datetime.now(),
                    "request_count": len(requests_to_submit),
                    "custom_ids": [req["custom_id"] for req in requests_to_submit],
                    "reason": reason,
                }

                logger.info(f"Batch {batch_id} submitted successfully")

                # Start timer for remaining requests
                if self.pending_requests and self.auto_submit:
                    self._start_submit_timer()

            except Exception as e:
                logger.error(f"Failed to submit batch: {e}")
                # Re-add requests to pending
                self.pending_requests = requests_to_submit + self.pending_requests

    def force_submit(self):
        """Force submission of all pending requests"""
        self._submit_batch("forced")

    def get_results(self, custom_id: str, timeout: int = 3600) -> Optional[BatchResult]:
        """Get results for a specific request"""
        # Find which batch contains this request
        batch_id = None
        for bid, info in self.submitted_batches.items():
            if custom_id in info["custom_ids"]:
                batch_id = bid
                break

        if not batch_id:
            # Check if still pending
            with self._lock:
                if any(req["custom_id"] == custom_id for req in self.pending_requests):
                    logger.info(f"Request {custom_id} is still pending")
                    return None

            logger.error(f"Request {custom_id} not found")
            return None

        # Get batch results
        try:
            results = self.processor.poll_batch_until_complete(batch_id, timeout)

            # Find specific result
            for result in results:
                if result.custom_id == custom_id:
                    return result

            logger.error(f"Result for {custom_id} not found in batch {batch_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to get results for {custom_id}: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """Get accumulator status"""
        with self._lock:
            return {
                "pending_requests": len(self.pending_requests),
                "submitted_batches": len(self.submitted_batches),
                "total_submitted": sum(
                    info["request_count"] for info in self.submitted_batches.values()
                ),
                "timer_active": self._submit_timer is not None,
                "last_add_time": self._last_add_time,
            }

    def shutdown(self):
        """Shutdown accumulator and submit remaining requests"""
        logger.info("Shutting down batch accumulator")

        # Cancel timer
        if self._submit_timer:
            self._submit_timer.cancel()

        # Submit remaining requests
        if self.pending_requests:
            self.force_submit()
