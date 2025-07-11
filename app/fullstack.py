"""Engagic Agenda Processor - Process city council meeting packets using Claude's PDF API

This module provides comprehensive PDF processing capabilities with multiple methods:
1. URL-based processing (fastest, no download required)
2. Base64 processing with caching (download once, cache for reuse)
3. Files API processing (upload once, reference multiple times)
4. OCR fallback for problematic PDFs

Key Features:
- Automatic method selection with fallback chain
- Token usage estimation
- Batch processing for high-volume workflows
- Database caching of processed summaries
- Support for multi-document agendas
"""

import os
import time
import logging
import anthropic
import argparse
import sys
from typing import List, Dict, Any, Union
from databases import DatabaseManager
from config import config
from pdf_api_processor import (
    PDFAPIProcessor,
    MAX_PDF_API_PAGES,
    BatchAccumulator,
    BatchResult,
    ResultType,
)
from pdf_ocr_extractor import PDFOCRExtractor, validate_url, sanitize_filename
import requests

logger = logging.getLogger("engagic")

# PDF download size limit (for download_packet method)
MAX_PDF_SIZE = 200 * 1024 * 1024  # 200MB max PDF size


class AgendaProcessor:
    def __init__(self, api_key=None, db_path="/root/engagic/app/meetings.db"):
        """Initialize processor with optional API key and database"""
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        if not self.api_key:
            raise ValueError("LLM_API_KEY environment variable required")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.db = DatabaseManager(
            locations_db_path=config.LOCATIONS_DB_PATH,
            meetings_db_path=config.MEETINGS_DB_PATH,
            analytics_db_path=config.ANALYTICS_DB_PATH,
        )

        # Initialize both PDF processors
        # Can configure to use Files API by default with use_files_api=True
        self.pdf_api_processor = PDFAPIProcessor(self.api_key, use_files_api=False)
        self.pdf_ocr_extractor = PDFOCRExtractor()

        # Initialize batch accumulator for efficient processing
        self.batch_accumulator = BatchAccumulator(
            self.pdf_api_processor,
            batch_size=50,  # Submit when 50 PDFs accumulated
            wait_time=300,  # Or after 5 minutes
            auto_submit=True,
        )

    def _process_with_pdf_api(self, url, method="url"):
        """Try to process PDF using the new PDF API with multiple methods"""
        try:
            # Log token estimation if single URL
            if isinstance(url, str):
                # Try to get page count from PDF metadata (simplified estimation)
                valid, _, size = self.pdf_api_processor.validate_pdf_for_api(url)
                if size:
                    # Rough estimate: 3KB per page
                    estimated_pages = min(size // 3000, MAX_PDF_API_PAGES)
                    token_estimate = self.pdf_api_processor.estimate_tokens(
                        estimated_pages
                    )
                    logger.info(
                        f"Estimated token usage: {token_estimate['total_tokens']:,} tokens for ~{estimated_pages} pages"
                    )

            summary = self.pdf_api_processor.process(url, method=method)
            logger.info(f"Successfully processed with PDF API ({method} method)")
            return summary, f"pdf_api_{method}"
        except Exception as e:
            logger.warning(f"PDF API processing failed with {method} method: {e}")
            raise

    def _process_with_ocr(self, url, english_threshold=0.7):
        """Fallback to OCR-based processing"""
        try:
            logger.info("Falling back to OCR-based processing...")

            # Extract and clean text
            cleaned_text = self.pdf_ocr_extractor.process(url, english_threshold)

            # Summarize
            logger.info("Starting OCR text summarization...")
            summary = self.summarize(cleaned_text)

            logger.info("Successfully processed with OCR")
            return summary, "ocr"
        except Exception as e:
            logger.error(f"OCR processing also failed: {e}")
            raise

    # OCR methods removed - now using pdf_ocr_extractor module
    # All OCR functionality has been moved to pdf_ocr_extractor.py

    def summarize(self, text: str, rate_limit_delay: int = 5) -> str:
        """Summarize text with improved prompting"""
        # Estimate document size based on text length
        text_length = len(text)
        estimated_pages = text_length // 3000  # Rough estimate
        logger.info(
            f"Document has approximately {estimated_pages} pages ({text_length} characters)"
        )

        # Use different approach for short documents
        if text_length < 90000:  # Roughly 30 pages
            return self._summarize_short_agenda(text, rate_limit_delay)
        else:
            return self._summarize_long_agenda(text, rate_limit_delay)

    def _summarize_short_agenda(self, text: str, rate_limit_delay: int = 5) -> str:
        """Summarize short agendas (<=10 pages) with simplified prompt"""
        logger.info("Using short agenda summarization approach")

        # Check if we have meaningful content to summarize
        cleaned_lines = [line.strip() for line in text.split("\n") if line.strip()]
        content_lines = [
            line
            for line in cleaned_lines
            if not line.startswith("[") and not line.startswith("---")
        ]

        if len(content_lines) < 10:
            logger.warning("Insufficient content extracted from PDF")
            return "Unable to extract meaningful content from this PDF. The document may be a scanned image without searchable text, or it may use a format that prevents text extraction."

        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=3000,
                messages=[
                    {
                        "role": "user",
                        "content": f"""This is a short city council meeting agenda. Provide a clear, concise summary that covers:

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
                        {text}""",
                    }
                ],
            )

            return response.content[0].text  # type: ignore

        except Exception as e:
            logger.error(f"Error processing short agenda: {e}")
            return "Unable to process this agenda due to a technical error. Please try again later."

    def _summarize_long_agenda(self, text: str, rate_limit_delay: int = 5) -> str:
        """Summarize long agendas (>30 pages) using direct approach"""
        logger.info("Using long agenda summarization approach")

        # Check if we have meaningful content to summarize
        cleaned_lines = [line.strip() for line in text.split("\n") if line.strip()]
        content_lines = [
            line
            for line in cleaned_lines
            if not line.startswith("[") and not line.startswith("---")
        ]

        if len(content_lines) < 20:
            logger.warning("Insufficient content extracted from PDF")
            return "Unable to extract meaningful content from this PDF. The document may be a scanned image without searchable text, or it may use a format that prevents text extraction."

        # For long documents, we'll summarize directly without chunking
        # The new PDF API can handle large documents better
        logger.info("Processing long document with comprehensive summary approach")

        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                messages=[
                    {
                        "role": "user",
                        "content": f"""This is a long city council meeting agenda packet. Please provide a comprehensive summary that covers:

                        **Major Agenda Items:**
                        - List all significant topics/issues being discussed with key details
                        - Include any public hearings, votes, or major decisions
                        - Note budget items, financial impacts, and dollar amounts

                        **Public Impact:**
                        - How these items affect residents' daily lives
                        - Specific addresses, developments, or areas affected
                        - Timing, deadlines, or implementation dates

                        **Public Participation:**
                        - Opportunities for public comment or hearings
                        - How residents can get involved

                        Format as organized sections with bullet points. Preserve specific details like addresses, dollar amounts, ordinance numbers, and dates. 
                        Focus on items that matter to citizens while skipping pure administrative matters.

                        Agenda text:
                        {text[:75000]}""",  # Limit to reasonable size for API
                    }
                ],
            )

            return response.content[0].text  # type: ignore

        except Exception as e:
            logger.error(f"Error processing long agenda: {e}")
            return "Unable to process this large agenda document. The file may be too complex or contain formatting that prevents proper analysis."

    def process_agenda_with_cache(
        self, meeting_data: Dict[str, Any], pdf_method: str = "auto"
    ) -> Dict[str, Any]:
        """Process agenda with database caching - main entry point for cached processing

        Args:
            meeting_data: Meeting information including packet_url
            pdf_method: PDF processing method (auto, url, base64, files, ocr)
        """
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
                "processing_method": cached_meeting.get("processing_method", "unknown"),
            }

        # Cache miss - process the agenda
        logger.info(f"Cache miss for {packet_url} - processing...")
        start_time = time.time()

        try:
            # Get city info using city_banana
            city_banana = meeting_data.get("city_banana")
            city_info = self.db.get_city_by_banana(city_banana) if city_banana else {}

            # Merge meeting data with city info
            full_meeting_data = {**meeting_data, **city_info}
            summary = self.process_agenda(
                packet_url, save_raw=False, save_cleaned=False, pdf_method=pdf_method
            )
            processing_time = time.time() - start_time

            # Track which method succeeded
            processing_method = pdf_method
            if pdf_method == "auto":
                # Try to determine which method actually worked based on logs
                # This is simplified - in production you'd track this properly
                processing_method = "pdf_api"  # Default assumption

            # Store in database with processing method
            full_meeting_data["processing_method"] = processing_method
            vendor = meeting_data.get("vendor")
            meeting_id = self.db.store_meeting_summary(
                full_meeting_data, summary, processing_time
            )

            logger.info(
                f"Processed and cached agenda {packet_url} in {processing_time:.1f}s using {processing_method} (ID: {meeting_id})"
            )

            return {
                "summary": summary,
                "processing_time": processing_time,
                "cached": False,
                "meeting_data": full_meeting_data,
                "meeting_id": meeting_id,
                "processing_method": processing_method,
            }

        except Exception as e:
            logger.error(f"Error processing agenda {packet_url}: {e}")
            raise

    def process_agenda(
        self,
        url,  # Can be string or list
        english_threshold: float = 0.7,
        save_raw: bool = True,
        save_cleaned: bool = True,
        pdf_method: str = "auto",  # auto, url, base64, files, ocr
    ) -> str:
        """Complete pipeline with multiple PDF processing approaches

        Args:
            url: PDF URL or list of URLs
            english_threshold: For OCR fallback
            save_raw: Save raw text output
            save_cleaned: Save cleaned text output
            pdf_method: Processing method - auto (tries url->base64->ocr), url, base64, files, or ocr
        """

        if pdf_method == "auto":
            # Try URL method first (fastest, no download)
            try:
                summary, method = self._process_with_pdf_api(url, "url")
                logger.info(f"Successfully processed using {method}")

                if save_raw or save_cleaned:
                    self._save_text(summary, "agenda_summary.txt")
                    logger.info("Complete! Summary saved to agenda_summary.txt")

                return summary

            except Exception as url_error:
                logger.warning(f"URL method failed: {url_error}")

                # Try base64 with caching (download once, cache for reuse)
                try:
                    summary, method = self._process_with_pdf_api(url, "base64")
                    logger.info(f"Successfully processed using {method}")

                    if save_raw or save_cleaned:
                        self._save_text(summary, "agenda_summary.txt")
                        logger.info("Complete! Summary saved to agenda_summary.txt")

                    return summary

                except Exception as base64_error:
                    logger.warning(f"Base64 method failed: {base64_error}")

                    # Final fallback to OCR
                    try:
                        summary, method = self._process_with_ocr(url, english_threshold)
                        logger.info(f"Successfully processed using {method}")

                        if save_raw or save_cleaned:
                            self._save_text(summary, "agenda_summary.txt")
                            logger.info("Complete! Summary saved to agenda_summary.txt")

                        return summary

                    except Exception as ocr_error:
                        logger.error("All processing methods failed")
                        logger.error(f"URL error: {url_error}")
                        logger.error(f"Base64 error: {base64_error}")
                        logger.error(f"OCR error: {ocr_error}")

                        # Return a user-friendly error message
                        return "Unable to process this PDF document. The file may be corrupted, password-protected, or in an unsupported format."

        elif pdf_method == "ocr":
            # Direct OCR processing
            try:
                summary, method = self._process_with_ocr(url, english_threshold)
                logger.info(f"Successfully processed using {method}")

                if save_raw or save_cleaned:
                    self._save_text(summary, "agenda_summary.txt")
                    logger.info("Complete! Summary saved to agenda_summary.txt")

                return summary

            except Exception as e:
                logger.error(f"OCR processing failed: {e}")
                return "Unable to process this PDF document using OCR."

        else:
            # Use specified PDF API method
            try:
                summary, method = self._process_with_pdf_api(url, pdf_method)
                logger.info(f"Successfully processed using {method}")

                if save_raw or save_cleaned:
                    self._save_text(summary, "agenda_summary.txt")
                    logger.info("Complete! Summary saved to agenda_summary.txt")

                return summary

            except Exception as e:
                logger.error(f"{pdf_method} method failed: {e}")

                # Try OCR as fallback unless explicitly disabled
                if pdf_method != "ocr":
                    try:
                        logger.info("Falling back to OCR...")
                        summary, method = self._process_with_ocr(url, english_threshold)
                        logger.info(f"Successfully processed using {method}")

                        if save_raw or save_cleaned:
                            self._save_text(summary, "agenda_summary.txt")
                            logger.info("Complete! Summary saved to agenda_summary.txt")

                        return summary
                    except Exception as ocr_error:
                        logger.error(f"OCR fallback also failed: {ocr_error}")

                return f"Unable to process PDF using {pdf_method} method."

    def _save_text(self, text: str, filename: str) -> None:
        """Save text to file with UTF-8 encoding"""
        # Sanitize filename to prevent directory traversal
        safe_filename = sanitize_filename(filename)
        with open(safe_filename, "w", encoding="utf-8") as f:
            f.write(text)
        logger.info(f"Saved to {safe_filename} ({len(text)} characters)")

    def download_packet(self, url: str, output_path: str = None) -> str:
        """Download PDF packet and save to file"""
        # Validate URL for security
        validate_url(url)

        if not output_path:
            output_path = "downloaded_packet.pdf"

        # Sanitize output path
        safe_output_path = sanitize_filename(output_path)

        logger.info(f"Downloading packet from: {url[:80]}...")

        try:
            # Download with streaming and size limit
            response = requests.get(
                url,
                timeout=30,
                stream=True,
                headers={"User-Agent": "Engagic-Agenda-Processor/1.0"},
            )
            response.raise_for_status()

            # Check content length
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_PDF_SIZE:
                raise ValueError(
                    f"PDF size {content_length} exceeds maximum allowed size of {MAX_PDF_SIZE} bytes"
                )

            # Download with size checking
            pdf_content = b""
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded > MAX_PDF_SIZE:
                        raise ValueError(
                            f"PDF size exceeds maximum allowed size of {MAX_PDF_SIZE} bytes"
                        )
                    pdf_content += chunk

        except requests.RequestException as e:
            raise Exception(f"Failed to download PDF: {e}")

        with open(safe_output_path, "wb") as f:
            f.write(pdf_content)

        logger.info(f"Packet saved to {safe_output_path} ({len(pdf_content)} bytes)")
        return safe_output_path

    def process_batch_agendas(
        self,
        pdf_requests: List[Dict[str, Any]],
        wait_for_results: bool = True,
        return_raw: bool = False,
    ) -> Union[str, List[Dict[str, Any]], List[BatchResult]]:
        """Process multiple agendas using batch API with full support

        Args:
            pdf_requests: List of dicts with 'url' and optional 'prompt', 'custom_id', 'model' keys
            wait_for_results: If True, wait for completion and return results
            return_raw: If True, return raw BatchResult objects; otherwise return summaries

        Returns:
            If wait_for_results=False: Batch job ID for tracking
            If wait_for_results=True and return_raw=True: List of BatchResult objects
            If wait_for_results=True and return_raw=False: List of processed summaries
        """
        logger.info(f"Processing batch of {len(pdf_requests)} agendas")

        try:
            # Enhanced validation with model selection
            valid_requests = []
            for i, req in enumerate(pdf_requests):
                url = req.get("url")
                if not url:
                    logger.warning(f"Request {i} missing 'url' field, skipping")
                    continue

                valid, error_msg, size = self.pdf_api_processor.validate_pdf_for_api(
                    url
                )
                if not valid:
                    logger.warning(f"PDF {i} validation failed: {error_msg}")
                    continue

                # Add size info for model selection
                req["_size"] = size
                valid_requests.append(req)

            if not valid_requests:
                raise ValueError("No valid PDFs to process")

            logger.info(
                f"Processing {len(valid_requests)} valid PDFs out of {len(pdf_requests)} total"
            )

            # Submit batch job with enhanced options
            result = self.pdf_api_processor.process_batch(
                valid_requests,
                wait_for_completion=wait_for_results,
                use_prompt_caching=True,
            )

            if not wait_for_results:
                # Return batch ID for async tracking
                return result

            # Process results
            if return_raw:
                return result  # List[BatchResult]

            # Extract summaries and handle errors
            processed_results = []
            for batch_result in result:
                if batch_result.result_type == ResultType.SUCCEEDED:
                    summary = batch_result.message.get("content", [{}])[0].get(
                        "text", ""
                    )
                    processed_results.append(
                        {
                            "custom_id": batch_result.custom_id,
                            "status": "success",
                            "summary": summary,
                            "usage": batch_result.usage,
                        }
                    )
                else:
                    processed_results.append(
                        {
                            "custom_id": batch_result.custom_id,
                            "status": "error",
                            "error": batch_result.error
                            or f"Request {batch_result.result_type.value}",
                        }
                    )

            # Log cost summary
            cost_summary = self.pdf_api_processor.cost_tracker.get_summary()
            logger.info(f"Batch processing complete. Cost summary: {cost_summary}")

            return processed_results

        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            raise

    def add_to_batch_queue(self, pdf_url: str, custom_id: str = None) -> str:
        """Add a PDF to the batch accumulator for efficient processing"""
        return self.batch_accumulator.add_request(pdf_url, custom_id)

    def get_batch_queue_status(self) -> Dict[str, Any]:
        """Get current status of the batch accumulator"""
        return self.batch_accumulator.get_status()

    def force_batch_submission(self):
        """Force submission of accumulated batch requests"""
        self.batch_accumulator.force_submit()

    def get_cost_summary(self) -> Dict[str, Any]:
        """Get comprehensive cost tracking summary"""
        return self.pdf_api_processor.cost_tracker.get_summary()

    def shutdown(self):
        """Cleanup resources"""
        logger.info("Shutting down AgendaProcessor...")
        if hasattr(self, "batch_accumulator"):
            self.batch_accumulator.shutdown()
        logger.info("Shutdown complete")


def create_cli_parser():
    """Create CLI argument parser"""
    parser = argparse.ArgumentParser(
        description="Engagic Agenda Processor - Process city council meeting packets using AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fullstack.py --process https://example.com/packet.pdf
  python fullstack.py --process https://example.com/packet.pdf --pdf-method ocr
  python fullstack.py --download https://example.com/packet.pdf -o agenda.pdf
  python fullstack.py --batch meetings.json --wait
        """,
    )

    # Action flags (mutually exclusive)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--process",
        metavar="URL",
        help="Process PDF from URL and generate AI summary",
    )
    action_group.add_argument(
        "--download",
        metavar="URL",
        help="Download PDF packet from URL and save to file",
    )
    action_group.add_argument(
        "--batch",
        metavar="FILE",
        help="Process multiple PDFs from JSON file using batch API",
    )

    # Optional parameters
    parser.add_argument(
        "--output",
        "-o",
        help="Output filename for downloaded packet (only with --download)",
    )
    parser.add_argument(
        "--api-key", help="Anthropic API key (or set LLM_API_KEY env var)"
    )
    parser.add_argument(
        "--pdf-method",
        choices=["auto", "url", "base64", "files", "ocr"],
        default="auto",
        help="PDF processing method (default: auto - tries url->base64->ocr)",
    )
    parser.add_argument(
        "--use-files-api",
        action="store_true",
        help="Use Files API for PDF processing (uploads PDFs for reuse)",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for batch processing to complete (only with --batch)",
    )
    parser.add_argument(
        "--save-summary",
        action="store_true",
        help="Save summary to file after processing",
    )

    return parser


def main():
    """CLI main function"""
    parser = create_cli_parser()
    args = parser.parse_args()

    try:
        # Initialize processor
        processor = AgendaProcessor(api_key=args.api_key)

        if args.download:
            logger.info("=== DOWNLOADING PDF ===")
            output_path = processor.download_packet(args.download, args.output)
            logger.info(f"Success! Packet saved to: {output_path}")

        elif args.process:
            logger.info("=== PROCESSING AGENDA ===")

            # Configure processor with Files API if requested
            if args.use_files_api:
                processor.pdf_api_processor.use_files_api = True
                logger.info("Using Files API for PDF processing")

            # Process the agenda
            summary = processor.process_agenda(
                args.process,
                pdf_method=args.pdf_method,
                save_raw=args.save_summary,
                save_cleaned=args.save_summary,
            )

            if args.save_summary:
                processor._save_text(summary, "agenda_summary.txt")
                logger.info("Summary saved to agenda_summary.txt")

            logger.info(f"Success! Generated summary with {len(summary)} characters")
            logger.info("=" * 50)
            logger.info("SUMMARY:")
            logger.info("=" * 50)
            logger.info(summary)

        elif args.batch:
            logger.info("=== BATCH PROCESSING ===")

            # Load batch requests from JSON file
            import json

            with open(args.batch, "r") as f:
                pdf_requests = json.load(f)

            logger.info(f"Processing {len(pdf_requests)} PDFs in batch mode")

            # Process batch
            results = processor.process_batch_agendas(
                pdf_requests, wait_for_results=args.wait, return_raw=False
            )

            if args.wait:
                # Show results
                success_count = sum(1 for r in results if r.get("status") == "success")
                logger.info(f"Batch complete: {success_count}/{len(results)} succeeded")

                if args.save_summary:
                    # Save all summaries
                    for i, result in enumerate(results):
                        if result.get("status") == "success":
                            filename = f"batch_summary_{result.get('custom_id', i)}.txt"
                            processor._save_text(result["summary"], filename)
                            logger.info(f"Saved summary to {filename}")
            else:
                # Just show batch ID
                logger.info(f"Batch submitted with ID: {results}")
                logger.info("Use batch status API to check progress")

    except KeyboardInterrupt:
        logger.warning("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Ensure cleanup on interrupt
        logger.info("\nShutting down...")
        sys.exit(0)
