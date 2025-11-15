"""
Gemini LLM Orchestration - Smart model selection and prompt management

Responsibilities:
- Load prompts from prompts.json
- Select appropriate model (flash vs flash-lite) based on document size
- Configure extended thinking based on complexity
- Handle single and batch API calls
- Parse and validate responses
"""

import os
import json
import time
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from importlib.resources import files

from google import genai
from google.genai import types

from config import get_logger
from server.metrics import metrics

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
            response = self.client.models.generate_content(
                model=model_name, contents=prompt, config=config
            )

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
            raise

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
                f"[Summarizer] Large item '{item_title[:50]}...' ({page_count} pages, {text_size} chars) - using comprehensive prompt"
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
                f"[Summarizer] Standard item '{item_title[:50]}...' ({page_count} pages, {text_size} chars)"
            )

        # Get adaptive prompt and config
        prompt = self._get_prompt("item", prompt_type, title=item_title, text=text)
        response_schema = self.prompts["item"][prompt_type].get("response_schema")
        config = types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=2048,
            response_mime_type="application/json",
            response_schema=response_schema
        )

        # Track API call
        start_time = time.time()

        try:
            response = self.client.models.generate_content(
                model=model_name, contents=prompt, config=config
            )

            if not response.text:
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
            summary, topics = self._parse_item_response(response.text)

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
            raise

    def summarize_batch(
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
                        f"[Summarizer] Creating Gemini cache for shared context (~{token_count:,} tokens)"
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
                        f"[Summarizer] Cache created: {cache_name} "
                        f"(~{token_count:,} tokens, 1h TTL)"
                    )
                except Exception as e:
                    logger.warning(
                        f"[Summarizer] Failed to create cache: {e}. "
                        "Proceeding without caching."
                    )
                    cache_name = None
            else:
                logger.info(
                    f"[Summarizer] Shared context too small for caching "
                    f"({token_count} tokens < {min_tokens} minimum)"
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
            f"[Summarizer] Split into {len(chunks)} chunks of {chunk_size} items each"
        )

        total_successful = 0
        total_processed = 0

        try:
            for chunk_idx, chunk in enumerate(chunks):
                chunk_num = chunk_idx + 1
                logger.info(
                    f"[Summarizer] Processing chunk {chunk_num}/{len(chunks)} ({len(chunk)} items)"
                )

                # Process chunk with retry logic (pass cache_name and shared_context)
                chunk_results = self._process_batch_chunk(chunk, chunk_num, cache_name, shared_context)

                # Track stats
                chunk_successful = sum(1 for r in chunk_results if r.get("success"))
                total_successful += chunk_successful
                total_processed += len(chunk_results)

                logger.info(
                    f"[Summarizer] Chunk {chunk_num} complete: {chunk_successful}/{len(chunk_results)} successful "
                    f"(total: {total_successful}/{total_processed})"
                )

                # Yield results immediately for incremental saving
                yield chunk_results

                # Delay between chunks (except after last chunk)
                if chunk_idx < len(chunks) - 1:
                    delay = 120  # 120 seconds between chunks (increased from 90s to prevent quota exhaustion)
                    logger.info(
                        f"[Summarizer] Waiting {delay}s before next chunk (quota refill)..."
                    )
                    time.sleep(delay)

        finally:
            # Cleanup: Delete cache after all chunks processed
            if cache_name:
                try:
                    logger.info(f"[Summarizer] Cleaning up cache: {cache_name}")
                    self.client.caches.delete(name=cache_name)
                    logger.info("[Summarizer] Cache deleted successfully")
                except Exception as e:
                    logger.warning(f"[Summarizer] Failed to delete cache: {e}")

            logger.info(
                f"[Summarizer] Batch complete: {total_successful}/{total_processed} successful"
            )

    def _process_batch_chunk(
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
            # JSONL file method with explicit key-based matching
            # This is the ONLY way to guarantee request/response matching
            request_map = {}  # Maps key (item_id) -> original request

            # Create temp JSONL file
            temp_file = tempfile.NamedTemporaryFile(
                mode='w', suffix='.json', delete=False
            )
            temp_path = temp_file.name

            try:
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
                    # NOTE: Batch API might not support responseSchema
                    # Use responseMimeType only, rely on prompt for structure
                    generation_config = {
                        "temperature": 0.3,
                        "maxOutputTokens": 8192,
                        "responseMimeType": "application/json",
                    }

                    # Log input details for debugging
                    logger.info(
                        f"[Summarizer] Request {i}: '{item_title[:80]}...', {len(text)} chars, {page_count} pages, {prompt_type} prompt"
                    )

                    # Write JSONL line with key for matching
                    # NOTE: Batch API expects camelCase for ALL field names in JSON
                    jsonl_line = {
                        "key": item_id,  # CRITICAL: This key matches response to request
                        "request": {
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": generation_config,  # camelCase!
                        }
                    }

                    # Include cached context if available
                    if cache_name:
                        jsonl_line["request"]["cachedContent"] = cache_name

                    temp_file.write(json.dumps(jsonl_line) + '\n')
                    request_map[item_id] = req

                temp_file.close()

                # Upload JSONL file
                logger.info(
                    f"[Summarizer] Uploading JSONL file with {len(chunk_requests)} items (attempt {attempt + 1}/{max_retries})"
                )

                uploaded_file = self.client.files.upload(
                    file=temp_path,
                    config={"display_name": f"batch-chunk-{chunk_num}-{time.time()}"}
                )

                logger.info(f"[Summarizer] Uploaded file: {uploaded_file.name}")

                # Submit batch job with uploaded file
                if not uploaded_file.name:
                    raise ValueError("File uploaded but no name returned")

                logger.info(
                    f"[Summarizer] Submitting chunk {chunk_num} batch job"
                )

                # Track batch job timing
                batch_start_time = time.time()

                batch_job = self.client.batches.create(
                    model=self.flash_model_name,
                    src=uploaded_file.name,
                    config={"display_name": f"chunk-{chunk_num}-{time.time()}"},
                )

                batch_name = batch_job.name
                if not batch_name:
                    raise ValueError("Batch job created but no name returned")

                logger.info(f"[Summarizer] Submitted batch {batch_name}")

                # Poll for completion
                max_wait_time = 1800  # 30 minutes max
                poll_interval = 10  # Check every 10 seconds
                waited_time = 0

                completed_states = {
                    "JOB_STATE_SUCCEEDED",
                    "JOB_STATE_FAILED",
                    "JOB_STATE_CANCELLED",
                    "JOB_STATE_EXPIRED",
                }

                while waited_time < max_wait_time:
                    batch_job = self.client.batches.get(name=batch_name)

                    if batch_job.state and batch_job.state.name in completed_states:
                        logger.info(
                            f"[Summarizer] Batch {batch_name} completed: {batch_job.state.name}"
                        )
                        break

                    state_name = batch_job.state.name if batch_job.state else "unknown"
                    if waited_time % 30 == 0:  # Log every 30s
                        logger.info(
                            f"[Summarizer] Batch processing... ({waited_time}s, state: {state_name})"
                        )

                    time.sleep(poll_interval)
                    waited_time += poll_interval

                if waited_time >= max_wait_time:
                    raise TimeoutError(f"Batch timed out after {max_wait_time}s")

                if (
                    not batch_job.state
                    or batch_job.state.name != "JOB_STATE_SUCCEEDED"
                ):
                    state_name = batch_job.state.name if batch_job.state else "unknown"
                    raise RuntimeError(f"Batch failed: {state_name}")

                # Process results from JSONL response file
                results = []

                if batch_job.dest and batch_job.dest.file_name:
                    # Download response JSONL file
                    response_file_name = batch_job.dest.file_name
                    logger.info(f"[Summarizer] Downloading response file: {response_file_name}")

                    response_content = self.client.files.download(file=response_file_name)
                    response_text = response_content.decode('utf-8')

                    # Parse JSONL responses
                    for line_num, line in enumerate(response_text.strip().split('\n')):
                        if not line.strip():
                            continue

                        try:
                            response_obj = json.loads(line)

                            # Extract key from response
                            key = response_obj.get('key')
                            if not key:
                                logger.error(f"[Summarizer] Response line {line_num} missing 'key' field")
                                continue

                            if key not in request_map:
                                logger.warning(
                                    f"[Summarizer] No mapping found for key {key} in request_map keys: {list(request_map.keys())[:5]}"
                                )
                                continue

                            original_req = request_map[key]

                            # Check if response or error
                            if 'response' in response_obj:
                                response_data = response_obj['response']
                                response_text = None

                                try:
                                    # Extract text from response
                                    if 'text' in response_data:
                                        response_text = response_data['text']
                                    elif 'candidates' in response_data and response_data['candidates']:
                                        # Extract from candidates structure
                                        candidate = response_data['candidates'][0]
                                        if 'content' in candidate and 'parts' in candidate['content']:
                                            parts = candidate['content']['parts']
                                            if parts and 'text' in parts[0]:
                                                response_text = parts[0]['text']

                                    # Check finish_reason
                                    if 'candidates' in response_data and response_data['candidates']:
                                        finish_reason = response_data['candidates'][0].get('finish_reason')
                                        if finish_reason and finish_reason != "STOP":
                                            logger.warning(
                                                f"[Summarizer] Item {key} had non-normal finish_reason: {finish_reason}"
                                            )
                                            if finish_reason == "MAX_TOKENS":
                                                logger.error(
                                                    f"[Summarizer] Item {key} hit MAX_TOKENS - response truncated!"
                                                )

                                    # Log response
                                    logger.info(
                                        f"[Summarizer] Response for {key}: {len(response_text) if response_text else 0} chars"
                                    )

                                    if not response_text:
                                        logger.warning(f"[Summarizer] Empty response for {key}")
                                        results.append({
                                            "item_id": original_req["item_id"],
                                            "success": False,
                                            "error": "Empty response from Gemini",
                                        })
                                        continue

                                    # Parse response
                                    summary, topics = self._parse_item_response(response_text)

                                    results.append({
                                        "item_id": original_req["item_id"],
                                        "success": True,
                                        "summary": summary,
                                        "topics": topics,
                                    })

                                except Exception as e:
                                    logger.error(
                                        f"[Summarizer] Error parsing response for {key}: {e}"
                                    )
                                    logger.error(
                                        f"[Summarizer] Input that caused failure - Title: {original_req['title'][:100]}"
                                    )
                                    logger.error(
                                        f"[Summarizer] Input text length: {len(original_req['text'])} chars"
                                    )
                                    logger.error(
                                        f"[Summarizer] Raw response that failed: {str(response_text)[:1000] if response_text else 'None'}"
                                    )
                                    results.append({
                                        "item_id": original_req["item_id"],
                                        "success": False,
                                        "error": str(e),
                                    })

                            elif 'error' in response_obj:
                                error_data = response_obj['error']
                                error_str = str(error_data)

                                # Log quota errors but DON'T retry the whole chunk
                                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                                    logger.warning(
                                        f"[Summarizer] Item {key} hit quota limit (individual failure): {error_str}"
                                    )
                                logger.error(
                                    f"[Summarizer] Item {key} failed: {error_str}"
                                )
                                results.append({
                                    "item_id": original_req["item_id"],
                                    "success": False,
                                    "error": error_str,
                                })

                        except json.JSONDecodeError as e:
                            logger.error(f"[Summarizer] Failed to parse JSONL line {line_num}: {e}")
                            continue

                else:
                    logger.error("[Summarizer] Batch job completed but no response file available")
                    raise RuntimeError("No response file in batch job result")

                # Cleanup: Delete temp file
                try:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                        logger.debug(f"[Summarizer] Cleaned up temp file: {temp_path}")
                except Exception as cleanup_error:
                    logger.warning(f"[Summarizer] Failed to cleanup temp file: {cleanup_error}")

                successful = sum(1 for r in results if r.get("success"))
                failed = len(results) - successful
                batch_duration = time.time() - batch_start_time

                # Record metrics for each item in batch
                for result in results:
                    # Estimate prompt type from request
                    req = request_map.get(result["item_id"], {})
                    page_count = req.get("page_count", 0) if req else 0
                    prompt_type = "large" if page_count >= 100 else "standard"

                    metrics.record_llm_call(
                        model="flash",
                        prompt_type=f"item_{prompt_type}_batch",
                        duration_seconds=batch_duration / len(results),  # Amortize batch time
                        input_tokens=0,  # Batch API doesn't provide per-item token counts
                        output_tokens=0,
                        cost_dollars=0,  # Track via batch-level estimates
                        success=result.get("success", False)
                    )

                logger.info("batch chunk complete", chunk_num=chunk_num, duration_seconds=round(batch_duration, 1), successful=successful, total=len(results), failure_rate=round(failed / len(results) * 100, 1) if results else 0)

                return results

            except Exception as e:
                error_str = str(e)
                is_quota_error = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str

                # Record error metrics
                metrics.record_error(component="analyzer", error=e)

                if is_quota_error and attempt < max_retries - 1:
                    # Exponential backoff on quota errors
                    backoff_delay = retry_delay * (2**attempt)
                    logger.warning(
                        f"[Summarizer] Chunk {chunk_num} hit quota limit (attempt {attempt + 1}/{max_retries}). "
                        f"Retrying in {backoff_delay}s..."
                    )
                    time.sleep(backoff_delay)
                    continue
                else:
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
                f"[Summarizer] Simple document ({page_count} pages) - disabling thinking for speed"
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
                f"[Summarizer] Medium document ({page_count} pages) - using moderate thinking"
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
                f"[Summarizer] Complex document ({page_count} pages) - using dynamic thinking"
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
                logger.error(f"[Summarizer] JSON missing required fields: {missing_fields}")
                raise ValueError(f"Invalid JSON response: missing {missing_fields}")

            # Build comprehensive summary with all components
            summary_md = data.get("summary_markdown", "")
            impact_md = data.get("citizen_impact_markdown", "")
            confidence = data.get("confidence", "unknown")

            # Validate and normalize topics
            raw_topics = data.get("topics", [])
            if not isinstance(raw_topics, list):
                logger.error(f"[Summarizer] Topics field is not a list: {type(raw_topics)}")
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
                    logger.warning(f"[Summarizer] LLM returned invalid topic: '{topic}' (not in taxonomy)")

            if invalid_topics:
                logger.warning(
                    f"[Summarizer] Rejected {len(invalid_topics)} invalid topics: {invalid_topics}. "
                    f"Valid topics: {validated_topics}"
                )

            # If all topics were invalid, use "other" as fallback
            if not validated_topics and raw_topics:
                logger.warning("[Summarizer] All topics invalid, using 'other' as fallback")
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
            logger.error(f"[Summarizer] Failed to parse JSON response: {e}")
            logger.error(f"[Summarizer] Full malformed JSON response:\n{response_text}")
            raise
        except Exception as e:
            logger.error(f"[Summarizer] Error validating JSON response: {e}")
            logger.error(f"[Summarizer] Response that failed validation:\n{response_text}")
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
