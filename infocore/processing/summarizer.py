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

        # Load prompts from JSON (use v2 by default, fallback to v1)
        if prompts_path is None:
            prompts_v2_file = Path(__file__).parent / "prompts_v2.json"
            prompts_v1_file = Path(__file__).parent / "prompts.json"

            if prompts_v2_file.exists():
                prompts_file = prompts_v2_file
                self.prompts_version = "v2"
                logger.info("[Summarizer] Using prompts_v2.json (JSON structured output)")
            else:
                prompts_file = prompts_v1_file
                self.prompts_version = "v1"
                logger.info("[Summarizer] Using prompts.json (legacy text parsing)")
        else:
            prompts_file = Path(prompts_path)
            self.prompts_version = "custom"

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

    def summarize_item(self, item_title: str, text: str) -> Tuple[str, List[str]]:
        """Summarize a single agenda item and extract topics

        Args:
            item_title: Title of the agenda item
            text: Combined text from all attachments

        Returns:
            Tuple of (summary, topics_list) for backwards compatibility
            With v2 prompts, summary includes thinking trace and markdown formatting
        """
        text_size = len(text)
        page_count = self._estimate_page_count(text)

        # Model selection
        if text_size < FLASH_LITE_MAX_CHARS and page_count <= FLASH_LITE_MAX_PAGES:
            model_name = self.flash_lite_model_name
        else:
            model_name = self.flash_model_name

        logger.info(
            f"[Summarizer] Summarizing item '{item_title[:50]}...' ({page_count} pages, {text_size} chars)"
        )

        # Get prompt and config
        prompt = self._get_prompt("item", "standard", title=item_title, text=text)

        # Check if using v2 prompts with JSON schema
        if self.prompts_version == "v2":
            # Use JSON structured output with schema
            response_schema = self.prompts["item"]["standard"].get("response_schema")
            config = types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=2048,
                response_mime_type="application/json",
                response_schema=response_schema
            )
        else:
            # Legacy text output
            config = types.GenerateContentConfig(temperature=0.3, max_output_tokens=2048)

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

        Args:
            item_requests: List of dicts with structure:
                [{
                    'item_id': str,
                    'title': str,
                    'text': str,  # Pre-extracted and concatenated text
                    'sequence': int
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

        logger.info(
            f"[Summarizer] Processing {len(item_requests)} items using Batch API (50% savings)"
        )

        try:
            # Prepare inline requests
            inline_requests = []
            request_map = {}

            for i, req in enumerate(item_requests):
                item_title = req["title"]
                text = req["text"]

                # Build prompt
                prompt = self._get_prompt(
                    "item", "standard", title=item_title, text=text
                )

                # Build config based on version
                if self.prompts_version == "v2":
                    response_schema = self.prompts["item"]["standard"].get("response_schema")
                    config = {
                        "temperature": 0.3,
                        "max_output_tokens": 2048,
                        "response_mime_type": "application/json",
                        "response_schema": response_schema
                    }
                else:
                    config = {"temperature": 0.3, "max_output_tokens": 2048}

                inline_requests.append(
                    {
                        "contents": [{"parts": [{"text": prompt}], "role": "user"}],
                        "config": config,
                    }
                )

                request_map[i] = req

            # Submit batch job
            logger.info(
                f"[Summarizer] Submitting batch with {len(inline_requests)} items"
            )

            batch_job = self.client.batches.create(
                model=self.flash_model_name,
                src=inline_requests,
                config={"display_name": f"item-batch-{time.time()}"},
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
                logger.error(f"[Summarizer] Batch timed out after {max_wait_time}s")
                return [
                    {
                        "item_id": req["item_id"],
                        "success": False,
                        "error": "Batch timeout",
                    }
                    for req in item_requests
                ]

            if not batch_job.state or batch_job.state.name != "JOB_STATE_SUCCEEDED":
                state_name = batch_job.state.name if batch_job.state else "unknown"
                logger.error(f"[Summarizer] Batch failed: {state_name}")
                return [
                    {
                        "item_id": req["item_id"],
                        "success": False,
                        "error": f"Batch failed: {state_name}",
                    }
                    for req in item_requests
                ]

            # Process results
            results = []

            if batch_job.dest and batch_job.dest.inlined_responses:
                for i, inline_response in enumerate(batch_job.dest.inlined_responses):
                    if i not in request_map:
                        logger.warning(
                            f"[Summarizer] No mapping found for response {i}"
                        )
                        continue

                    original_req = request_map[i]

                    if inline_response.response:
                        try:
                            response_text = inline_response.response.text
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
                            summary, topics = self._parse_item_response(response_text)

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
                            results.append(
                                {
                                    "item_id": original_req["item_id"],
                                    "success": False,
                                    "error": str(e),
                                }
                            )

                    elif inline_response.error:
                        logger.error(
                            f"[Summarizer] Item {original_req['item_id']} failed: {inline_response.error}"
                        )
                        results.append(
                            {
                                "item_id": original_req["item_id"],
                                "success": False,
                                "error": str(inline_response.error),
                            }
                        )

            successful = sum(1 for r in results if r["success"])
            logger.info(
                f"[Summarizer] Batch complete: {successful}/{len(results)} successful"
            )

            return results

        except Exception as e:
            logger.error(f"[Summarizer] Batch processing failed: {e}")
            return [
                {"item_id": req["item_id"], "success": False, "error": str(e)}
                for req in item_requests
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
            response_text: Raw response from Gemini (JSON for v2, text for v1)

        Returns:
            Tuple of (summary, topics_list)

        For v2 prompts with JSON:
            summary = Combined markdown with thinking trace, summary, and citizen impact
            topics = List of canonical topic strings
        """
        response_text = response_text.strip()

        # v2: JSON structured output
        if self.prompts_version == "v2":
            try:
                data = json.loads(response_text)

                # Build comprehensive summary with all components
                thinking = data.get("thinking", "")
                summary_md = data.get("summary_markdown", "")
                impact_md = data.get("citizen_impact_markdown", "")
                confidence = data.get("confidence", "unknown")

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
                topics = data.get("topics", [])

                logger.debug(
                    f"[Summarizer] Parsed JSON response: {len(topics)} topics, confidence={confidence}"
                )

                return summary, topics

            except json.JSONDecodeError as e:
                logger.error(f"[Summarizer] Failed to parse JSON response: {e}")
                logger.debug(f"[Summarizer] Response text: {response_text[:200]}...")
                # Fallback to legacy parsing

        # v1: Legacy text parsing
        summary = ""
        topics = []

        for line in response_text.split("\n"):
            line = line.strip()
            if line.startswith("SUMMARY:"):
                summary = line.replace("SUMMARY:", "").strip()
            elif line.startswith("TOPICS:"):
                topics_str = line.replace("TOPICS:", "").strip()
                topics = [t.strip() for t in topics_str.split(",") if t.strip()]

        # Fallback if parsing failed
        if not summary:
            summary = response_text[:500]
            logger.warning(
                "[Summarizer] Failed to parse response, using truncated text"
            )

        if not topics:
            logger.debug("[Summarizer] No topics extracted from response")

        return summary, topics

    def _estimate_page_count(self, text: str) -> int:
        """Estimate page count from text

        Args:
            text: Extracted text

        Returns:
            Estimated page count
        """
        # Rough estimate: ~2000 chars per page
        return max(1, len(text) // 2000)
