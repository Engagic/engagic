"""
Gemini LLM Orchestration - Smart model selection and prompt management

Responsibilities:
- Load prompts from prompts.json
- Select appropriate model (flash vs flash-lite) based on document size
- Configure thinking budgets based on complexity
- Handle single and batch API calls
- Parse and validate responses
"""

import os
import json
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from google import genai
from google.genai import types

logger = logging.getLogger("engagic")

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
        if prompts_path is None:
            prompts_file = Path(__file__).parent / "prompts_v2.json"
        else:
            prompts_file = Path(prompts_path)

        self.prompts_version = "v2"

        with open(prompts_file, "r") as f:
            self.prompts = json.load(f)

        logger.info(f"[Summarizer] Loaded {len(self.prompts)} prompt categories")

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

        logger.info(
            f"[Summarizer] Summarizing {page_count} pages ({text_size} chars) using Gemini {model_display}"
        )

        # Prompt selection based on document size
        if page_count <= 30:
            prompt = self._get_prompt("meeting", "short_agenda", text=text)
        else:
            prompt = self._get_prompt("meeting", "comprehensive", text=text)

        # Thinking configuration based on complexity
        config = self._get_thinking_config(page_count, text_size, model_name)

        try:
            response = self.client.models.generate_content(
                model=model_name, contents=prompt, config=config
            )

            if response.text is None:
                raise ValueError("Gemini returned no text in response")

            return response.text

        except Exception as e:
            logger.error(f"[Summarizer] Meeting summarization failed: {e}")
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
        # Large items (100+ pages): comprehensive analysis with enhanced thinking
        # Standard items: focused analysis
        if page_count >= 100:
            prompt_type = "large"
            model_name = self.flash_model_name  # Always use flash for large items
            logger.info(
                f"[Summarizer] Large item '{item_title[:50]}...' ({page_count} pages, {text_size} chars) - using comprehensive prompt"
            )
        else:
            prompt_type = "standard"
            # Model selection for standard items
            if text_size < FLASH_LITE_MAX_CHARS and page_count <= FLASH_LITE_MAX_PAGES:
                model_name = self.flash_lite_model_name
            else:
                model_name = self.flash_model_name
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

        try:
            response = self.client.models.generate_content(
                model=model_name, contents=prompt, config=config
            )

            if not response.text:
                raise ValueError("Gemini returned no text")

            # Parse response based on version
            summary, topics = self._parse_item_response(response.text)

            return summary, topics

        except Exception as e:
            logger.error(f"[Summarizer] Item summarization failed: {e}")
            raise

    def summarize_batch(
        self, item_requests: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Process multiple agenda items using Gemini Batch API for 50% cost savings

        Uses chunked processing to respect rate limits:
        - 15 items per chunk (respects 1k RPM flash quota with buffer)
        - 90-second delays between chunks (allows quota refill)
        - Exponential backoff on 429 errors

        Args:
            item_requests: List of dicts with structure:
                [{
                    'item_id': str,
                    'title': str,
                    'text': str,  # Pre-extracted and concatenated text
                    'sequence': int,
                    'page_count': int or None  # Actual PDF page count if available
                }, ...]

        Returns:
            List of results: [{
                'item_id': str,
                'success': bool,
                'summary': str,
                'topics': List[str],
                'error': str (if failed)
            }, ...]
        """
        if not item_requests:
            return []

        total_items = len(item_requests)
        logger.info(
            f"[Summarizer] Processing {total_items} items using Batch API (50% savings)"
        )

        # Chunk items to respect rate limits
        chunk_size = 15  # Conservative: respects 1k RPM limit
        chunks = [
            item_requests[i : i + chunk_size]
            for i in range(0, total_items, chunk_size)
        ]

        logger.info(
            f"[Summarizer] Split into {len(chunks)} chunks of {chunk_size} items each"
        )

        all_results = []

        for chunk_idx, chunk in enumerate(chunks):
            chunk_num = chunk_idx + 1
            logger.info(
                f"[Summarizer] Processing chunk {chunk_num}/{len(chunks)} ({len(chunk)} items)"
            )

            # Process chunk with retry logic
            chunk_results = self._process_batch_chunk(chunk, chunk_num)
            all_results.extend(chunk_results)

            # Delay between chunks (except after last chunk)
            if chunk_idx < len(chunks) - 1:
                delay = 90  # 90 seconds between chunks
                logger.info(
                    f"[Summarizer] Waiting {delay}s before next chunk (quota refill)..."
                )
                time.sleep(delay)

        successful = sum(1 for r in all_results if r.get("success"))
        logger.info(
            f"[Summarizer] Batch complete: {successful}/{total_items} successful"
        )

        return all_results

    def _process_batch_chunk(
        self, chunk_requests: List[Dict[str, Any]], chunk_num: int
    ) -> List[Dict[str, Any]]:
        """Process a single chunk of batch requests with retry logic

        Args:
            chunk_requests: List of item requests for this chunk
            chunk_num: Chunk number for logging

        Returns:
            List of results for this chunk
        """
        max_retries = 3
        retry_delay = 60  # Start with 60s delay

        for attempt in range(max_retries):
            try:
                # Prepare inline requests
                inline_requests = []
                request_map = {}

                for i, req in enumerate(chunk_requests):
                    item_title = req["title"]
                    text = req["text"]

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
                    response_schema = self.prompts["item"][prompt_type].get(
                        "response_schema"
                    )
                    config = {
                        "temperature": 0.3,
                        "max_output_tokens": 8192,  # Match single-item processing (was 2048, caused truncation)
                        "response_mime_type": "application/json",
                        "response_schema": response_schema,
                    }

                    # Log input details for debugging
                    logger.info(
                        f"[Summarizer] Request {i}: '{item_title[:80]}...', {len(text)} chars, {page_count} pages, {prompt_type} prompt"
                    )

                    inline_requests.append(
                        {
                            "contents": [{"parts": [{"text": prompt}], "role": "user"}],
                            "config": config,
                        }
                    )

                    request_map[i] = req

                # Submit batch job
                logger.info(
                    f"[Summarizer] Submitting chunk {chunk_num} with {len(inline_requests)} items (attempt {attempt + 1}/{max_retries})"
                )

                batch_job = self.client.batches.create(
                    model=self.flash_model_name,
                    src=inline_requests,
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

                # Process results
                results = []

                if batch_job.dest and batch_job.dest.inlined_responses:
                    for i, inline_response in enumerate(
                        batch_job.dest.inlined_responses
                    ):
                        if i not in request_map:
                            logger.warning(
                                f"[Summarizer] No mapping found for response {i}"
                            )
                            continue

                        original_req = request_map[i]

                        if inline_response.response:
                            response_text = None  # Initialize for error logging
                            try:
                                response_text = inline_response.response.text

                                # Check finish_reason to detect truncation
                                if inline_response.response.candidates:
                                    finish_reason = inline_response.response.candidates[0].finish_reason
                                    if finish_reason and finish_reason.name != "STOP":
                                        logger.warning(
                                            f"[Summarizer] Item {original_req['item_id']} had non-normal finish_reason: {finish_reason.name}"
                                        )
                                        if finish_reason.name == "MAX_TOKENS":
                                            logger.error(
                                                f"[Summarizer] Item {original_req['item_id']} hit MAX_TOKENS - response truncated!"
                                            )

                                # Log raw response for debugging failures
                                logger.info(
                                    f"[Summarizer] Response for {original_req['item_id']}: {len(response_text) if response_text else 0} chars"
                                )

                                if not response_text:
                                    logger.warning(
                                        f"[Summarizer] Empty response for {original_req['item_id']}"
                                    )
                                    results.append(
                                        {
                                            "item_id": original_req["item_id"],
                                            "success": False,
                                            "error": "Empty response from Gemini",
                                        }
                                    )
                                    continue

                                # Parse response
                                summary, topics = self._parse_item_response(
                                    response_text
                                )

                                results.append(
                                    {
                                        "item_id": original_req["item_id"],
                                        "success": True,
                                        "summary": summary,
                                        "topics": topics,
                                    }
                                )

                            except Exception as e:
                                logger.error(
                                    f"[Summarizer] Error parsing response for {original_req['item_id']}: {e}"
                                )
                                logger.error(
                                    f"[Summarizer] Input that caused failure - Title: {original_req['title'][:100]}"
                                )
                                logger.error(
                                    f"[Summarizer] Input text length: {len(original_req['text'])} chars, first 500 chars: {original_req['text'][:500]}"
                                )
                                logger.error(
                                    f"[Summarizer] Raw response that failed: {response_text[:1000] if response_text else 'None'}"
                                )
                                results.append(
                                    {
                                        "item_id": original_req["item_id"],
                                        "success": False,
                                        "error": str(e),
                                    }
                                )

                        elif inline_response.error:
                            error_str = str(inline_response.error)
                            logger.error(
                                f"[Summarizer] Item {original_req['item_id']} failed: {error_str}"
                            )

                            # Check for quota errors
                            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                                raise RuntimeError(f"Quota exceeded: {error_str}")

                            results.append(
                                {
                                    "item_id": original_req["item_id"],
                                    "success": False,
                                    "error": error_str,
                                }
                            )

                successful = sum(1 for r in results if r.get("success"))
                logger.info(
                    f"[Summarizer] Chunk {chunk_num} complete: {successful}/{len(results)} successful"
                )

                return results

            except Exception as e:
                error_str = str(e)
                is_quota_error = "429" in error_str or "RESOURCE_EXHAUSTED" in error_str

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
                    logger.error(
                        f"[Summarizer] Chunk {chunk_num} failed after {attempt + 1} attempts: {e}"
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
            required_fields = ["thinking", "summary_markdown", "citizen_impact_markdown", "topics", "confidence"]
            missing_fields = [f for f in required_fields if f not in data]
            if missing_fields:
                logger.error(f"[Summarizer] JSON missing required fields: {missing_fields}")
                raise ValueError(f"Invalid JSON response: missing {missing_fields}")

            # Build comprehensive summary with all components
            thinking = data.get("thinking", "")
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

            if thinking:
                summary_parts.append(f"## Thinking\n\n{thinking}\n")

            if summary_md:
                summary_parts.append(f"## Summary\n\n{summary_md}\n")

            if impact_md:
                summary_parts.append(f"## Citizen Impact\n\n{impact_md}\n")

            if confidence:
                summary_parts.append(f"## Confidence\n\n{confidence}")

            summary = "\n".join(summary_parts)

            logger.debug(
                f"[Summarizer] Parsed JSON response: {len(topics)} valid topics, confidence={confidence}"
            )

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
