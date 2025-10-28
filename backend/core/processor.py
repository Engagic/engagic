"""
PDF Processing Stack for Engagic - Free Tier (Tier 1 Only)

STRATEGY: Fail fast with simple, cost-effective processing
- Tier 1: PyPDF2 + Gemini (60% success rate, ~$0.001/doc, ~2-5s)
- If Tier 1 fails: raise error immediately (document needs paid tier)

Premium tiers (Tier 2 Mistral OCR, Tier 3 Gemini PDF) archived for future use.
See: backend/archived/premium_processing_tiers.py

Key features:
- Smart model selection (Flash vs Flash-Lite based on document size)
- No chunking needed (1M+ token context window)
- Batch processing support for 50% cost savings
- Simple, clean implementation without complex fallback logic
"""

import os
import re
import time
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum

# Google AI
from google import genai
from google.genai import types

# Our modules
from backend.database import UnifiedDatabase
from backend.core.config import config
from backend.core.pdf_extractor import PdfExtractor

logger = logging.getLogger("engagic")

# Model thresholds
FLASH_LITE_MAX_CHARS = 200000  # Use Flash-Lite for documents under ~200K chars
FLASH_LITE_MAX_PAGES = 50      # Or under 50 pages


class ProcessingError(Exception):
    """Base exception for PDF processing errors"""
    pass


class ResultType(Enum):
    """Result type for batch processing"""
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class BatchMessage:
    """Message content from batch processing"""
    content: List[Dict[str, str]]


@dataclass
class BatchResult:
    """Result from batch processing"""
    custom_id: str
    result_type: ResultType
    message: Optional[BatchMessage] = None
    error: Optional[str] = None


class AgendaProcessor:
    """PDF processor optimized for cost and quality"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the processor

        Args:
            api_key: API key (or uses environment variables)
        """
        # Initialize client
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")
        if not self.api_key:
            raise ValueError("API key required - set GEMINI_API_KEY or LLM_API_KEY environment variable")

        # Initialize client (will use GEMINI_API_KEY env var if api_key is None)
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = genai.Client()  # Uses GEMINI_API_KEY from environment

        # Model names for selection
        self.flash_model_name = 'gemini-2.5-flash'
        self.flash_lite_model_name = 'gemini-2.5-flash-lite'

        # Initialize unified database
        self.db = UnifiedDatabase(config.UNIFIED_DB_PATH)

        # Initialize PDF extractor
        self.pdf_extractor = PdfExtractor()

    def process_agenda_with_cache(self, meeting_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point - process agenda with caching
        
        Args:
            meeting_data: Dictionary with packet_url, city_banana, etc.
            
        Returns:
            Dictionary with summary, processing_time, cached flag, etc.
        """
        packet_url = meeting_data.get("packet_url")
        if not packet_url:
            return {"success": False, "error": "No packet_url provided"}
        
        # Extract city context for logging
        city_banana = meeting_data.get("city_banana", "unknown")

        # Check cache first
        cached_meeting = self.db.get_cached_summary(packet_url)
        if cached_meeting:
            logger.info(f"[Cache] HIT - {city_banana}")

            return {
                "success": True,
                "summary": cached_meeting.summary,
                "processing_time": cached_meeting.processing_time or 0,
                "cached": True,
                "meeting_data": cached_meeting.to_dict(),
                "processing_method": cached_meeting.processing_method or "cached"
            }

        # Process with Gemini
        logger.info(f"[Cache] MISS - {city_banana}")
        start_time = time.time()

        try:
            # Process the agenda
            summary, method = self.process_agenda_optimal(packet_url)

            # Store in database
            processing_time = time.time() - start_time
            meeting_data["processed_summary"] = summary
            meeting_data["processing_time_seconds"] = processing_time
            meeting_data["processing_method"] = method

            # Update meeting with summary
            meeting_id = meeting_data.get("meeting_id")
            if meeting_id:
                self.db.update_meeting_summary(meeting_id, summary, method, processing_time)

            # Store in cache
            self._store_in_cache(packet_url, summary, processing_time)

            logger.info(f"[Processing] SUCCESS - {city_banana}")

            return {
                "success": True,
                "summary": summary,
                "processing_time": processing_time,
                "cached": False,
                "meeting_data": meeting_data,
                "meeting_id": meeting_id,
                "processing_method": method
            }

        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"[Processing] FAILED - {city_banana} - {type(e).__name__}: {e}")
            return {
                "success": False,
                "error": str(e),
                "processing_time": processing_time,
                "cached": False
            }
    
    def process_agenda_optimal(self, url: Union[str, List[str]]) -> tuple[str, str]:
        """Process agenda using Tier 1 (PyPDF2 + Gemini) - fail fast approach

        FREE TIER STRATEGY:
        - Try Tier 1: PyPDF2 text extraction + Gemini (60% success rate)
        - If it fails: raise error immediately (no expensive fallbacks)
        - Premium tiers archived in backend/archived/premium_processing_tiers.py

        Args:
            url: Single URL string or list of URLs

        Returns:
            Tuple of (summary, method_used)

        Raises:
            ProcessingError: If Tier 1 fails (document requires paid tier)
        """
        # Handle multiple URLs
        if isinstance(url, list):
            return self._process_multiple_pdfs(url)

        # Tier 1: PyMuPDF extraction + Gemini text API (free tier)
        try:
            result = self.pdf_extractor.extract_from_url(url)
            if result.get('success') and result.get('text'):
                summary = self._summarize_with_gemini(result['text'])
                logger.info(f"[Tier1] SUCCESS - {url}")
                return summary, "tier1_pymupdf_gemini"
            else:
                logger.warning(f"[Tier1] FAILED - No text extracted or poor quality - {url}")

        except Exception as e:
            logger.warning(f"[Tier1] FAILED - {type(e).__name__}: {str(e)} - {url}")

        # Free tier: fail fast (no expensive fallbacks)
        # TODO: When you have paid customers, check subscription tier here
        # and enable Tier 2/3 from backend/archived/premium_processing_tiers.py
        logger.error(f"[Tier1] REJECTED - Requires premium tier - {url}")
        raise ProcessingError(
            "Document requires premium tier for processing. "
            "This PDF may be scanned or have complex formatting that requires OCR."
        )

    # Tier 2 (Mistral OCR) and Tier 3 (Gemini PDF API) archived
    # See: backend/archived/premium_processing_tiers.py for re-enablement

    def _summarize_with_gemini(self, text: str) -> str:
        """Summarize extracted text using Gemini
        
        Args:
            text: Extracted text to summarize
            
        Returns:
            Summary text
        """
        # Determine which model to use based on text size
        text_size = len(text)
        page_count = self._estimate_page_count(text)
        
        if text_size < FLASH_LITE_MAX_CHARS and page_count <= FLASH_LITE_MAX_PAGES:
            model_name = self.flash_lite_model_name
            model_display = "flash-lite"
        else:
            model_name = self.flash_model_name
            model_display = "flash"
        
        logger.info(f"Summarizing {page_count} pages ({text_size} chars) using Gemini {model_display}")
        
        # Get appropriate prompt based on document size
        if page_count <= 30:
            prompt = self._get_short_agenda_prompt(text)
        else:
            prompt = self._get_comprehensive_prompt() + f"\n\nAgenda text:\n{text}"
        
        try:
            # Confidence: 9/10 - Gemini's large context handles everything in one pass
            # Adaptive thinking based on document complexity
            if page_count <= 10 and text_size <= 30000:
                # Easy task: Simple agendas, disable thinking for speed
                logger.info(f"Simple document ({page_count} pages) - disabling thinking for speed")
                config = types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                    thinking_config=types.ThinkingConfig(thinking_budget=0)  # No thinking needed
                )
            elif page_count <= 50 and text_size <= 150000:
                # Medium task: Standard agendas, use moderate thinking
                logger.info(f"Medium document ({page_count} pages) - using moderate thinking")
                if model_name == self.flash_lite_model_name:
                    # Flash-Lite needs explicit budget since it doesn't think by default
                    config = types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=8192,
                        thinking_config=types.ThinkingConfig(thinking_budget=2048)  # Moderate thinking
                    )
                else:
                    # Flash uses dynamic thinking by default
                    config = types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=8192,
                        # Let model decide thinking budget dynamically
                    )
            else:
                # Hard task: Complex documents, use dynamic thinking for best quality
                logger.info(f"Complex document ({page_count} pages) - using dynamic thinking")
                config = types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                    thinking_config=types.ThinkingConfig(thinking_budget=-1)  # Dynamic thinking
                )
            
            response = self.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )

            if response.text is None:
                raise ValueError("Gemini returned no text in response")
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini summarization failed: {e}")
            raise
    
    def _get_short_agenda_prompt(self, text: str) -> str:
        """Get prompt for short agendas"""
        return f"""This is a city council meeting agenda. Provide a clear, concise summary that covers:

**Key Agenda Items:**
- List the main topics/issues being discussed
- Include any public hearings or votes
- Note any budget or financial items

**Important Details:**
- Specific addresses, dollar amounts, ordinance numbers
- Deadlines or implementation dates
- Public participation opportunities

Keep it brief but informative. Focus on what citizens need to know.

Agenda text:
{text}"""
    
    def _get_comprehensive_prompt(self) -> str:
        """Get prompt for comprehensive agenda analysis"""
        return """Analyze this city council meeting agenda and provide a comprehensive summary for residents.

**Complete Agenda Items** (list every single one):
- Item number and full title
- Complete description of what's being proposed
- Department or presenter
- Action required (vote, discussion, information only)

**Financial Details** (every dollar amount):
- Budget items with exact amounts
- Contract values and vendors
- Grant amounts and sources
- Fee changes or rate adjustments

**Property and Development** (all locations):
- Complete addresses for any property discussed
- Zoning changes with current and proposed zoning
- Development project names and descriptions
- Square footage, units, or measurements

**Public Participation**:
- Public hearing items with times
- Comment period details
- How to participate (in person, online, written)
- Deadlines for input

**Key Details to Preserve**:
- Exact dollar amounts (not "several million" but "$3,456,789")
- Complete addresses (not "downtown" but "123 Main Street")
- Full names and titles
- Precise dates and times
- Ordinance and resolution numbers

Format as organized sections with bullet points. Be thorough and detailed.
Skip pure administrative items unless they have significant public impact."""
    
    def _process_multiple_pdfs(self, urls: List[str]) -> tuple[str, str]:
        """Process multiple PDFs by extracting all text first, then summarizing with full context

        Strategy: Most multi-PDF cases are main agenda + supplemental materials.
        The model should reason over the complete context to produce a coherent summary,
        rather than separate summaries concatenated together.
        """
        logger.info(f"Processing {len(urls)} PDFs with combined context")

        # Extract text from all PDFs
        all_text_parts = []
        failed_pdfs = []

        for i, url in enumerate(urls, 1):
            logger.info(f"Extracting text from PDF {i}/{len(urls)}: {url}")
            try:
                result = self.pdf_extractor.extract_from_url(url)
                if result.get('success') and result.get('text'):
                    text = result['text']
                    # Label each document for model context
                    doc_label = "MAIN AGENDA" if i == 1 else f"SUPPLEMENTAL MATERIAL {i-1}"
                    all_text_parts.append(f"=== {doc_label} ===\n{text}")
                    logger.info(f"[PyMuPDF] Extracted {len(text)} chars from document {i}")
                else:
                    logger.warning(f"[PyMuPDF] No text from PDF {i}")
                    failed_pdfs.append(i)
            except Exception as e:
                logger.error(f"[PyMuPDF] Failed to extract from PDF {i}: {type(e).__name__}: {str(e)}")
                failed_pdfs.append(i)

        # If we got no usable text from any PDF, fail fast
        if not all_text_parts:
            logger.error(f"[Tier1] REJECTED - No usable text from any of {len(urls)} PDFs")
            raise ProcessingError(
                f"All {len(urls)} documents require premium tier for processing. "
                "These PDFs may be scanned or have complex formatting that requires OCR."
            )

        # Combine all text and summarize with full context
        combined_text = "\n\n".join(all_text_parts)
        logger.info(f"[Tier1] Combined {len(all_text_parts)}/{len(urls)} documents ({len(combined_text)} chars total)")

        # Summarize with full context (model sees all documents at once)
        summary = self._summarize_with_gemini(combined_text)

        # Note partial failures in the summary if any PDFs couldn't be processed
        if failed_pdfs:
            failure_note = f"\n\n[Note: {len(failed_pdfs)} of {len(urls)} documents could not be processed]"
            summary += failure_note
            logger.warning(f"Partial success: {len(all_text_parts)}/{len(urls)} documents processed")

        return summary, f"multiple_pdfs_{len(urls)}_combined"

    def process_agenda_item(self, item_data: Dict[str, Any], city_banana: str) -> Dict[str, Any]:
        """Process a single agenda item with its attachments

        Args:
            item_data: Dictionary with structure:
                {
                    'item_id': str,
                    'title': str,
                    'sequence': int,
                    'attachments': [{'name': str, 'url': str, 'type': str}, ...]
                }
            city_banana: City identifier for logging

        Returns:
            Dictionary with:
                {
                    'success': bool,
                    'summary': str,
                    'topics': List[str],
                    'processing_time': float,
                    'attachments_processed': int,
                    'error': str (if success=False)
                }
        """
        start_time = time.time()
        item_title = item_data.get('title', 'Untitled Item')
        attachments = item_data.get('attachments', [])

        logger.info(f"[Item] Processing: {item_title[:80]}")

        if not attachments:
            logger.info("[Item] No attachments, skipping processing")
            return {
                'success': True,
                'summary': None,
                'topics': [],
                'processing_time': time.time() - start_time,
                'attachments_processed': 0
            }

        logger.info(f"[Item] Found {len(attachments)} attachment(s)")

        try:
            # Process attachments - handle both URL-based and text segment types
            all_text_parts = []
            processed_count = 0

            for i, att in enumerate(attachments, 1):
                att_type = att.get('type', 'unknown')

                # Case 1: Text segment (from item detection)
                if att_type == 'text_segment':
                    text_content = att.get('content', '')
                    if text_content:
                        all_text_parts.append(text_content)
                        processed_count += 1
                        logger.info(f"[Item] Using text segment ({len(text_content)} chars)")
                    continue

                # Case 2: PDF attachment with URL (from Legistar/adapters)
                if att_type == 'pdf':
                    att_name = att.get('name', f'Attachment {i}')
                    att_url = att.get('url')

                    if not att_url:
                        logger.warning(f"[Item] PDF attachment {i} has no URL, skipping")
                        continue

                    logger.info(f"[Item] Extracting from PDF: {att_name}")

                    try:
                        result = self.pdf_extractor.extract_from_url(att_url)
                        if result.get('success') and result.get('text'):
                            text = result['text']
                            all_text_parts.append(f"=== {att_name} ===\n{text}")
                            processed_count += 1
                            logger.info(f"[PyMuPDF] Extracted {len(text)} chars from {att_name}")
                        else:
                            logger.warning(f"[PyMuPDF] No text from {att_name}")
                    except Exception as e:
                        logger.warning(f"[PyMuPDF] Failed to extract from {att_name}: {e}")
                else:
                    logger.debug(f"[Item] Skipping attachment type: {att_type}")

            # If no usable text, return empty result
            if not all_text_parts:
                logger.warning("[Item] No usable text from any attachment")
                return {
                    'success': False,
                    'error': 'No usable text extracted from attachments',
                    'processing_time': time.time() - start_time,
                    'attachments_processed': 0
                }

            # Combine all attachment text
            combined_text = "\n\n".join(all_text_parts)

            # Generate item summary with topic extraction
            summary, topics = self._summarize_agenda_item(item_title, combined_text)

            processing_time = time.time() - start_time
            logger.info(f"[Item] Processed in {processing_time:.1f}s - {processed_count} attachments, {len(topics)} topics")

            return {
                'success': True,
                'summary': summary,
                'topics': topics,
                'processing_time': processing_time,
                'attachments_processed': processed_count
            }

        except Exception as e:
            logger.error(f"[Item] Processing failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'processing_time': time.time() - start_time,
                'attachments_processed': 0
            }

    def process_batch_items(self, item_requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process multiple agenda items using Gemini Batch API for 50% cost savings.

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

        logger.info(f"[BatchItems] Processing {len(item_requests)} items using Batch API (50% savings)")

        try:
            # Prepare inline requests for Gemini batch
            inline_requests = []
            request_map = {}

            for i, req in enumerate(item_requests):
                item_title = req['title']
                text = req['text']
                text_size = len(text)
                page_count = self._estimate_page_count(text)

                # Build prompt for this item
                prompt = f"""This is a single agenda item from a city council meeting. The item is titled:

"{item_title}"

Based on the attached documents below, provide:

1. A concise 2-3 sentence summary of what this agenda item is about, focusing on:
   - The main action or decision being proposed
   - Key details (amounts, locations, dates)
   - Why it matters to citizens

2. Extract 1-3 main topics discussed in this item (e.g., "affordable housing", "traffic safety", "budget allocation"). Return these as a simple comma-separated list.

Format your response EXACTLY as:

SUMMARY: [your 2-3 sentence summary here]

TOPICS: topic1, topic2, topic3

Attached documents:
{text}"""

                inline_requests.append({
                    'contents': [{
                        'parts': [{'text': prompt}],
                        'role': 'user'
                    }],
                    'config': {
                        'temperature': 0.3,
                        'max_output_tokens': 2048
                    }
                })

                request_map[i] = req

            # Submit to Gemini Batch API
            logger.info(f"[BatchItems] Submitting batch with {len(inline_requests)} items")

            batch_job = self.client.batches.create(
                model=self.flash_model_name,
                src=inline_requests,
                config={
                    'display_name': f"item-batch-{time.time()}"
                }
            )

            batch_name = batch_job.name
            if not batch_name:
                raise ValueError("Batch job created but no name returned")

            logger.info(f"[BatchItems] Submitted batch {batch_name}")

            # Poll for completion
            max_wait_time = 1800  # 30 minutes max
            poll_interval = 10    # Check every 10 seconds
            waited_time = 0

            completed_states = {
                'JOB_STATE_SUCCEEDED',
                'JOB_STATE_FAILED',
                'JOB_STATE_CANCELLED',
                'JOB_STATE_EXPIRED'
            }

            while waited_time < max_wait_time:
                batch_job = self.client.batches.get(name=batch_name)

                if batch_job.state and batch_job.state.name in completed_states:
                    logger.info(f"[BatchItems] Batch {batch_name} completed: {batch_job.state.name}")
                    break

                state_name = batch_job.state.name if batch_job.state else "unknown"
                if waited_time % 30 == 0:  # Log every 30s
                    logger.info(f"[BatchItems] Batch processing... ({waited_time}s, state: {state_name})")

                time.sleep(poll_interval)
                waited_time += poll_interval

            if waited_time >= max_wait_time:
                logger.error(f"[BatchItems] Batch timed out after {max_wait_time}s")
                return [{'item_id': req['item_id'], 'success': False, 'error': 'Batch timeout'} for req in item_requests]

            if not batch_job.state or batch_job.state.name != 'JOB_STATE_SUCCEEDED':
                state_name = batch_job.state.name if batch_job.state else "unknown"
                logger.error(f"[BatchItems] Batch failed: {state_name}")
                return [{'item_id': req['item_id'], 'success': False, 'error': f'Batch failed: {state_name}'} for req in item_requests]

            # Process results
            results = []

            if batch_job.dest and batch_job.dest.inlined_responses:
                for i, inline_response in enumerate(batch_job.dest.inlined_responses):
                    if i not in request_map:
                        logger.warning(f"[BatchItems] No mapping found for response {i}")
                        continue

                    original_req = request_map[i]

                    if inline_response.response:
                        try:
                            # Handle empty/None responses from Gemini
                            response_text = inline_response.response.text
                            if not response_text:
                                logger.warning(f"[BatchItems] Empty response from Gemini for {original_req['item_id']}")
                                results.append({
                                    'item_id': original_req['item_id'],
                                    'success': False,
                                    'error': 'Empty response from Gemini'
                                })
                                continue

                            response_text = response_text.strip()

                            # Parse summary and topics
                            summary = ""
                            topics = []

                            for line in response_text.split('\n'):
                                line = line.strip()
                                if line.startswith('SUMMARY:'):
                                    summary = line.replace('SUMMARY:', '').strip()
                                elif line.startswith('TOPICS:'):
                                    topics_str = line.replace('TOPICS:', '').strip()
                                    topics = [t.strip() for t in topics_str.split(',') if t.strip()]

                            if not summary:
                                summary = response_text[:500]
                                logger.warning(f"[BatchItems] Failed to parse SUMMARY for {original_req['item_id']}")

                            results.append({
                                'item_id': original_req['item_id'],
                                'success': True,
                                'summary': summary,
                                'topics': topics
                            })

                        except Exception as e:
                            logger.error(f"[BatchItems] Error parsing response for {original_req['item_id']}: {e}")
                            results.append({
                                'item_id': original_req['item_id'],
                                'success': False,
                                'error': str(e)
                            })

                    elif inline_response.error:
                        logger.error(f"[BatchItems] Item {original_req['item_id']} failed: {inline_response.error}")
                        results.append({
                            'item_id': original_req['item_id'],
                            'success': False,
                            'error': str(inline_response.error)
                        })

            successful = sum(1 for r in results if r['success'])
            logger.info(f"[BatchItems] Batch complete: {successful}/{len(results)} successful")

            return results

        except Exception as e:
            logger.error(f"[BatchItems] Batch processing failed: {e}")
            # Fallback: return failures for all items
            return [{'item_id': req['item_id'], 'success': False, 'error': str(e)} for req in item_requests]

    def _summarize_agenda_item(self, item_title: str, text: str) -> tuple[str, List[str]]:
        """Summarize a single agenda item and extract topics

        Args:
            item_title: Title of the agenda item
            text: Combined text from all attachments

        Returns:
            Tuple of (summary, topics_list)
        """
        text_size = len(text)
        page_count = self._estimate_page_count(text)

        # Use Flash-Lite for smaller items
        if text_size < FLASH_LITE_MAX_CHARS and page_count <= FLASH_LITE_MAX_PAGES:
            model_name = self.flash_lite_model_name
        else:
            model_name = self.flash_model_name

        logger.info(f"[Item] Summarizing {page_count} pages ({text_size} chars)")

        prompt = f"""This is a single agenda item from a city council meeting. The item is titled:

"{item_title}"

Based on the attached documents below, provide:

1. A concise 2-3 sentence summary of what this agenda item is about, focusing on:
   - The main action or decision being proposed
   - Key details (amounts, locations, dates)
   - Why it matters to citizens

2. Extract 1-3 main topics discussed in this item (e.g., "affordable housing", "traffic safety", "budget allocation"). Return these as a simple comma-separated list.

Format your response EXACTLY as:

SUMMARY: [your 2-3 sentence summary here]

TOPICS: topic1, topic2, topic3

Attached documents:
{text}"""

        try:
            # Simple config for item-level processing
            config = types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=2048
            )

            response = self.client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config
            )

            if not response.text:
                raise ValueError("Gemini returned no text")

            # Parse response
            response_text = response.text.strip()

            # Extract summary and topics
            summary = ""
            topics = []

            for line in response_text.split('\n'):
                line = line.strip()
                if line.startswith('SUMMARY:'):
                    summary = line.replace('SUMMARY:', '').strip()
                elif line.startswith('TOPICS:'):
                    topics_str = line.replace('TOPICS:', '').strip()
                    topics = [t.strip() for t in topics_str.split(',') if t.strip()]

            # Fallback if parsing failed
            if not summary:
                summary = response_text[:500]
                logger.warning("[Item] Failed to parse SUMMARY from response, using truncated text")

            if not topics:
                logger.warning("[Item] No topics extracted from response")

            return summary, topics

        except Exception as e:
            logger.error(f"[Item] Summarization failed: {e}")
            raise

    def combine_item_summaries(self, item_summaries: List[Dict[str, Any]], meeting_title: str) -> str:
        """Combine multiple item summaries into a single meeting summary via concatenation

        Args:
            item_summaries: List of dicts with structure:
                [
                    {'sequence': 1, 'title': '...', 'summary': '...', 'topics': [...]},
                    {'sequence': 2, 'title': '...', 'summary': '...', 'topics': [...]},
                    ...
                ]
            meeting_title: Title of the meeting

        Returns:
            Combined meeting summary string
        """
        logger.info(f"[Combine] Concatenating {len(item_summaries)} item summaries")

        if not item_summaries:
            return "No agenda items were processed for this meeting."

        # Build concatenated summary
        summary_parts = [f"Meeting: {meeting_title}\n"]

        for item in sorted(item_summaries, key=lambda x: x.get('sequence', 0)):
            title = item.get('title', 'Untitled')
            summary = item.get('summary')
            topics = item.get('topics', [])

            if summary:
                topics_str = f" [{', '.join(topics)}]" if topics else ""
                summary_parts.append(f"\n{title}{topics_str}\n{summary}")

        combined = "\n".join(summary_parts)
        logger.info(f"[Combine] Created {len(combined)} char summary from {len(item_summaries)} items")

        return combined

    def _estimate_page_count(self, text: str) -> int:
        """Estimate page count from text"""
        # Look for page markers first
        page_markers = re.findall(r'--- PAGE (\d+) ---', text)
        if page_markers:
            return len(page_markers)

        # Estimate based on character count
        chars_per_page = 3000
        return max(1, len(text) // chars_per_page)

    def detect_agenda_items(self, text: str, max_chunk_size: int = 75000) -> List[Dict[str, Any]]:
        """
        Universal agenda parser with fallback strategies.

        Primary: Structural chunking (cover + body boundary detection)
        Fallback: Two-pass pattern matching (for unstructured agendas)

        Args:
            text: Extracted PDF text
            max_chunk_size: Maximum characters per chunk (default 75K)

        Returns:
            List of detected items: [{'sequence': N, 'title': '...', 'text': '...', 'start_page': N}, ...]
            Empty list if no clear item structure detected
        """
        # Try primary approach: structural chunking
        try:
            chunks = self._chunk_agenda_by_structure(text)
            if chunks:
                logger.info(f"[ItemDetection] Structural chunking succeeded: {len(chunks)} items")
                return chunks
            else:
                logger.debug("[ItemDetection] Structural chunking returned empty, trying fallback")
        except Exception as e:
            logger.warning(f"[ItemDetection] Structural chunking exception: {e}", exc_info=True)

        # Fallback: two-pass pattern matching
        logger.info("[ItemDetection] Falling back to pattern-based detection")
        return self._chunk_agenda_by_patterns(text, max_chunk_size)

    def _chunk_agenda_by_structure(self, pdf_text: str) -> List[Dict[str, Any]]:
        """
        Universal agenda parser. Works by:
        1. Extract cover page agenda listing (source of truth for item metadata)
        2. Find where those items appear in the body text
        3. Split on those boundaries
        """
        # Normalize page breaks and excessive newlines
        text = re.sub(r'\f+', '\n\n', pdf_text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Step 1: Split cover from body
        cover_end = self._detect_cover_end(text)

        cover_text = text[:cover_end]
        body_text = text[cover_end:]

        logger.info(f"[Chunker] Cover ends at {cover_end} ({cover_end/len(text)*100:.1f}% of doc)")

        # Step 2: Extract item metadata from cover
        agenda_items = self._parse_cover_agenda(cover_text)

        if not agenda_items:
            logger.info("[Chunker] No agenda items found in cover")
            return []

        # If cover is suspiciously small but we found items, it might still be valid
        # Only reject if cover is < 0.5% AND we found very few items
        cover_pct = cover_end / len(text)
        if cover_pct < 0.005 and len(agenda_items) < 3:
            logger.info(f"[Chunker] Cover too small ({cover_pct*100:.1f}%) with only {len(agenda_items)} items - likely false detection")
            return []

        logger.info(f"[Chunker] Found {len(agenda_items)} items in cover section")

        # Step 3: Find where cover items appear in body
        boundaries = self._find_item_boundaries_by_title(body_text, agenda_items)

        if not boundaries or len(boundaries) < 2:
            logger.info(f"[Chunker] Insufficient boundaries found by title search (found {len(boundaries) if boundaries else 0})")
            return []

        # Step 4: Create chunks from boundaries
        chunks = []
        for i, boundary in enumerate(boundaries):
            start = boundary['start']
            end = boundaries[i+1]['start'] if i+1 < len(boundaries) else len(body_text)

            content = body_text[start:end].strip()

            if len(content) < 100:  # Skip tiny chunks
                continue

            # Extract page number if available
            page_match = re.search(r'--- PAGE (\d+) ---', content[:500])
            start_page = int(page_match.group(1)) if page_match else None

            chunks.append({
                'sequence': i + 1,
                'title': f"{boundary['item_id']}. {boundary['title']}",
                'text': content,
                'start_page': start_page
            })

        logger.info(f"[Chunker] Created {len(chunks)} chunks from {len(agenda_items)} cover items")

        return chunks if len(chunks) >= 2 else []

    def _detect_cover_end(self, text: str) -> int:
        """
        Find where cover page ends and item content begins.
        Signals: first occurrence of repeating report headers, or large structural shift.
        """
        # Common report header patterns (require newline before for specificity)
        report_headers = [
            r'\n\s*REPORT TO THE',
            r'\n\s*Item \d+\s*\n\s*Staff Report',  # "Item 4\n Staff Report"
            r'\n\s*STAFF REPORT\s*\n',  # Must be on own line
            r'\n\s*ACTION ITEM\s*\n',
        ]

        # Find first strong header
        earliest_pos = len(text)
        found_pattern = None
        for pattern in report_headers:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match and match.start() < earliest_pos:
                earliest_pos = match.start()
                found_pattern = pattern

        if found_pattern:
            logger.debug(f"[CoverEnd] Found pattern '{found_pattern}' at position {earliest_pos}")

        # Better fallback: find first page break after significant content
        if earliest_pos == len(text):
            logger.debug("[CoverEnd] No report headers found, using density analysis")
            # Look for content density change (agenda is dense, reports have whitespace)
            chunks = [text[i:i+2000] for i in range(0, min(len(text), 20000), 2000)]
            for i, chunk in enumerate(chunks[1:], 1):
                # Count newlines per 100 chars as density metric
                density = chunk.count('\n') / (len(chunk) / 100)
                prev_density = chunks[i-1].count('\n') / (len(chunks[i-1]) / 100)
                # Significant drop in density = transition to report content
                if density < prev_density * 0.6:
                    earliest_pos = i * 2000
                    break

            # Ultimate fallback
            if earliest_pos == len(text):
                earliest_pos = int(len(text) * 0.15)

        return earliest_pos

    def _parse_cover_agenda(self, cover_text: str) -> List[Dict[str, Any]]:
        """
        Extract agenda item listing from cover page.
        Handles both same-line and multiline formats:
        - "4. Title here – 45 minutes" (same line)
        - "4.\n    Title here" (multiline - common in Palo Alto, etc.)
        """
        items = []

        # Use regex patterns that work across line boundaries
        # Pattern 1: Numbered items (multiline and same-line)
        numbered_patterns = [
            r'\n\s*(\d+)\.\s*\n\s*([A-Z][^\n]{10,200})',  # "1.\n Title" (multiline)
            r'\n\s*(\d+)\.\s+([A-Z][^\n]{10,200})',       # "1. Title" (same line)
        ]

        for pattern in numbered_patterns:
            for match in re.finditer(pattern, '\n' + cover_text):
                num = int(match.group(1))
                title = match.group(2).strip()

                # Extract duration if present (e.g., "– 45 minutes")
                duration = None
                duration_match = re.search(r'[–—-]\s*(\d+)\s*minutes?', title, re.IGNORECASE)
                if duration_match:
                    duration = int(duration_match.group(1))
                    title = title[:duration_match.start()].strip()

                # Skip if title is too short or looks like junk
                if len(title) < 10 or title.upper() in ['MINUTES', 'AGENDA', 'MEETING', 'REPORTS']:
                    continue

                # Clean up title
                title = re.sub(r'\s+', ' ', title)

                items.append({
                    'item_id': str(num),
                    'item_number': num,
                    'title': title[:150],  # Cap length
                    'duration': duration,
                    'is_subsection': False
                })

        # Dedupe by item_id (prefer first occurrence)
        seen = set()
        deduped = []
        for item in items:
            if item['item_id'] not in seen:
                seen.add(item['item_id'])
                deduped.append(item)

        # Sort by item number
        deduped.sort(key=lambda x: x['item_number'])

        return deduped

    def _find_item_boundaries_by_title(self, body_text: str, agenda_items: List[Dict]) -> List[Dict]:
        """
        Find where each cover agenda item appears in the body text.
        Searches for item titles from cover, using fuzzy matching.
        """
        boundaries = []

        for item in agenda_items:
            title = item['title']
            item_id = item['item_id']

            # Try to find this title in the body
            # First, try exact match (accounting for whitespace differences)
            title_pattern = re.escape(title[:80])  # Use first 80 chars
            title_pattern = title_pattern.replace(r'\ ', r'\s+')  # Allow flexible whitespace

            match = re.search(title_pattern, body_text, re.IGNORECASE)

            if match:
                boundaries.append({
                    'start': match.start(),
                    'item_id': item_id,
                    'title': title,
                    'match_type': 'exact'
                })
                logger.debug(f"[Chunker] Found item {item_id} at position {match.start()}")
            else:
                # Try searching for item number + common headers
                # Pattern: "Item 1" or footer patterns like "Item 1: ... Pg. X of Y"
                num_patterns = [
                    rf'Item\s+{re.escape(item_id)}[\s:]',
                    rf'\n{re.escape(item_id)}\.\s*\n',  # Numbered like "1.\n"
                ]

                for pattern in num_patterns:
                    match = re.search(pattern, body_text, re.IGNORECASE)
                    if match:
                        boundaries.append({
                            'start': match.start(),
                            'item_id': item_id,
                            'title': title,
                            'match_type': 'by_number'
                        })
                        logger.debug(f"[Chunker] Found item {item_id} by number at position {match.start()}")
                        break

        # Sort by position in document
        boundaries.sort(key=lambda x: x['start'])

        return boundaries

    def _detect_item_boundaries(self, body_text: str) -> List[Dict[str, int]]:
        """
        Find where each item starts in the body text.
        Strategy: look for repeating structural markers, prefer strongest patterns.
        """
        all_boundaries = []

        # Common boundary markers (ordered by strength)
        patterns = [
            # Strong: Full report headers
            (r'(?:REPORT TO THE|AGENDA ITEM|Item \d+)', 'header', 0),
            # Medium: Page footers with item IDs
            (r'\n\d+\s*\n\s*(\d+\.?[a-z]?)\s*\n', 'footer', 1),
            # Weak: Repeated structural elements
            (r'(?:RECOMMENDATION|BACKGROUND|FISCAL IMPACT)\s*\n', 'section', 2),
        ]

        # Collect from ALL patterns
        for pattern, marker_type, strength in patterns:
            matches = list(re.finditer(pattern, body_text, re.IGNORECASE | re.MULTILINE))
            if len(matches) >= 2:  # Need multiple occurrences
                for match in matches:
                    all_boundaries.append({
                        'start': match.start(),
                        'strength': strength,
                        'marker_type': marker_type,
                        'text': match.group(0)
                    })

        if not all_boundaries:
            return []

        # Deduplicate by preferring strongest marker at each position
        boundaries = self._dedupe_boundaries_by_strength(all_boundaries)

        # Sort by position
        boundaries.sort(key=lambda x: x['start'])

        return boundaries

    def _dedupe_boundaries_by_strength(self, boundaries: List[Dict]) -> List[Dict]:
        """Remove boundaries that are very close together, keeping strongest."""
        if not boundaries:
            return []

        # Sort by position, then by strength
        boundaries.sort(key=lambda x: (x['start'], x['strength']))

        deduped = [boundaries[0]]

        for boundary in boundaries[1:]:
            # If close to previous (within 100 chars)
            if boundary['start'] - deduped[-1]['start'] <= 100:
                # Keep strongest
                if boundary['strength'] < deduped[-1]['strength']:
                    deduped[-1] = boundary
            else:
                deduped.append(boundary)

        return deduped

    def _extract_item_id_from_content(self, content: str) -> Optional[str]:
        """
        Extract item ID from within the content chunk.
        Look in footers, headers, first lines.
        """
        # Check first 500 chars for item markers
        header = content[:500]

        # Pattern: "Item 4" or "7.a" or "Item 4a"
        patterns = [
            r'Item\s+(\d+[a-z]?)',
            r'^(\d+\.?[a-z]?)\s*$',  # Footer style
            r'Report.*Item\s+(\d+\.?[a-z]?)',
        ]

        for pattern in patterns:
            match = re.search(pattern, header, re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1)

        # Check page footers (last 300 chars)
        footer = content[-300:]
        for pattern in patterns:
            match = re.search(pattern, footer, re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _match_to_agenda(self, detected_id: Optional[str], content: str,
                        agenda_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Match content chunk to cover agenda metadata.
        Uses detected ID, title fuzzy matching, and position.
        """
        # Try exact ID match first
        if detected_id:
            for item in agenda_items:
                if item['item_id'] == detected_id:
                    return item

        # Try fuzzy title match
        content_preview = content[:500].lower()

        for item in agenda_items:
            title_lower = item['title'].lower()
            # Check if title appears in content
            if len(title_lower) > 15 and title_lower in content_preview:
                return item

        # Fallback: return generic metadata
        return {
            'item_id': detected_id or 'unknown',
            'item_number': self._extract_base_number(detected_id) if detected_id else 0,
            'title': self._extract_title_from_content(content),
            'duration': None,
            'is_subsection': False
        }

    def _extract_base_number(self, item_id: str) -> int:
        """Extract number from '7a' -> 7, 'Item 4' -> 4."""
        match = re.search(r'(\d+)', str(item_id))
        return int(match.group(1)) if match else 0

    def _extract_title_from_content(self, content: str) -> str:
        """Extract title from content when no cover match found."""
        # Look for "Report: Title" pattern
        report_match = re.search(r'Report:\s*(.+?)(?:\n|$)', content, re.IGNORECASE)
        if report_match:
            return report_match.group(1).strip()

        # Fallback: first substantial line
        lines = content.split('\n')
        for line in lines[:10]:
            line = line.strip()
            if len(line) > 20 and not line.isupper():
                return line[:100]

        return "Untitled Item"

    def _chunk_agenda_by_patterns(self, text: str, max_chunk_size: int = 75000) -> List[Dict[str, Any]]:
        """
        Fallback pattern-based chunking (original two-pass approach).
        Used when structural chunking fails.
        """
        # PASS 1: Find agenda items in the first portion (likely table of contents)
        # Assume agenda is in first 20% or 50K chars, whichever is smaller
        agenda_section_size = min(int(len(text) * 0.2), 50000)
        agenda_section = text[:agenda_section_size]

        # Find the actual agenda section (between section markers and before content)
        # Common section headers that indicate start of real agenda items
        start_markers = [
            r'BUSINESS\s+ITEMS?',
            r'ACTION\s+ITEMS?',
            r'CONSENT\s+(CALENDAR|AGENDA)',
            r'REGULAR\s+AGENDA',
            r'DISCUSSION\s+ITEMS?',
            r'PUBLIC\s+HEARINGS?',
            r'INFORMATION\s+REPORTS?'
        ]

        # Find where agenda items start (after section markers) - OPTIONAL
        agenda_start = 0
        found_start_marker = False
        for marker_pattern in start_markers:
            match = re.search(marker_pattern, agenda_section, re.IGNORECASE)
            if match and match.start() > agenda_start:
                agenda_start = match.start()
                found_start_marker = True

        # Find where agenda ends (before adjournment or actual content) - OPTIONAL
        end_markers = [
            r'ADJOURNMENT',
            r'^\d+\s+(MINUTES|TRANSCRIPT)',  # Line-numbered minutes/transcripts
            r'Item\s+\d+[:\s]+Staff Report Pg\.',  # Actual item content
        ]

        agenda_end = agenda_section_size
        found_end_marker = False
        for marker_pattern in end_markers:
            match = re.search(marker_pattern, agenda_section[agenda_start:], re.IGNORECASE | re.MULTILINE)
            if match:
                agenda_end = agenda_start + match.start()
                found_end_marker = True
                break

        # Only use narrow range if we found BOTH markers, otherwise search full section
        if found_start_marker and found_end_marker:
            actual_agenda = agenda_section[agenda_start:agenda_end]
            logger.debug(f"[ItemDetection] Using marker-based range: {agenda_start}-{agenda_end}")
        else:
            actual_agenda = agenda_section
            agenda_start = 0
            agenda_end = agenda_section_size
            logger.debug(f"[ItemDetection] No clear markers found, searching full agenda section")

        agenda_patterns = [
            (r"\n\s*(\d+)\.\s*\n\s*([A-Z][^\n]{10,200})", 'numbered'),  # "1.\n Title" (multiline)
            (r"\n\s*(\d+)\.\s+([A-Z][^\n]{10,200})", 'numbered_inline'), # "1. Title" (same line)
            (r"\n\s*([A-Z])\.\s*\n\s*([A-Z][^\n]{10,200})", 'lettered'), # "A.\n Title"
            (r"\n\s*([A-Z])\.\s+([A-Z][^\n]{10,200})", 'lettered_inline'),
            (r"\n\s*(Item\s+\d+)[:\s]+([^\n]{10,200})", 'item'),        # "Item 1: NAME"
        ]

        # Extract agenda items with their titles
        agenda_items = []
        for pattern, item_type in agenda_patterns:
            for match in re.finditer(pattern, actual_agenda, re.IGNORECASE):
                item_num = match.group(1)
                item_title = match.group(2).strip()

                # Skip if this looks like a line number (single word or very short)
                if len(item_title) < 15 or item_title.upper() in ['MINUTES', 'PARKS', 'RECREATION', 'COMMISSION', 'MEETING', 'REGULAR']:
                    continue

                # Clean up title - remove extra whitespace, CEQA status, etc
                item_title = re.sub(r'\s+', ' ', item_title)
                item_title = re.sub(r';?\s*CEQA[^;]*$', '', item_title, flags=re.IGNORECASE)

                agenda_items.append({
                    'number': item_num,
                    'title': item_title[:150],  # Cap title length
                    'type': item_type,
                    'agenda_pos': agenda_start + match.start()
                })

        if not agenda_items:
            logger.info(f"[ItemDetection] No agenda items found in agenda section (searched {len(actual_agenda)} chars between markers)")
            return []

        logger.info(f"[ItemDetection] Found {len(agenda_items)} items in agenda section (between positions {agenda_start}-{agenda_end})")

        # PASS 2: Find where these items appear again in the body
        # Search for item titles in the remainder of the document
        split_points = [0]  # Start of document

        for item in agenda_items:
            # Create search patterns for this item title
            # Try exact match and fuzzy match (accounting for line breaks, extra spaces)
            title_pattern = re.escape(item['title'][:50])  # Use first 50 chars for matching
            title_pattern = title_pattern.replace(r'\ ', r'\s+')  # Allow flexible whitespace

            # Search starting after the agenda section
            search_start = agenda_section_size
            match = re.search(title_pattern, text[search_start:], re.IGNORECASE)

            if match:
                boundary_pos = search_start + match.start()
                split_points.append(boundary_pos)
                logger.debug(f"[ItemDetection] Found '{item['number']}. {item['title'][:40]}...' at position {boundary_pos}")
            else:
                # Fallback: search for just the item number pattern
                num_pattern = rf"\n\s*{re.escape(item['number'])}\.\s+"
                match = re.search(num_pattern, text[search_start:])
                if match:
                    boundary_pos = search_start + match.start()
                    split_points.append(boundary_pos)
                    logger.debug(f"[ItemDetection] Found item {item['number']} (by number only) at position {boundary_pos}")

        split_points = sorted(set(split_points))
        split_points.append(len(text))

        logger.info(f"[ItemDetection] Found {len(split_points) - 2} boundaries in {len(text)} chars document")

        # If too few boundaries found, not worth chunking
        if len(split_points) < 3:  # Need at least 2 items (0, item1, end)
            logger.info(f"[ItemDetection] Only {len(split_points) - 2} boundaries found - processing monolithically")
            return []

        # Create chunks at every boundary
        # Each chunk should correspond to an agenda item's detailed content
        chunks = []
        for i in range(1, len(split_points)):
            chunk_text = text[split_points[i-1]:split_points[i]]

            # Try to match this chunk to an agenda item
            # Find which agenda item this boundary corresponds to
            chunk_start_pos = split_points[i-1]
            matching_item = None

            for item in agenda_items:
                # Check if this chunk starts near where we found this item in the body
                # (We added boundary positions to split_points in pass 2)
                if abs(chunk_start_pos - search_start) < 1000 or chunk_start_pos == 0:
                    # First chunk (before detailed content starts)
                    continue
                # Try to find the item number at the start of this chunk
                chunk_preview = chunk_text[:200]
                if re.search(rf"\n\s*{re.escape(item['number'])}\.\s+", chunk_preview):
                    matching_item = item
                    break

            chunks.append({
                'start_pos': split_points[i-1],
                'end_pos': split_points[i],
                'text': chunk_text,
                'agenda_item': matching_item
            })

        # Filter out chunks that are too small (likely agenda header) and combine if needed
        meaningful_chunks = []
        for chunk in chunks:
            # Skip very small chunks (likely just agenda section)
            if len(chunk['text']) < 1000 and chunk['start_pos'] == 0:
                logger.debug(f"[ItemDetection] Skipping small header chunk ({len(chunk['text'])} chars)")
                continue
            meaningful_chunks.append(chunk)

        if len(meaningful_chunks) <= 1:
            logger.info(f"[ItemDetection] Only {len(meaningful_chunks)} meaningful chunks - processing monolithically")
            return []

        # Cap at reasonable number of chunks
        if len(meaningful_chunks) > 50:
            logger.warning(f"[ItemDetection] {len(meaningful_chunks)} chunks detected - too many! Processing monolithically")
            return []

        logger.info(f"[ItemDetection] Created {len(meaningful_chunks)} chunks from {len(agenda_items)} agenda items")

        # Convert chunks to items with metadata
        result = []
        for i, chunk in enumerate(meaningful_chunks):
            # Use the matched agenda item if we found one
            if chunk['agenda_item']:
                item_num = chunk['agenda_item']['number']
                title = f"{item_num}. {chunk['agenda_item']['title']}"
            else:
                # Fallback: try to extract title from chunk
                title = f"Section {i + 1}"
                chunk_preview = chunk['text'][:300]
                for pattern, _ in agenda_patterns:
                    match = re.search(pattern, chunk_preview, re.IGNORECASE)
                    if match:
                        title_text = match.group(2).strip() if match.lastindex and match.lastindex >= 2 else ""
                        if title_text:
                            title = f"{match.group(1)}. {title_text[:100]}"
                        break

            # Try to extract page number
            page_match = re.search(r'--- PAGE (\d+) ---', chunk['text'][:500])
            start_page = int(page_match.group(1)) if page_match else None

            result.append({
                'sequence': i + 1,
                'title': title,
                'text': chunk['text'],
                'start_page': start_page
            })

        return result
    
    def _update_cache_hit_count(self, packet_url: str):
        """Update cache hit count in cache table"""
        try:
            conn = self.db.conn
            if conn:
                cursor = conn.cursor()
                
                # Serialize packet_url if it's a list
                lookup_url = packet_url
                if isinstance(packet_url, list):
                    lookup_url = json.dumps(packet_url)
                
                cursor.execute("""
                    UPDATE cache 
                    SET cache_hit_count = cache_hit_count + 1,
                        last_accessed = CURRENT_TIMESTAMP
                    WHERE packet_url = ?
                """, (lookup_url,))
                
                conn.commit()
        except Exception as e:
            logger.debug(f"Could not update cache hit count: {e}")
    
    def _store_in_cache(self, packet_url: str, summary: str, processing_time: float):
        """Store processing results in cache table"""
        try:
            conn = self.db.conn
            if conn:
                cursor = conn.cursor()
                
                # Serialize packet_url if it's a list
                lookup_url = packet_url
                if isinstance(packet_url, list):
                    lookup_url = json.dumps(packet_url)
                
                # Generate content hash
                content_hash = hashlib.md5(summary.encode()).hexdigest() if summary else None
                
                cursor.execute("""
                    INSERT OR REPLACE INTO cache
                    (packet_url, content_hash, processing_method,
                     processing_time, cache_hit_count, created_at)
                    VALUES (?, ?, 'tier1_pypdf2_gemini', ?, 0, CURRENT_TIMESTAMP)
                """, (
                    lookup_url,
                    content_hash,
                    processing_time
                ))
                
                conn.commit()
                logger.debug(f"Stored in cache: {packet_url}")
        except Exception as e:
            logger.error(f"Failed to store in cache: {e}")
    
    def process_batch_agendas(
        self, 
        batch_requests: List[Dict[str, str]], 
        wait_for_results: bool = True,
        return_raw: bool = False
    ) -> List[Dict[str, Any]]:
        """Process multiple agendas using Gemini's Batch API for 50% cost savings
        
        Args:
            batch_requests: List of {"url": packet_url, "custom_id": custom_id}
            wait_for_results: Whether to wait for batch completion (default True)
            return_raw: Whether to return raw batch results (default False)
            
        Returns:
            List of processing results matching the input custom_ids
        """
        if not batch_requests:
            return []
            
        logger.info(f"Processing {len(batch_requests)} agendas using Gemini Batch API (50% cost savings)")
        
        try:
            # Prepare inline requests for Gemini batch
            inline_requests = []
            request_map = {}  # Map custom_id to original request
            
            for req in batch_requests:
                try:
                    # Handle both single URLs and lists of URLs
                    urls = req["url"] if isinstance(req["url"], list) else [req["url"]]
                    
                    # Extract text from all URLs
                    all_texts = []
                    for url in urls:
                        result = self.pdf_extractor.extract_from_url(url)
                        if result.get('success') and result.get('text'):
                            text = result['text']
                            # Validate text quality using the extractor's validator
                            if self.pdf_extractor.validate_text(text):
                                all_texts.append(text)
                    
                    if not all_texts:
                        logger.warning(f"Skipping {req['custom_id']} - failed text extraction from all URLs")
                        continue
                    
                    # Combine all texts
                    text = "\n\n--- NEXT DOCUMENT ---\n\n".join(all_texts)
                    
                    # Get appropriate prompt based on document size
                    page_count = self._estimate_page_count(text)
                    if page_count <= 30:
                        prompt = self._get_short_agenda_prompt(text)
                    else:
                        prompt = self._get_comprehensive_prompt() + f"\n\nAgenda text:\n{text}"
                    
                    # Create inline request for Gemini batch
                    inline_requests.append({
                        'contents': [{
                            'parts': [{'text': prompt}],
                            'role': 'user'
                        }],
                        'config': {
                            'temperature': 0.3,
                            'max_output_tokens': 8192
                        }
                    })
                    
                    # Store mapping for result processing
                    request_map[len(inline_requests) - 1] = req
                    
                except Exception as e:
                    logger.error(f"Error preparing batch request for {req['custom_id']}: {e}")
                    continue
            
            if not inline_requests:
                logger.warning("No valid batch requests to process")
                return []
            
            # Submit to Gemini Batch API
            # Confidence: 9/10 - Using inline requests for smaller batches
            batch_job = self.client.batches.create(
                model=self.flash_model_name,  # Use Flash for batch processing
                src=inline_requests,
                config={
                    'display_name': f"agenda-batch-{time.time()}"
                }
            )

            batch_name = batch_job.name
            if not batch_name:
                raise ValueError("Batch job created but no name returned")
            logger.info(f"Submitted batch {batch_name} with {len(inline_requests)} requests")
            
            if not wait_for_results:
                return [{"batch_id": batch_name, "status": "submitted"}]
            
            # Poll for completion
            max_wait_time = 3600  # 1 hour max wait
            poll_interval = 30    # Check every 30 seconds
            waited_time = 0
            
            completed_states = {
                'JOB_STATE_SUCCEEDED',
                'JOB_STATE_FAILED', 
                'JOB_STATE_CANCELLED',
                'JOB_STATE_EXPIRED'
            }
            
            while waited_time < max_wait_time:
                batch_job = self.client.batches.get(name=batch_name)

                if batch_job.state and batch_job.state.name in completed_states:
                    logger.info(f"Batch {batch_name} completed with state: {batch_job.state.name}")
                    break

                state_name = batch_job.state.name if batch_job.state else "unknown"
                logger.info(f"Batch {batch_name} still processing... ({waited_time}s waited, state: {state_name})")
                time.sleep(poll_interval)
                waited_time += poll_interval

            if waited_time >= max_wait_time:
                logger.error(f"Batch {batch_name} timed out after {max_wait_time}s")
                return []

            if not batch_job.state or batch_job.state.name != 'JOB_STATE_SUCCEEDED':
                state_name = batch_job.state.name if batch_job.state else "unknown"
                logger.error(f"Batch {batch_name} failed with state: {state_name}")
                if batch_job.error:
                    logger.error(f"Error details: {batch_job.error}")
                return []
            
            # Process results
            results = []
            
            if batch_job.dest and batch_job.dest.inlined_responses:
                for i, inline_response in enumerate(batch_job.dest.inlined_responses):
                    if i not in request_map:
                        logger.warning(f"No mapping found for response index {i}")
                        continue
                    
                    original_req = request_map[i]
                    
                    if inline_response.response:
                        try:
                            # Extract summary text from response
                            summary = inline_response.response.text
                            
                            # Create result object matching expected format
                            result = BatchResult(
                                custom_id=original_req["custom_id"],
                                result_type=ResultType.SUCCEEDED,
                                message=BatchMessage(content=[{'text': summary or ""}]),
                                error=None
                            )
                            
                            results.append(result)
                            logger.info(f"Successfully processed {original_req['custom_id']}")
                            
                        except Exception as e:
                            logger.error(f"Error extracting response for {original_req['custom_id']}: {e}")
                            
                            result = BatchResult(
                                custom_id=original_req["custom_id"],
                                result_type=ResultType.FAILED,
                                message=None,
                                error=str(e)
                            )
                            
                            results.append(result)
                    
                    elif inline_response.error:
                        logger.error(f"Batch item {original_req['custom_id']} failed: {inline_response.error}")
                        
                        result = BatchResult(
                            custom_id=original_req["custom_id"],
                            result_type=ResultType.FAILED,
                            message=None,
                            error=str(inline_response.error)
                        )
                        
                        results.append(result)
            
            successful_count = sum(1 for r in results if r.result_type == ResultType.SUCCEEDED)
            logger.info(f"Batch processing complete: {successful_count}/{len(results)} successful")
            
            return results
            
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            
            # Fallback to individual processing
            logger.info("Falling back to individual processing")
            results = []
            for req in batch_requests:
                try:
                    summary, method = self.process_agenda_optimal(req["url"])
                    
                    result = BatchResult(
                        custom_id=req["custom_id"],
                        result_type=ResultType.SUCCEEDED,
                        message=BatchMessage(content=[{'text': summary}]),
                        error=None
                    )
                    
                    results.append(result)
                    
                except Exception as e:
                    logger.error(f"Individual processing failed for {req['custom_id']}: {e}")
                    
                    result = BatchResult(
                        custom_id=req["custom_id"],
                        result_type=ResultType.FAILED,
                        message=None,
                        error=str(e)
                    )
                    
                    results.append(result)
            
            return results


def create_processor(**kwargs) -> AgendaProcessor:
    """Create a processor instance"""
    return AgendaProcessor(**kwargs)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python gemini_processor.py <pdf_url>")
        sys.exit(1)
    
    processor = create_processor()
    
    test_url = sys.argv[1]
    summary, method = processor.process_agenda_optimal(test_url)
    
    print("=== SUMMARY ===")
    print(summary)
    print("\n=== PROCESSING INFO ===")
    print(f"Method: {method}")