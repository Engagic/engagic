"""
Gemini LLM Orchestration - Smart model selection and prompt management

Responsibilities:
- Load prompts from prompts.json
- Select appropriate model (flash vs flash-lite) based on document size
- Configure extended thinking based on complexity
- Handle single and batch API calls
- Parse and validate responses
"""

import asyncio
import os
import json
import re
import time
from typing import List, Dict, Any, Optional, Tuple
from importlib.resources import files
from json import JSONDecodeError

from google import genai
from google.genai import types

from config import get_logger
from server.metrics import metrics
from exceptions import LLMError

logger = get_logger(__name__).bind(component="analyzer")

# Model thresholds
FLASH_LITE_MAX_CHARS = 200000  # Use Flash-Lite for documents under ~200K chars
FLASH_LITE_MAX_PAGES = 50  # Or under 50 pages


class GeminiSummarizer:
    """Smart LLM orchestrator - picks model, picks prompt, formats response"""

    def __init__(
        self, api_key: Optional[str] = None, prompts_path: Optional[str] = None
    ):
        """Initialize summarizer

        Args:
            api_key: Gemini API key (defaults to env vars)
            prompts_path: Path to prompts.json (defaults to same directory)
        """
        # Initialize Gemini client
        self.api_key = (
            api_key or os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
        )
        if not self.api_key:
            raise ValueError(
                "API key required - set GEMINI_API_KEY or LLM_API_KEY environment variable"
            )

        self.client = genai.Client(api_key=self.api_key)

        # Model names
        self.flash_model_name = "gemini-2.5-flash"
        self.flash_lite_model_name = "gemini-2.5-flash-lite"

        # Load prompts from JSON (v2 only)
        self.prompts_version = "v2"

        if prompts_path is None:
            # Load from package resources (works in installed packages)
            prompts_text = files("analysis.llm").joinpath("prompts_v2.json").read_text()
            self.prompts = json.loads(prompts_text)
        else:
            with open(prompts_path, "r") as f:
                self.prompts = json.load(f)

        logger.info("prompts loaded", prompt_categories=len(self.prompts), version=self.prompts_version)

    def _calculate_cost(self, model_name: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate API cost in dollars based on model and token usage

        Pricing (as of Nov 2025):
        - Gemini Flash: $0.075/1M input, $0.30/1M output
        - Gemini Flash-Lite: $0.0375/1M input, $0.15/1M output

        Confidence: 8/10 - Pricing accurate as of deployment but may change
        """
        if "lite" in model_name.lower():
            input_cost = (input_tokens / 1_000_000) * 0.0375
            output_cost = (output_tokens / 1_000_000) * 0.15
        else:
            input_cost = (input_tokens / 1_000_000) * 0.075
            output_cost = (output_tokens / 1_000_000) * 0.30

        return input_cost + output_cost

    def _call_with_retry(self, model_name: str, prompt: str, config, max_retries: int = 3):
        """Call Gemini API with automatic retry on 429 rate limits.

        Instead of proactive rate limiting, we trust Gemini to tell us when to retry.
        Gemini returns retryDelay in 429 responses - we parse and respect it.

        Args:
            model_name: Gemini model to use
            prompt: The prompt text
            config: GenerateContentConfig
            max_retries: Maximum retry attempts (default 3)

        Returns:
            GenerateContentResponse from Gemini

        Raises:
            LLMError: If max retries exceeded or non-rate-limit error
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=model_name, contents=prompt, config=config
                )
                return response

            except Exception as e:
                last_error = e
                error_str = str(e)

                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    # Parse retryDelay from Gemini's error response
                    retry_match = re.search(r'"retryDelay":\s*"(\d+)s"', error_str)
                    if retry_match:
                        delay = int(retry_match.group(1)) + 1  # Add 1s buffer
                    else:
                        # Fallback: exponential backoff (30s, 60s, 90s)
                        delay = 30 * (attempt + 1)

                    logger.warning(
                        "rate limited by gemini, waiting for retry",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay_seconds=delay
                    )
                    time.sleep(delay)
                    continue

                # Non-rate-limit error: raise immediately
                raise

        # All retries exhausted
        raise LLMError(
            f"Max retries ({max_retries}) exceeded due to rate limiting",
            model=model_name,
            prompt_type="unknown",
            original_error=last_error
        )

    def summarize_meeting(self, text: str) -> str:
        """Summarize a full meeting agenda

        Args:
            text: Extracted text from agenda PDF(s)

        Returns:
            Summary text
        """
        text_size = len(text)
        page_count = self._estimate_page_count(text)

        # Model selection based on size
        if text_size < FLASH_LITE_MAX_CHARS and page_count <= FLASH_LITE_MAX_PAGES:
            model_name = self.flash_lite_model_name
            model_display = "flash-lite"
        else:
            model_name = self.flash_model_name
            model_display = "flash"

        logger.info("summarizing meeting", page_count=page_count, text_size=text_size, model=model_display)

        # Prompt selection based on document size
        if page_count <= 30:
            prompt = self._get_prompt("meeting", "short_agenda", text=text)
        else:
            prompt = self._get_prompt("meeting", "comprehensive", text=text)

        # Thinking configuration based on complexity
        config = self._get_thinking_config(page_count, text_size, model_name)

        # Track API call duration
        start_time = time.time()
        prompt_type = "meeting_short" if page_count <= 30 else "meeting_comprehensive"

        try:
            response = self._call_with_retry(model_name, prompt, config)

            if response.text is None:
                raise ValueError("Gemini returned no text in response")

            # Extract token usage if available
            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) if hasattr(response, 'usage_metadata') else 0

            duration = time.time() - start_time

            # Record metrics
            metrics.record_llm_call(
                model=model_display,
                prompt_type=prompt_type,
                duration_seconds=duration,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_dollars=self._calculate_cost(model_name, input_tokens, output_tokens),
                success=True
            )

            logger.info("meeting summarized", duration_seconds=round(duration, 1), input_tokens=input_tokens, output_tokens=output_tokens, model=model_display)

            return response.text

        except Exception as e:
            duration = time.time() - start_time
            metrics.record_llm_call(
                model=model_display,
                prompt_type=prompt_type,
                duration_seconds=duration,
                input_tokens=0,
                output_tokens=0,
                cost_dollars=0,
                success=False
            )
            metrics.record_error(component="analyzer", error=e)
            logger.error("meeting summarization failed", duration_seconds=round(duration, 1), error=str(e), error_type=type(e).__name__)
            raise LLMError(
                f"Meeting summarization failed after {duration:.1f}s",
                model=model_display,
                prompt_type=prompt_type,
                original_error=e
            ) from e

    def summarize_item(self, item_title: str, text: str, page_count: Optional[int] = None) -> Tuple[str, List[str]]:
        """Summarize a single agenda item and extract topics (adaptive based on size)

        Args:
            item_title: Title of the agenda item
            text: Combined text from all attachments
            page_count: Actual page count from PDF extractor (optional, will estimate if not provided)

        Returns:
            Tuple of (summary, topics_list)
            summary = Combined markdown with thinking trace, summary, and citizen impact
            topics = List of canonical topic strings
        """
        text_size = len(text)

        # Use actual page count from PDF if available, otherwise estimate
        if page_count is None:
            page_count = self._estimate_page_count(text)

        # Adaptive prompt selection based on document size
        # Large items (100+ pages): comprehensive analysis with extended thinking mode
        # Standard items: focused analysis
        if page_count >= 100:
            prompt_type = "large"
            model_name = self.flash_model_name  # Always use flash for large items
            model_display = "flash"
            logger.info(
                "large item using comprehensive prompt",
                item_title=item_title[:50],
                page_count=page_count,
                text_size=text_size
            )
        else:
            prompt_type = "standard"
            # Model selection for standard items
            if text_size < FLASH_LITE_MAX_CHARS and page_count <= FLASH_LITE_MAX_PAGES:
                model_name = self.flash_lite_model_name
                model_display = "flash-lite"
            else:
                model_name = self.flash_model_name
                model_display = "flash"
            logger.info(
                "standard item processing",
                item_title=item_title[:50],
                page_count=page_count,
                text_size=text_size
            )

        # Get adaptive prompt and config
        prompt = self._get_prompt("item", prompt_type, title=item_title, text=text)
        response_schema = self.prompts["item"][prompt_type].get("response_schema")
        config = types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=8192,  # Increased from 2048 to match batch API
            response_mime_type="application/json",
            response_schema=response_schema
        )

        # Track API call
        start_time = time.time()

        try:
            response = self._call_with_retry(model_name, prompt, config)

            # Extract text - handle various response structures
            response_text = response.text
            if not response_text:
                # Try extracting from candidates structure (may have thinking blocks)
                response_text = self._extract_text_from_response(response)

            if not response_text:
                # Log full response structure for debugging
                logger.error(
                    "gemini empty response debug",
                    has_candidates=hasattr(response, 'candidates') and bool(response.candidates),
                    candidate_count=len(response.candidates) if hasattr(response, 'candidates') and response.candidates else 0,
                    has_prompt_feedback=hasattr(response, 'prompt_feedback'),
                    prompt_feedback=str(getattr(response, 'prompt_feedback', None))[:200] if hasattr(response, 'prompt_feedback') else None
                )
                raise ValueError("Gemini returned no text")

            # Extract token usage
            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0) if hasattr(response, 'usage_metadata') else 0
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0) if hasattr(response, 'usage_metadata') else 0

            duration = time.time() - start_time

            # Record metrics
            metrics.record_llm_call(
                model=model_display,
                prompt_type=f"item_{prompt_type}",
                duration_seconds=duration,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_dollars=self._calculate_cost(model_name, input_tokens, output_tokens),
                success=True
            )

            # Parse response based on version
            summary, topics = self._parse_item_response(response_text)

            return summary, topics

        except Exception as e:
            duration = time.time() - start_time
            metrics.record_llm_call(
                model=model_display,
                prompt_type=f"item_{prompt_type}",
                duration_seconds=duration,
                input_tokens=0,
                output_tokens=0,
                cost_dollars=0,
                success=False
            )
            metrics.record_error(component="analyzer", error=e)
            logger.error("item summarization failed", duration_seconds=round(duration, 1), error=str(e), error_type=type(e).__name__, prompt_type=prompt_type)
            raise LLMError(
                f"Item summarization failed after {duration:.1f}s",
                model=model_display,
                prompt_type=f"item_{prompt_type}",
                original_error=e
            ) from e

    async def summarize_batch(
        self,
        item_requests: List[Dict[str, Any]],
        shared_context: Optional[str] = None,
        meeting_id: Optional[str] = None
    ):
        """Process multiple agenda items using Gemini Batch API, yielding results per chunk

        Generator that yields chunk results immediately after each chunk completes.
        This enables incremental saving to prevent data loss on crashes.

        Uses chunked processing to respect rate limits:
        - 5 items per chunk (respects TPM quota)
        - 120-second delays between chunks (allows quota refill)
        - Exponential backoff on 429 errors

        Args:
            item_requests: List of dicts with structure:
                [{
                    'item_id': str,
                    'title': str,
                    'text': str,  # Item-specific text only (shared docs excluded)
                    'sequence': int,
                    'page_count': int or None  # Actual PDF page count if available
                }, ...]
            shared_context: Optional meeting-level shared document context (for caching)
            meeting_id: Optional meeting ID (for cache naming)

        Yields:
            List of results per chunk: [{
                'item_id': str,
                'success': bool,
                'summary': str,
                'topics': List[str],
                'error': str (if failed)
            }, ...]
        """
        if not item_requests:
            return

        total_items = len(item_requests)
        logger.info("processing batch", total_items=total_items, batch_enabled=True, cost_savings_percent=50)

        # Create Gemini cache for shared context if available and meets minimum threshold
        cache_name = None
        if shared_context:
            # Estimate token count (rough: 1 token = 4 chars)
            token_count = len(shared_context) // 4
            min_tokens = 1024  # Minimum for Flash caching

            if token_count >= min_tokens:
                try:
                    logger.info(
                        "creating gemini cache for shared context",
                        token_count=token_count
                    )
                    cache = self.client.caches.create(
                        model=self.flash_model_name,
                        config=types.CreateCachedContentConfig(
                            display_name=f"meeting-{meeting_id}-shared-docs",
                            contents=[types.Content(parts=[types.Part(text=shared_context)])],
                            ttl="3600s"  # 1 hour TTL (sufficient for batch processing)
                        )
                    )
                    cache_name = cache.name
                    logger.info(
                        "cache created",
                        cache_name=cache_name,
                        token_count=token_count,
                        ttl="1h"
                    )
                except (ValueError, TypeError, AttributeError, LLMError) as e:
                    logger.warning(
                        "failed to create cache proceeding without caching",
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    cache_name = None
            else:
                logger.info(
                    "shared context too small for caching",
                    token_count=token_count,
                    min_tokens=min_tokens
                )

        # Chunk items to respect TPM (tokens-per-minute) limits
        # Gemini Flash: 1M TPM limit - large PDFs can use 50K+ tokens each
        # Conservative chunk size prevents RESOURCE_EXHAUSTED errors
        chunk_size = 5  # Reduced from 15 -> 8 -> 5 due to TPM quota exhaustion
        chunks = [
            item_requests[i : i + chunk_size]
            for i in range(0, total_items, chunk_size)
        ]

        logger.info(
            "split into chunks",
            num_chunks=len(chunks),
            chunk_size=chunk_size
        )

        total_successful = 0
        total_processed = 0

        try:
            for chunk_idx, chunk in enumerate(chunks):
                chunk_num = chunk_idx + 1
                logger.info(
                    "processing chunk",
                    chunk_num=chunk_num,
                    total_chunks=len(chunks),
                    items_in_chunk=len(chunk)
                )

                # Process chunk with retry logic (pass cache_name and shared_context)
                chunk_results = await self._process_batch_chunk(chunk, chunk_num, cache_name, shared_context)

                # Track stats
                chunk_successful = sum(1 for r in chunk_results if r.get("success"))
                total_successful += chunk_successful
                total_processed += len(chunk_results)

                logger.info(
                    "chunk complete",
                    chunk_num=chunk_num,
                    successful=chunk_successful,
                    total=len(chunk_results),
                    cumulative_successful=total_successful,
                    cumulative_total=total_processed
                )

                # Yield results immediately for incremental saving
                yield chunk_results

                # Delay between chunks (except after last chunk)
                if chunk_idx < len(chunks) - 1:
                    delay = 120  # 120 seconds between chunks (increased from 90s to prevent quota exhaustion)
                    logger.info(
                        "waiting before next chunk for quota refill",
                        delay_seconds=delay
                    )
                    await asyncio.sleep(delay)

        finally:
            # Cleanup: Delete cache after all chunks processed
            if cache_name:
                try:
                    logger.info("cleaning up cache", cache_name=cache_name)
                    self.client.caches.delete(name=cache_name)
                    logger.info("cache deleted successfully")
                except (ValueError, AttributeError, LLMError) as e:
                    logger.warning("failed to delete cache", cache_name=cache_name, error=str(e), error_type=type(e).__name__)

            logger.info(
                "batch complete",
                successful=total_successful,
                total=total_processed
            )

    def _extract_response_text(self, response_data: Dict[str, Any]) -> Optional[str]:
        """Extract text from nested Gemini response structure

        Args:
            response_data: Response data from batch API

        Returns:
            Extracted text or None if not found
        """
        # Direct text field (simple case)
        if 'text' in response_data:
            return response_data['text']

        # Navigate candidates structure (complex case)
        candidates = response_data.get('candidates')
        if not candidates:
            return None

        candidate = candidates[0]
        content = candidate.get('content')
        if not content:
            return None

        parts = content.get('parts')
        if not parts or not parts[0]:
            return None

        return parts[0].get('text')

    def _extract_text_from_response(self, response) -> Optional[str]:
        """Extract text from live Gemini API response object

        Handles various response structures including thinking blocks.
        Used when response.text is None/empty.

        Args:
            response: GenerateContentResponse object from Gemini API

        Returns:
            Extracted text or None if not found
        """
        # Check for candidates
        if not hasattr(response, 'candidates') or not response.candidates:
            return None

        candidate = response.candidates[0]

        # Check finish reason for debugging
        if hasattr(candidate, 'finish_reason'):
            logger.debug("candidate finish_reason", finish_reason=str(candidate.finish_reason))

        # Check for content
        if not hasattr(candidate, 'content') or not candidate.content:
            return None

        # Check for parts
        if not hasattr(candidate.content, 'parts') or not candidate.content.parts:
            return None

        # Try to find text in parts (skip thinking blocks)
        for part in candidate.content.parts:
            if hasattr(part, 'text') and part.text:
                logger.info("extracted text from candidate part", length=len(part.text))
                return part.text

        return None

    def _parse_batch_response_line(
        self,
        line: str,
        line_num: int,
        request_map: Dict[str, Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Parse single JSONL response line and extract result

        Args:
            line: JSONL line to parse
            line_num: Line number for logging
            request_map: Map of item_id -> original request

        Returns:
            Result dict with item_id, success, summary/topics/error
            None if line should be skipped
        """
        if not line.strip():
            return None

        try:
            response_obj = json.loads(line)
        except json.JSONDecodeError as e:
            logger.error("failed to parse jsonl line", line_num=line_num, error=str(e), error_type=type(e).__name__)
            return None

        # Extract key from response
        key = response_obj.get('key')
        if not key:
            logger.error("response line missing key field", line_num=line_num)
            return None

        if key not in request_map:
            logger.warning(
                "no mapping found for key",
                key=key,
                sample_keys=list(request_map.keys())[:5]
            )
            return None

        original_req = request_map[key]

        # Handle error response
        if 'error' in response_obj:
            error_data = response_obj['error']
            error_str = str(error_data)

            # Log quota errors but DON'T retry the whole chunk
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                logger.warning(
                    "item hit quota limit individual failure",
                    key=key,
                    error=error_str
                )
            logger.error("item failed", key=key, error=error_str)

            return {
                "item_id": original_req["item_id"],
                "success": False,
                "error": error_str,
            }

        # Handle success response
        if 'response' not in response_obj:
            return None

        response_data = response_obj['response']

        try:
            # Extract text from nested structure
            response_text = self._extract_response_text(response_data)

            # Check finish_reason
            candidates = response_data.get('candidates')
            if candidates:
                finish_reason = candidates[0].get('finish_reason')
                if finish_reason and finish_reason != "STOP":
                    logger.warning(
                        "non-normal finish reason",
                        item_key=key,
                        finish_reason=finish_reason
                    )
                    if finish_reason == "MAX_TOKENS":
                        logger.error(
                            "item hit max tokens response truncated",
                            item_key=key
                        )

            # Log response
            logger.info(
                "response received",
                key=key,
                response_length=len(response_text) if response_text else 0
            )

            if not response_text:
                logger.warning("empty response from gemini", key=key)
                return {
                    "item_id": original_req["item_id"],
                    "success": False,
                    "error": "Empty response from Gemini",
                }

            # Parse response
            summary, topics = self._parse_item_response(response_text)

            return {
                "item_id": original_req["item_id"],
                "success": True,
                "summary": summary,
                "topics": topics,
            }

        except (JSONDecodeError, ValueError, KeyError, AttributeError) as e:
            logger.error(
                "error parsing response",
                key=key,
                error=str(e),
                error_type=type(e).__name__
            )
            logger.error(
                "input that caused failure",
                title=original_req['title'][:100],
                text_length=len(original_req['text'])
            )
            logger.error(
                "raw response that failed",
                response_preview=str(response_text)[:1000] if response_text else 'None'
            )
            return {
                "item_id": original_req["item_id"],
                "success": False,
                "error": str(e),
            }

    async def _wait_for_batch_completion(
        self,
        batch_name: str,
        max_wait_time: int = 1800,
        poll_interval: int = 10
    ) -> None:
        """Poll batch job until completion

        Args:
            batch_name: Batch job identifier
            max_wait_time: Maximum wait time in seconds (default 30 minutes)
            poll_interval: Polling interval in seconds (default 10 seconds)

        Raises:
            TimeoutError: If batch doesn't complete within max_wait_time
            RuntimeError: If batch job fails
        """
        completed_states = {
            "JOB_STATE_SUCCEEDED",
            "JOB_STATE_FAILED",
            "JOB_STATE_CANCELLED",
            "JOB_STATE_EXPIRED",
        }

        waited_time = 0
        while waited_time < max_wait_time:
            batch_job = self.client.batches.get(name=batch_name)

            if batch_job.state and batch_job.state.name in completed_states:
                logger.info(
                    "batch completed",
                    batch_name=batch_name,
                    state=batch_job.state.name
                )

                # Check for success
                if batch_job.state.name != "JOB_STATE_SUCCEEDED":
                    raise RuntimeError(f"Batch failed: {batch_job.state.name}")

                return

            state_name = batch_job.state.name if batch_job.state else "unknown"
            if waited_time % 30 == 0:  # Log every 30s
                logger.info(
                    "batch processing",
                    waited_time_seconds=waited_time,
                    state=state_name
                )

            await asyncio.sleep(poll_interval)
            waited_time += poll_interval

        raise TimeoutError(f"Batch timed out after {max_wait_time}s")

    async def _process_batch_chunk(
        self,
        chunk_requests: List[Dict[str, Any]],
        chunk_num: int,
        cache_name: Optional[str] = None,
        shared_context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Process a single chunk of batch requests with retry logic using JSONL file method

        Args:
            chunk_requests: List of item requests for this chunk
            chunk_num: Chunk number for logging
            cache_name: Optional Gemini cache name for shared context
            shared_context: Optional shared context text (used inline if not cached)

        Returns:
            List of results for this chunk
        """
        import json
        import tempfile
        import os

        max_retries = 3
        retry_delay = 60  # Start with 60s delay

        for attempt in range(max_retries):
            temp_path = None

            try:
                # Build request map and JSONL file
                request_map = {}
                temp_file = tempfile.NamedTemporaryFile(
                    mode='w', suffix='.json', delete=False
                )
                temp_path = temp_file.name

                for i, req in enumerate(chunk_requests):
                    item_title = req["title"]
                    item_id = req["item_id"]
                    text = req["text"]

                    # If shared context exists but not cached, prepend it inline
                    if shared_context and not cache_name:
                        text = f"=== SHARED CONTEXT (Background documents for this meeting) ===\n\n{shared_context}\n\n=== AGENDA ITEM: {item_title} ===\n\n{text}"

                    # Use actual page count if available, otherwise estimate
                    page_count = req.get("page_count")
                    if page_count is None:
                        page_count = self._estimate_page_count(text)

                    # Adaptive prompt selection based on size
                    prompt_type = "large" if page_count >= 100 else "standard"

                    # Build prompt and config
                    prompt = self._get_prompt(
                        "item", prompt_type, title=item_title, text=text
                    )

                    generation_config = {
                        "temperature": 0.3,
                        "maxOutputTokens": 8192,
                        "responseMimeType": "application/json",
                    }

                    logger.info(
                        "batch request details",
                        request_index=i,
                        item_title=item_title[:80],
                        text_length=len(text),
                        page_count=page_count,
                        prompt_type=prompt_type
                    )

                    # Write JSONL line with key for matching
                    jsonl_line = {
                        "key": item_id,
                        "request": {
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": generation_config,
                        }
                    }

                    if cache_name:
                        jsonl_line["request"]["cachedContent"] = cache_name

                    temp_file.write(json.dumps(jsonl_line) + '\n')
                    request_map[item_id] = req

                temp_file.close()

                # Upload JSONL file
                logger.info(
                    "uploading jsonl file",
                    num_items=len(chunk_requests),
                    attempt=attempt + 1,
                    max_retries=max_retries
                )

                uploaded_file = self.client.files.upload(
                    file=temp_path,
                    config={"display_name": f"batch-chunk-{chunk_num}-{time.time()}"}
                )

                if not uploaded_file.name:
                    raise ValueError("File uploaded but no name returned")

                logger.info("uploaded file", file_name=uploaded_file.name)

                # Submit batch job
                logger.info("submitting batch job", chunk_num=chunk_num)
                batch_start_time = time.time()

                batch_job = self.client.batches.create(
                    model=self.flash_model_name,
                    src=uploaded_file.name,
                    config={"display_name": f"chunk-{chunk_num}-{time.time()}"},
                )

                if not batch_job.name:
                    raise ValueError("Batch job created but no name returned")

                logger.info("submitted batch", batch_name=batch_job.name)

                # Wait for batch completion
                await self._wait_for_batch_completion(batch_job.name)

                # Download and parse results
                batch_job = self.client.batches.get(name=batch_job.name)

                if not batch_job.dest or not batch_job.dest.file_name:
                    logger.error("batch job completed but no response file available")
                    raise RuntimeError("No response file in batch job result")

                response_file_name = batch_job.dest.file_name
                logger.info("downloading response file", file_name=response_file_name)

                response_content = self.client.files.download(file=response_file_name)
                response_text = response_content.decode('utf-8')

                # Parse JSONL responses
                results = []
                for line_num, line in enumerate(response_text.strip().split('\n')):
                    result = self._parse_batch_response_line(line, line_num, request_map)
                    if result:
                        results.append(result)

                # Cleanup temp file
                try:
                    if temp_path and os.path.exists(temp_path):
                        os.unlink(temp_path)
                        logger.debug("cleaned up temp file", path=temp_path)
                except OSError as cleanup_error:
                    logger.warning("failed to cleanup temp file", path=temp_path, error=str(cleanup_error), error_type=type(cleanup_error).__name__)

                # Record metrics
                successful = sum(1 for r in results if r.get("success"))
                failed = len(results) - successful
                batch_duration = time.time() - batch_start_time

                for result in results:
                    req = request_map.get(result["item_id"], {})
                    page_count = req.get("page_count", 0) if req else 0
                    prompt_type = "large" if page_count >= 100 else "standard"

                    metrics.record_llm_call(
                        model="flash",
                        prompt_type=f"item_{prompt_type}_batch",
                        duration_seconds=batch_duration / len(results),
                        input_tokens=0,
                        output_tokens=0,
                        cost_dollars=0,
                        success=result.get("success", False)
                    )

                logger.info("batch chunk complete", chunk_num=chunk_num, duration_seconds=round(batch_duration, 1), successful=successful, total=len(results), failure_rate=round(failed / len(results) * 100, 1) if results else 0)

                return results

            except Exception as e:
                error_str = str(e)
                is_quota_error = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str

                metrics.record_error(component="analyzer", error=e)

                if is_quota_error and attempt < max_retries - 1:
                    backoff_delay = retry_delay * (2**attempt)
                    logger.warning(
                        "chunk hit quota limit retrying",
                        chunk_num=chunk_num,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        backoff_delay_seconds=backoff_delay
                    )
                    await asyncio.sleep(backoff_delay)
                    continue

                # Final attempt failed or non-quota error
                logger.error("batch chunk failed", chunk_num=chunk_num, attempts=attempt + 1, error=str(e), error_type=type(e).__name__)

                # Record failed batch metrics
                for req in chunk_requests:
                    page_count = req.get("page_count", 0)
                    prompt_type = "large" if page_count >= 100 else "standard"
                    metrics.record_llm_call(
                        model="flash",
                        prompt_type=f"item_{prompt_type}_batch",
                        duration_seconds=0,
                        input_tokens=0,
                        output_tokens=0,
                        cost_dollars=0,
                        success=False
                    )

                return [
                    {"item_id": req["item_id"], "success": False, "error": error_str}
                    for req in chunk_requests
                ]

        # Should never reach here, but safety fallback
        return [
            {
                "item_id": req["item_id"],
                "success": False,
                "error": "Max retries exceeded",
            }
            for req in chunk_requests
        ]

    def _get_prompt(self, category: str, prompt_type: str, **variables) -> str:
        """Get prompt from JSON and format with variables

        Args:
            category: Top-level category (e.g., 'meeting', 'item')
            prompt_type: Specific prompt type (e.g., 'short_agenda', 'standard')
            **variables: Variables to interpolate into template

        Returns:
            Formatted prompt string
        """
        try:
            prompt_data = self.prompts[category][prompt_type]
            template = prompt_data["template"]
        except KeyError as e:
            raise ValueError(f"Prompt not found: {category}.{prompt_type}") from e

        try:
            return template.format(**variables)
        except KeyError as e:
            raise ValueError(
                f"Missing variable for prompt {category}.{prompt_type}: {e}"
            ) from e

    def _get_thinking_config(
        self, page_count: int, text_size: int, model_name: str
    ) -> types.GenerateContentConfig:
        """Get thinking configuration based on document complexity

        Args:
            page_count: Number of pages
            text_size: Character count
            model_name: Model being used

        Returns:
            GenerateContentConfig with appropriate thinking budget
        """
        # Confidence: 9/10 - Gemini's large context handles everything in one pass
        # Adaptive thinking based on document complexity

        if page_count <= 10 and text_size <= 30000:
            # Easy task: Simple agendas, disable thinking for speed
            logger.info(
                "simple document disabling thinking for speed",
                page_count=page_count
            )
            return types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=0
                ),  # No thinking needed
            )

        elif page_count <= 50 and text_size <= 150000:
            # Medium task: Standard agendas, use moderate thinking
            logger.info(
                "medium document using moderate thinking",
                page_count=page_count
            )
            if model_name == self.flash_lite_model_name:
                # Flash-Lite needs explicit budget since it doesn't think by default
                return types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=2048
                    ),  # Moderate thinking
                )
            else:
                # Flash uses dynamic thinking by default
                return types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                    # Let model decide thinking budget dynamically
                )

        else:
            # Hard task: Complex documents, use dynamic thinking for best quality
            logger.info(
                "complex document using dynamic thinking",
                page_count=page_count
            )
            return types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=-1
                ),  # Dynamic thinking
            )

    def _parse_item_response(self, response_text: str) -> Tuple[str, List[str]]:
        """Parse item response into summary and topics

        Args:
            response_text: Raw JSON response from Gemini

        Returns:
            Tuple of (summary, topics_list)
            summary = Combined markdown with thinking trace, summary, and citizen impact
            topics = List of canonical topic strings (validated against taxonomy)
        """
        response_text = response_text.strip()

        try:
            data = json.loads(response_text)

            # Validate JSON structure
            required_fields = ["summary_markdown", "citizen_impact_markdown", "topics", "confidence"]
            missing_fields = [f for f in required_fields if f not in data]
            if missing_fields:
                logger.error("json missing required fields", missing_fields=missing_fields)
                raise ValueError(f"Invalid JSON response: missing {missing_fields}")

            # Build comprehensive summary with all components
            summary_md = data.get("summary_markdown", "")
            impact_md = data.get("citizen_impact_markdown", "")
            confidence = data.get("confidence", "unknown")

            # Validate and normalize topics
            raw_topics = data.get("topics", [])
            if not isinstance(raw_topics, list):
                logger.error("topics field is not a list", topics_type=type(raw_topics).__name__)
                raw_topics = []

            # Validate topics against canonical taxonomy
            from analysis.topics.normalizer import get_normalizer
            normalizer = get_normalizer()
            canonical_topics = normalizer.get_all_canonical_topics()

            validated_topics = []
            invalid_topics = []

            for topic in raw_topics:
                if topic in canonical_topics:
                    validated_topics.append(topic)
                else:
                    invalid_topics.append(topic)
                    logger.warning("llm returned invalid topic not in taxonomy", topic=topic)

            if invalid_topics:
                logger.warning(
                    "rejected invalid topics",
                    num_invalid=len(invalid_topics),
                    invalid_topics=invalid_topics,
                    valid_topics=validated_topics
                )

            # If all topics were invalid, use "other" as fallback
            if not validated_topics and raw_topics:
                logger.warning("all topics invalid using other as fallback")
                validated_topics = ["other"]

            topics = validated_topics

            # Combine into single markdown document
            summary_parts = []

            if summary_md:
                summary_parts.append(f"## Summary\n\n{summary_md}\n")

            if impact_md:
                summary_parts.append(f"## Citizen Impact\n\n{impact_md}\n")

            if confidence:
                summary_parts.append(f"## Confidence\n\n{confidence}")

            summary = "\n".join(summary_parts)

            return summary, topics

        except json.JSONDecodeError as e:
            # FIXED (Nov 2025): Was caused by max_output_tokens=2048 in batch API
            # Increased to 8192 to match single-item processing
            # Added finish_reason checking to detect future MAX_TOKENS issues
            logger.error("failed to parse json response", error=str(e), error_type=type(e).__name__)
            logger.error("full malformed json response", response_text=response_text)
            raise
        except Exception as e:
            logger.error("error validating json response", error=str(e), error_type=type(e).__name__)
            logger.error("response that failed validation", response_text=response_text)
            raise

    def _clean_summary(self, raw_summary: str) -> str:
        """Remove LLM artifacts and document headers from summary text

        Args:
            raw_summary: Raw summary text from LLM

        Returns:
            Cleaned summary text ready for storage
        """
        import re

        if not raw_summary:
            return ""

        cleaned = raw_summary
        # Remove document section markers
        cleaned = re.sub(r"=== DOCUMENT \d+ ===", "", cleaned)
        cleaned = re.sub(r"--- SECTION \d+ SUMMARY ---", "", cleaned)

        # Remove common LLM preambles
        cleaned = re.sub(r"Here's a concise summary of the[^:]*:", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"Here's a summary of the[^:]*:", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"Here's the key points[^:]*:", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"Here's a structured analysis[^:]*:", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"Summary of the[^:]*:", "", cleaned, flags=re.IGNORECASE)

        # Normalize excessive newlines
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

        return cleaned.strip()

    def _estimate_page_count(self, text: str) -> int:
        """Estimate page count from text

        Args:
            text: Extracted text

        Returns:
            Estimated page count
        """
        # Rough estimate: ~2000 chars per page
        return max(1, len(text) // 2000)
