"""Pipeline Processor - Queue processing and item assembly"""

import asyncio
import time
from collections import Counter
from typing import List, Optional, Dict, Any

from database.db_postgres import Database
from database.models import Meeting, Matter, MatterMetadata, ParticipationInfo
from database.id_generation import validate_matter_id, extract_banana_from_matter_id
from pipeline.utils import hash_attachments
from exceptions import ProcessingError, ExtractionError, LLMError
from analysis.analyzer_async import AsyncAnalyzer
from analysis.topics.normalizer import get_normalizer
from parsing.participation import parse_participation_info
from config import config, get_logger
from pipeline.protocols import MetricsCollector, NullMetrics
from pipeline.filters import should_skip_processing, is_public_comment_attachment
from vendors.session_manager_async import AsyncSessionManager

logger = get_logger(__name__).bind(component="processor")

QUEUE_POLL_INTERVAL = 5
QUEUE_FATAL_ERROR_BACKOFF = 10

PUBLIC_COMMENT_PAGE_THRESHOLD = 1000
PUBLIC_COMMENT_LARGE_DOC_THRESHOLD = 50
PUBLIC_COMMENT_OCR_THRESHOLD = 0.3
PUBLIC_COMMENT_SIGNATURE_THRESHOLD = 20


def is_procedural_item(title: str) -> bool:
    return should_skip_processing(title)


def is_likely_public_comment_compilation(
    extraction_result: Dict[str, Any],
    url_path: str
) -> bool:
    """Detect public comment compilations via page count, OCR ratio, and signature patterns."""
    page_count = extraction_result.get("page_count", 0)
    ocr_pages = extraction_result.get("ocr_pages", 0)
    text = extraction_result.get("text", "")

    if page_count > PUBLIC_COMMENT_PAGE_THRESHOLD:
        logger.info("skipping likely compilation - excessive page count", url_path=url_path, page_count=page_count)
        return True

    if page_count > PUBLIC_COMMENT_LARGE_DOC_THRESHOLD and ocr_pages > 0:
        ocr_ratio = ocr_pages / page_count
        if ocr_ratio > PUBLIC_COMMENT_OCR_THRESHOLD:
            logger.info("skipping likely scanned compilation - high OCR ratio", url_path=url_path, ocr_ratio=round(ocr_ratio, 2))
            return True

    if len(text) > 5000:
        sincerely_count = text.lower().count("sincerely,")
        if sincerely_count > PUBLIC_COMMENT_SIGNATURE_THRESHOLD:
            logger.info("skipping likely comment compilation - repetitive signatures", url_path=url_path, signature_count=sincerely_count)
            return True

    return False


class Processor:
    """Queue processing and item assembly orchestrator"""

    def __init__(
        self,
        db: Database,
        analyzer: Optional[AsyncAnalyzer] = None,
        metrics: Optional[MetricsCollector] = None,
    ):
        self.db = db
        self.metrics = metrics or NullMetrics()
        self.is_running = True

        if analyzer is not None:
            self.analyzer = analyzer
        else:
            try:
                self.analyzer = AsyncAnalyzer(api_key=config.get_api_key(), metrics=self.metrics)
                logger.info("initialized with async llm analyzer", has_analyzer=True)
            except ValueError:
                logger.warning("llm analyzer not available, summaries will be skipped", has_analyzer=False)
                self.analyzer = None

    def _filter_document_versions(self, urls: List[str]) -> List[str]:
        """Keep only latest versions (Ver2 > Ver1, etc.)."""
        import re

        url_groups = {}
        non_versioned = []
        version_pattern = re.compile(r'(.+?)\s+Ver(\d+)', re.IGNORECASE)

        for url in urls:
            filename = url.split('/')[-1] if url else ""
            match = version_pattern.search(filename)
            if match:
                base_name = match.group(1).strip()
                version_num = int(match.group(2))
                url_groups.setdefault(base_name, {})[version_num] = url
            else:
                non_versioned.append(url)

        filtered = non_versioned.copy()
        for versions in url_groups.values():
            filtered.append(versions[max(versions.keys())])

        return filtered

    async def _dispatch_and_process_job(self, job, queue_id: int) -> bool:
        """Dispatch and process a single queue job. Returns True if processed."""
        if not self.analyzer:
            await self.db.queue.mark_processing_failed(queue_id, "Analyzer not available", increment_retry=False)
            logger.warning("skipping queue job - analyzer not available", queue_id=queue_id)
            return True

        job_type = job.job_type

        try:
            if job_type == "matter":
                from pipeline.models import MatterJob
                if not isinstance(job.payload, MatterJob):
                    raise ValueError(f"Invalid payload type for matter job: {type(job.payload)}")
                await self.process_matter(job.payload.matter_id, job.payload.meeting_id, {"item_ids": job.payload.item_ids})

            elif job_type == "meeting":
                from pipeline.models import MeetingJob
                if not isinstance(job.payload, MeetingJob):
                    raise ValueError(f"Invalid payload type for meeting job: {type(job.payload)}")
                meeting = await self.db.meetings.get_meeting(job.payload.meeting_id)
                if not meeting:
                    await self.db.queue.mark_processing_failed(queue_id, "Meeting not found in database")
                    return True
                await self.process_meeting(meeting)

            else:
                raise ValueError(f"Unknown job type: {job_type}")

            await self.db.queue.mark_processing_complete(queue_id)
            logger.info("queue job completed", queue_id=queue_id)
            return True

        except (ProcessingError, LLMError, ExtractionError) as e:
            await self.db.queue.mark_processing_failed(queue_id, str(e))
            logger.error("queue job failed", queue_id=queue_id, error=str(e))
            return True

    async def process_queue(self):
        """Process jobs from the processing queue continuously"""
        logger.info("starting queue processor")

        while self.is_running:
            try:
                job = await self.db.queue.get_next_for_processing()

                if not job:
                    await asyncio.sleep(QUEUE_POLL_INTERVAL)
                    continue

                queue_id = job.id
                logger.info("processing queue job", queue_id=queue_id, job_type=job.job_type)

                await self._dispatch_and_process_job(job, queue_id)

            except (ProcessingError, LLMError, ExtractionError) as e:
                # Expected errors during job processing - log and continue
                logger.error("queue processor error", error=str(e), error_type=type(e).__name__)
                await asyncio.sleep(QUEUE_FATAL_ERROR_BACKOFF)

    async def process_city_jobs(self, city_banana: str) -> dict:
        """Process all queued jobs for a specific city."""
        logger.info("processing queued jobs for city", city=city_banana)
        processed_count = 0
        failed_count = 0
        total_items_processed = 0
        total_items_new = 0
        total_items_skipped = 0
        total_items_failed = 0

        while True:
            job = await self.db.queue.get_next_for_processing(banana=city_banana)
            if not job:
                break

            queue_id = job.id
            job_type = job.job_type
            logger.info("processing job", queue_id=queue_id, job_type=job_type)
            job_start_time = time.time()

            try:
                if job_type == "meeting":
                    from pipeline.models import MeetingJob
                    if not isinstance(job.payload, MeetingJob):
                        raise ValueError("Invalid payload type for meeting job")
                    meeting = await self.db.meetings.get_meeting(job.payload.meeting_id)
                    if not meeting:
                        await self.db.queue.mark_processing_failed(queue_id, "Meeting not found")
                        failed_count += 1
                        self.metrics.queue_jobs_processed.labels(job_type="meeting", status="failed").inc()
                        continue
                    with self.metrics.processing_duration.labels(job_type="meeting").time():
                        item_stats = await self.process_meeting(meeting)
                    await self.db.queue.mark_processing_complete(queue_id)
                    processed_count += 1
                    if item_stats:
                        total_items_processed += item_stats.get("items_processed", 0)
                        total_items_new += item_stats.get("items_new", 0)
                        total_items_skipped += item_stats.get("items_skipped", 0)
                        total_items_failed += item_stats.get("items_failed", 0)
                    logger.info("processed meeting", meeting_id=job.payload.meeting_id, duration_seconds=round(time.time() - job_start_time, 1))
                    self.metrics.queue_jobs_processed.labels(job_type=job_type, status="completed").inc()

                elif job_type == "matter":
                    from pipeline.models import MatterJob
                    if not isinstance(job.payload, MatterJob):
                        raise ValueError("Invalid payload type for matter job")
                    with self.metrics.processing_duration.labels(job_type="matter").time():
                        await self.process_matter(job.payload.matter_id, job.payload.meeting_id, {"item_ids": job.payload.item_ids})
                    await self.db.queue.mark_processing_complete(queue_id)
                    processed_count += 1
                    logger.info("processed matter", matter_id=job.payload.matter_id, duration_seconds=round(time.time() - job_start_time, 1))
                    self.metrics.queue_jobs_processed.labels(job_type=job_type, status="completed").inc()

                else:
                    raise ValueError(f"Unknown job type: {job_type}")

            except (ProcessingError, LLMError, ExtractionError) as e:
                await self.db.queue.mark_processing_failed(queue_id, str(e))
                failed_count += 1
                self.metrics.queue_jobs_processed.labels(job_type=job_type, status="failed").inc()
                self.metrics.record_error(component="processor", error=e)
                logger.error("job processing failed", queue_id=queue_id, job_type=job_type, duration_seconds=round(time.time() - job_start_time, 1), error=str(e))

        logger.info("processing complete for city", city=city_banana, meetings_succeeded=processed_count, meetings_failed=failed_count, items_processed=total_items_processed, items_new=total_items_new, items_skipped=total_items_skipped, items_failed=total_items_failed)

        return {
            "processed_count": processed_count,
            "failed_count": failed_count,
            "items_processed": total_items_processed,
            "items_new": total_items_new,
            "items_skipped": total_items_skipped,
            "items_failed": total_items_failed,
        }

    async def _process_single_item(self, item):
        """Process a single agenda item. Returns dict with success/summary/topics or None."""
        if not self.analyzer:
            raise ProcessingError(
                "Analyzer not initialized",
                context={"component": "processor", "function": "_process_single_item"}
            )

        # Skip procedural items
        if is_procedural_item(item.title):
            logger.debug("skipping procedural item", title=item.title[:50])
            return None

        if not item.attachments:
            logger.debug("no attachments for item", title=item.title[:50])
            return None

        # Check if entire item is public comments or parcel tables
        if is_public_comment_attachment(item.title):
            logger.info("skipping low-value item", title=item.title[:80], reason="public_comments_or_parcel_tables")
            return None

        # Extract text from attachments
        item_parts = []
        total_page_count = 0

        for att in item.attachments:
            att_url, att_type, att_name = att.url, att.type, att.name

            if att_type not in ("pdf", "doc", "unknown") or not att_url:
                continue

            if att_name and is_public_comment_attachment(att_name):
                logger.info("skipping low-value attachment", name=att_name)
                continue

            try:
                result = await self.analyzer.extract_pdf_async(att_url)
                if result.get("success") and result.get("text"):
                    if is_likely_public_comment_compilation(result, att_name or att_url):
                        logger.info("skipping public comment compilation", name=att_name or att_url)
                        continue
                    item_parts.append(f"=== {att_name or att_url} ===\n{result['text']}")
                    total_page_count += result.get("page_count", 0)
                    logger.debug("extracted attachment text", attachment=att_name or att_url, pages=result.get('page_count', 0), chars=len(result['text']))
            except (ExtractionError, OSError, IOError) as e:
                logger.warning("failed to extract attachment", name=att_name or att_url, error=str(e))

        if not item_parts:
            logger.warning("no text extracted for item", title=item.title[:50])
            raise ProcessingError(
                "No text extracted from agenda item",
                context={"item_id": item.id, "item_title": item.title[:100]}
            )

        combined_text = "\n\n".join(item_parts)

        batch_request = [{
            "item_id": item.id,
            "title": item.title,
            "text": combined_text,
            "sequence": item.sequence,
            "page_count": total_page_count if total_page_count > 0 else None,
        }]

        try:
            chunks = await self.analyzer.process_batch_items_async(batch_request, shared_context=None, meeting_id=None)
            for chunk_results in chunks:
                if chunk_results:
                    result = chunk_results[0]
                    if result.get("success"):
                        normalized_topics = get_normalizer().normalize(result.get("topics", []))
                        return {"success": True, "summary": result["summary"], "topics": normalized_topics}
                    else:
                        raise ProcessingError(f"Item processing failed: {result.get('error', 'Unknown error')}", context={"item_id": item.id})
        except LLMError as e:
            raise ProcessingError(f"Item processing failed: {e}", context={"item_id": item.id}) from e

        raise ProcessingError("No results returned from batch processing", context={"item_id": item.id})

    async def process_matter(self, matter_id: str, meeting_id: str, metadata: Optional[Dict] = None):
        """Process a matter across all its appearances, updating canonical summary."""
        logger.info("processing matter", matter_id=matter_id)

        if not validate_matter_id(matter_id):
            logger.error("invalid matter_id format", matter_id=matter_id)
            return

        banana = extract_banana_from_matter_id(matter_id)
        if not banana:
            logger.error("could not extract banana from matter_id", matter_id=matter_id)
            return

        items = []
        if metadata:
            for item_id in metadata.get("item_ids", []):
                item = await self.db.items.get_agenda_item(item_id)
                if item:
                    items.append(item)

        if not items:
            logger.warning("no items in payload, querying database", matter_id=matter_id)
            items = await self.db.items.get_all_items_for_matter(matter_id)

        if not items:
            logger.error("no items found for matter", matter_id=matter_id)
            return

        all_attachments = []
        seen_urls = set()
        for item in items:
            for att in (item.attachments or []):
                if att.url and att.url not in seen_urls:
                    seen_urls.add(att.url)
                    all_attachments.append(att)

        representative_item = items[0]
        representative_item.attachments = all_attachments

        logger.info("matter aggregation complete", matter_id=matter_id, appearances=len(items), unique_attachments=len(all_attachments))

        if not all_attachments:
            logger.debug("matter skipped - no attachments", matter_id=matter_id)
            return

        try:
            result = await self._process_single_item(representative_item)
        except ProcessingError as e:
            logger.error("matter processing failed", matter_id=matter_id, error=str(e))
            self.metrics.record_error("processor", e)
            return

        if not result:
            return

        summary = result.get("summary")
        topics = result.get("topics", [])

        if not summary:
            logger.warning("no summary generated for matter", matter_id=matter_id)
            return

        attachment_hash = hash_attachments(representative_item.attachments)
        existing_matter = await self.db.matters.get_matter(matter_id)

        matter_obj = Matter(
            id=matter_id,
            banana=banana,
            matter_id=existing_matter.matter_id if existing_matter else None,
            matter_file=representative_item.matter_file,
            matter_type=representative_item.matter_type,
            title=representative_item.title,
            sponsors=getattr(representative_item, 'sponsors', []),
            canonical_summary=summary,
            canonical_topics=topics,
            attachments=representative_item.attachments,
            metadata=MatterMetadata(attachment_hash=attachment_hash),
            first_seen=existing_matter.first_seen if existing_matter else None,
            last_seen=existing_matter.last_seen if existing_matter else None,
            appearance_count=existing_matter.appearance_count if existing_matter else 1,
        )

        await self.db.matters.store_matter(matter_obj)

        item_ids = [item.id for item in items]
        await self.db.items.bulk_update_item_summaries(item_ids=item_ids, summary=summary, topics=topics)

        logger.info("stored canonical summary and backfilled items", matter_id=matter_id, item_count=len(items))

    async def process_meeting(self, meeting: Meeting):
        """Process summary for a single meeting (items > packet fallback)."""
        empty_stats = {"items_processed": 0, "items_new": 0, "items_skipped": 0, "items_failed": 0}

        try:
            agenda_items = await self.db.items.get_agenda_items(meeting.id)

            if agenda_items:
                logger.info("found items for meeting", item_count=len(agenda_items), meeting_title=meeting.title)
                if not self.analyzer:
                    logger.warning("analyzer not available")
                    return empty_stats
                return await self._process_meeting_with_items(meeting, agenda_items)

            if meeting.packet_url:
                logger.info("processing packet as monolithic unit - no items found", meeting_title=meeting.title)
                if not self.analyzer:
                    logger.warning("skipping meeting - analyzer not available", packet_url=meeting.packet_url)
                    return empty_stats

                meeting_data = {
                    "packet_url": meeting.packet_url,
                    "city_banana": meeting.banana,
                    "meeting_name": meeting.title,
                    "meeting_date": meeting.date.isoformat() if meeting.date else None,
                    "meeting_id": meeting.id,
                }
                result = await self.analyzer.process_agenda_with_cache_async(meeting_data)
                if result.get("success"):
                    await self.db.meetings.update_meeting_summary(
                        meeting_id=meeting.id,
                        summary=result.get("summary"),
                        processing_method=result.get("processing_method") or "pymupdf_gemini",
                        processing_time=result.get("processing_time") or 0.0,
                        topics=None,
                        participation=result.get("participation"),
                    )
                    logger.info("processed packet", packet_url=meeting.packet_url, processing_time_seconds=round(result['processing_time'], 1))
                    return {"items_processed": 1, "items_new": 1, "items_skipped": 0, "items_failed": 0}
                else:
                    logger.error("failed to process packet", packet_url=meeting.packet_url, error=result.get('error'))
                    return {"items_processed": 0, "items_new": 0, "items_skipped": 0, "items_failed": 1}

            return empty_stats

        except (ProcessingError, LLMError, ExtractionError) as e:
            logger.error("error processing summary", packet_url=meeting.packet_url, error=str(e))
            return {"items_processed": 0, "items_new": 0, "items_skipped": 0, "items_failed": 1}

    async def _extract_participation_info(self, meeting: Meeting) -> Dict[str, Any]:
        """Extract participation info from agenda_url (PDF or HTML)."""
        if not meeting.agenda_url:
            return {}

        try:
            agenda_url_lower = meeting.agenda_url.lower()

            if agenda_url_lower.endswith('.pdf') or '.ashx' in agenda_url_lower:
                if not self.analyzer:
                    logger.warning("analyzer not initialized, skipping participation extraction")
                    return {}
                agenda_result = await self.analyzer.extract_pdf_async(meeting.agenda_url)
                if agenda_result.get("success") and agenda_result.get("text"):
                    agenda_participation = parse_participation_info(agenda_result["text"][:5000])
                    if agenda_participation:
                        return agenda_participation.model_dump(exclude_none=True)

            elif meeting.participation:
                return meeting.participation.model_dump(exclude_none=True)

        except (ExtractionError, OSError, IOError) as e:
            logger.warning("failed to extract participation from agenda_url", error=str(e))

        return {}

    async def _filter_processed_items(self, agenda_items: List) -> tuple[List[Dict], List]:
        """Separate already-processed items from items needing processing."""
        already_processed = []
        need_processing = []

        for item in agenda_items:
            if is_procedural_item(item.title):
                logger.debug("skipping procedural item", title=item.title[:50])
                continue

            if not item.attachments:
                logger.debug("skipping item without attachments", title=item.title[:50])
                continue

            if item.matter_id:
                matter = await self.db.matters.get_matter(item.matter_id)
                if matter and matter.canonical_summary:
                    logger.debug("reusing canonical summary from matter", title=item.title[:50])
                    if not item.summary:
                        await self.db.items.update_agenda_item(item_id=item.id, summary=matter.canonical_summary, topics=matter.canonical_topics or [])
                    already_processed.append({"sequence": item.sequence, "title": item.title, "summary": matter.canonical_summary, "topics": matter.canonical_topics or []})
                    continue

            if item.summary:
                logger.debug("item already processed", title=item.title[:50])
                already_processed.append({"sequence": item.sequence, "title": item.title, "summary": item.summary, "topics": item.topics or []})
            else:
                need_processing.append(item)

        return already_processed, need_processing

    async def _build_document_cache(self, need_processing: List) -> tuple[Dict, Dict, set]:
        """Build meeting-level document cache with version filtering and deduplication."""
        logger.info("building meeting-level document cache")
        document_cache = {}
        item_attachments = {}
        all_urls = set()
        url_to_items = {}
        url_to_name = {}

        for item in need_processing:
            item_urls = []
            for att in item.attachments:
                if att.type in ("pdf", "doc", "unknown") and att.url:
                    item_urls.append(att.url)
                    if att.name and att.url not in url_to_name:
                        url_to_name[att.url] = att.name

            filtered_item_urls = self._filter_document_versions(item_urls)
            item_attachments[item.id] = filtered_item_urls

            for url in filtered_item_urls:
                all_urls.add(url)
                url_to_items.setdefault(url, []).append(item.id)

        logger.info("collected unique URLs", url_count=len(all_urls), item_count=len(need_processing))

        if not self.analyzer:
            logger.error("analyzer not initialized, cannot extract attachments")
            return {}, item_attachments, all_urls

        for att_url in all_urls:
            att_name = url_to_name.get(att_url, "")
            if att_name and is_public_comment_attachment(att_name):
                logger.info("skipping low-value attachment", attachment_name=att_name)
                continue

            try:
                result = await self.analyzer.extract_pdf_async(att_url)
                if result.get("success") and result.get("text"):
                    if is_likely_public_comment_compilation(result, att_name or att_url):
                        logger.info("skipping public comment compilation", attachment=att_name or att_url)
                        continue
                    document_cache[att_url] = {"text": result["text"], "page_count": result.get("page_count", 0), "name": att_name or att_url}
                    item_count = len(url_to_items[att_url])
                    logger.info("extracted document", attachment=att_name or att_url, pages=result.get('page_count', 0), shared=(item_count > 1))
            except (ExtractionError, OSError, IOError) as e:
                logger.warning("failed to extract document", attachment=att_name or att_url, error=str(e))

        shared_urls = {url for url, items in url_to_items.items() if len(items) > 1 and url in document_cache}
        logger.info("cached documents", total_cached=len(document_cache), shared_count=len(shared_urls))

        return document_cache, item_attachments, shared_urls

    def _build_batch_requests(
        self,
        need_processing: List,
        document_cache: Dict,
        item_attachments: Dict,
        shared_urls: set,
        participation_data: Dict[str, Any],
        first_sequence: Optional[int],
        last_sequence: Optional[int]
    ) -> tuple[List[Dict], Dict, List[str]]:
        """Build batch requests from cached documents."""
        batch_requests = []
        item_map = {}
        failed_items = []

        for item in need_processing:
            try:
                if is_public_comment_attachment(item.title):
                    logger.info("skipping entire item - low value content", title=item.title[:80])
                    continue

                item_specific_parts = []
                total_page_count = 0

                for att_url in item_attachments.get(item.id, []):
                    if att_url in shared_urls:
                        continue
                    if att_url in document_cache:
                        doc = document_cache[att_url]
                        item_specific_parts.append(f"=== {doc['name']} ===\n{doc['text']}")
                        total_page_count += doc['page_count']

                if item_specific_parts:
                    combined_text = "\n\n".join(item_specific_parts)

                    if item.sequence in (first_sequence, last_sequence):
                        item_participation = parse_participation_info(combined_text)
                        if item_participation:
                            participation_data.update(item_participation.model_dump(exclude_none=True))

                    batch_requests.append({
                        "item_id": item.id,
                        "title": item.title,
                        "text": combined_text,
                        "sequence": item.sequence,
                        "page_count": total_page_count if total_page_count > 0 else None,
                    })
                    item_map[item.id] = item
                    logger.debug("prepared item for batch processing", title=item.title[:50], chars=len(combined_text))
                else:
                    logger.warning("no text extracted for item", title=item.title[:50])
                    failed_items.append(item.title)

            except (KeyError, AttributeError, TypeError) as e:
                logger.error("error extracting text for item", title=item.title[:50], error=str(e))
                failed_items.append(item.title)

        return batch_requests, item_map, failed_items

    async def _process_batch_incrementally(
        self,
        batch_requests: List[Dict],
        item_map: Dict,
        shared_context: Optional[str],
        meeting_id: str
    ) -> tuple[List[Dict], List[str]]:
        """Process batch requests incrementally, saving after each chunk."""
        processed_items = []
        failed_items = []

        if not batch_requests or not self.analyzer:
            return processed_items, failed_items

        logger.info("submitting batch to Gemini", item_count=len(batch_requests))

        chunks = await self.analyzer.process_batch_items_async(batch_requests, shared_context=shared_context, meeting_id=meeting_id)
        for chunk_results in chunks:
            logger.info("saving results from completed chunk", result_count=len(chunk_results))

            for result in chunk_results:
                item_id = result["item_id"]
                item = item_map.get(item_id)
                if not item:
                    logger.warning("no item mapping found", item_id=item_id)
                    continue

                if result["success"]:
                    normalized_topics = get_normalizer().normalize(result.get("topics", []))
                    await self.db.items.update_agenda_item(item_id=item_id, summary=result["summary"], topics=normalized_topics)

                    if item.matter_id:
                        await self._store_canonical_summary(item=item, summary=result["summary"], topics=normalized_topics)

                    processed_items.append({"sequence": item.sequence, "title": item.title, "summary": result["summary"], "topics": normalized_topics})
                    logger.info("item saved", title=item.title[:60])
                else:
                    failed_items.append(item.title)
                    logger.warning("item processing failed", title=item.title[:60], error=result.get('error'))

        return processed_items, failed_items

    async def _store_canonical_summary(self, item, summary: str, topics: List[str]) -> None:
        """Store canonical summary for matter deduplication across meetings."""
        banana = extract_banana_from_matter_id(item.matter_id)
        if not banana:
            logger.warning("could not extract banana from matter_id", matter_id=item.matter_id)
            return

        existing_matter = await self.db.matters.get_matter(item.matter_id)
        matter_obj = Matter(
            id=item.matter_id,
            banana=banana,
            matter_id=existing_matter.matter_id if existing_matter else None,
            matter_file=item.matter_file,
            matter_type=item.matter_type,
            title=item.title,
            sponsors=getattr(item, 'sponsors', []),
            canonical_summary=summary,
            canonical_topics=topics,
            attachments=item.attachments,
            metadata=MatterMetadata(attachment_hash=hash_attachments(item.attachments or [])),
            first_seen=existing_matter.first_seen if existing_matter else None,
            last_seen=existing_matter.last_seen if existing_matter else None,
            appearance_count=existing_matter.appearance_count if existing_matter else 1,
        )

        await self.db.matters.store_matter(matter_obj)
        logger.info("stored canonical summary", matter_id=item.matter_id)

    def _aggregate_meeting_topics(self, processed_items: List[Dict]) -> List[str]:
        """Aggregate topics from processed items, sorted by frequency."""
        topic_counts = Counter(topic for item in processed_items for topic in item.get("topics", []))
        meeting_topics = [topic for topic, _ in topic_counts.most_common()]
        logger.info("aggregated meeting topics", unique_topic_count=len(meeting_topics), item_count=len(processed_items))
        return meeting_topics

    async def _process_meeting_with_items(self, meeting: Meeting, agenda_items: List):
        """Process meeting at item-level granularity using batch API."""
        start_time = time.time()

        if not self.analyzer:
            logger.warning("analyzer not available")
            return {"items_processed": 0, "items_new": 0, "items_skipped": 0, "items_failed": 0}

        item_sequences = [item.sequence for item in agenda_items]
        first_sequence = min(item_sequences) if item_sequences else None
        last_sequence = max(item_sequences) if item_sequences else None

        participation_data = await self._extract_participation_info(meeting)
        already_processed, need_processing = await self._filter_processed_items(agenda_items)
        processed_items = list(already_processed)
        failed_items = []

        if not need_processing:
            logger.info("all items already processed", item_count=len(already_processed))
        else:
            logger.info("extracting text from items for batch processing", item_count=len(need_processing))

            document_cache, item_attachments, shared_urls = await self._build_document_cache(need_processing)

            shared_context = None
            if shared_urls:
                shared_parts = [f"=== {document_cache[url]['name']} ===\n{document_cache[url]['text']}" for url in sorted(shared_urls)]
                shared_context = "\n\n".join(shared_parts)
                logger.info("built meeting-level shared context", chars=len(shared_context), shared_document_count=len(shared_urls))

            batch_requests, item_map, failed_items = self._build_batch_requests(
                need_processing, document_cache, item_attachments, shared_urls,
                participation_data, first_sequence, last_sequence
            )

            if batch_requests:
                new_processed, new_failed = await self._process_batch_incrementally(batch_requests, item_map, shared_context, meeting.id)
                processed_items.extend(new_processed)
                failed_items.extend(new_failed)

        if processed_items and self.analyzer:
            meeting_topics = self._aggregate_meeting_topics(processed_items)

            merged_participation = None
            if participation_data or meeting.participation:
                merged_dict = meeting.participation.model_dump(exclude_none=True) if meeting.participation else {}
                if participation_data:
                    merged_dict.update(participation_data)
                merged_participation = ParticipationInfo(**merged_dict) if merged_dict else None

            processing_time = time.time() - start_time
            await self.db.meetings.update_meeting_summary(
                meeting_id=meeting.id,
                summary=None,
                processing_method=f"item_level_{len(processed_items)}_items",
                processing_time=processing_time,
                topics=meeting_topics,
                participation=merged_participation,
            )

            skipped_count = len(already_processed)
            new_count = len(processed_items) - skipped_count
            logger.info("item processing completed", processed_count=len(processed_items), new_items=new_count, skipped_items=skipped_count, failed_count=len(failed_items), processing_time_seconds=round(processing_time, 1))

            return {"items_processed": len(processed_items), "items_new": new_count, "items_skipped": skipped_count, "items_failed": len(failed_items)}

        logger.warning("no items could be processed")
        return {"items_processed": 0, "items_new": 0, "items_skipped": 0, "items_failed": 0}

    async def close(self):
        """Cleanup resources (HTTP sessions)"""
        if self.analyzer:
            await self.analyzer.close()
            logger.debug("analyzer http session closed")
        await AsyncSessionManager.close_all()
        logger.debug("vendor http sessions closed")
