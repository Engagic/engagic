"""
Admin utilities for debugging and inspection

Standalone utilities for previewing and extracting text from meetings and items.
These are debugging tools, not core orchestration logic.
"""

import logging
from typing import Dict, Any, Optional

import config
from database.db import UnifiedDatabase

logger = logging.getLogger("engagic")


def extract_text_preview(meeting_id: str, output_file: Optional[str] = None) -> Dict[str, Any]:
    """Extract text from meeting PDF without processing (for manual review)

    Args:
        meeting_id: Meeting identifier
        output_file: Optional file path to save extracted text

    Returns:
        Dictionary with text preview and stats
    """
    logger.info(f"[Admin] Extracting text preview for {meeting_id}...")

    db = UnifiedDatabase(config.UNIFIED_DB_PATH)
    meeting = db.get_meeting(meeting_id)
    if not meeting:
        return {"error": "Meeting not found"}

    # Try agenda_url first (item-level), fallback to packet_url (monolithic)
    source_url = meeting.agenda_url or meeting.packet_url
    if not source_url:
        return {"error": "No agenda or packet URL for this meeting"}

    try:
        # Extract text using PDF extractor (doesn't need LLM analyzer)
        from parsing.pdf import PdfExtractor
        extractor = PdfExtractor()

        # Handle URL being either str or List[str]
        url = source_url[0] if isinstance(source_url, list) else source_url

        logger.info(f"[Admin] Downloading PDF: {url}")
        extraction_result = extractor.extract_from_url(url)

        if not extraction_result["success"]:
            return {
                "error": extraction_result.get("error", "Failed to extract text"),
                "meeting_id": meeting_id,
            }

        text = extraction_result["text"]
        page_count = extraction_result.get("page_count", 0)
        text_length = len(text)

        # Optionally save to file
        if output_file:
            with open(output_file, "w") as f:
                f.write(f"Meeting: {meeting.title}\n")
                f.write(f"Date: {meeting.date}\n")
                f.write(f"URL: {source_url}\n")
                f.write(f"Pages: {page_count}\n")
                f.write(f"Characters: {text_length}\n")
                f.write("=" * 80 + "\n\n")
                f.write(text)
            logger.info(f"[Admin] Saved text to {output_file}")

        # Return preview (first 2000 chars)
        preview_text = text[:2000] + ("..." if len(text) > 2000 else "")

        return {
            "success": True,
            "meeting_id": meeting_id,
            "title": meeting.title,
            "date": meeting.date.isoformat() if meeting.date else None,
            "page_count": page_count,
            "text_length": text_length,
            "preview": preview_text,
            "saved_to": output_file,
        }

    except Exception as e:
        logger.error(f"[Admin] Failed to extract text: {e}")
        return {
            "error": str(e),
            "meeting_id": meeting_id,
        }


def preview_items(meeting_id: str, extract_text: bool = False, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """Preview items and optionally extract text from their attachments

    Args:
        meeting_id: Meeting identifier
        extract_text: Whether to extract text from item attachments (default False)
        output_dir: Optional directory to save extracted texts

    Returns:
        Dictionary with items structure and optional text previews
    """
    logger.info(f"[Admin] Previewing items for {meeting_id}...")

    db = UnifiedDatabase(config.UNIFIED_DB_PATH)
    meeting = db.get_meeting(meeting_id)
    if not meeting:
        return {"error": "Meeting not found"}

    # Get items from database
    agenda_items = db.get_agenda_items(meeting_id)
    if not agenda_items:
        return {
            "error": "No items found for this meeting",
            "meeting_id": meeting_id,
            "meeting_title": meeting.title,
        }

    items_preview = []

    for item in agenda_items:
        item_data = {
            "item_id": item.id,
            "title": item.title,
            "sequence": item.sequence,
            "attachments": [
                {
                    "name": att.get("name", "Unknown"),
                    "url": att.get("url", ""),
                    "type": att.get("type", "unknown"),
                }
                for att in (item.attachments or [])
            ],
            "has_summary": bool(item.summary),
        }

        # Optionally extract text from first attachment
        if extract_text and item.attachments:
            first_attachment = item.attachments[0]
            att_url = first_attachment.get("url")

            if att_url and att_url.endswith(".pdf"):
                try:
                    from parsing.pdf import PdfExtractor
                    extractor = PdfExtractor()

                    logger.info(f"[Admin] Extracting text from {item.id} attachment...")
                    extraction_result = extractor.extract_from_url(att_url)

                    if extraction_result["success"]:
                        text = extraction_result["text"]
                        page_count = extraction_result.get("page_count", 0)

                        # Preview first 500 chars
                        item_data["text_preview"] = text[:500] + ("..." if len(text) > 500 else "")
                        item_data["page_count"] = page_count
                        item_data["text_length"] = len(text)

                        # Optionally save to file
                        if output_dir:
                            import os
                            os.makedirs(output_dir, exist_ok=True)
                            filename = f"{item.id}.txt"
                            filepath = os.path.join(output_dir, filename)

                            with open(filepath, "w") as f:
                                f.write(f"Item: {item.title}\n")
                                f.write(f"Attachment: {first_attachment.get('name')}\n")
                                f.write(f"URL: {att_url}\n")
                                f.write(f"Pages: {page_count}\n")
                                f.write(f"Characters: {len(text)}\n")
                                f.write("=" * 80 + "\n\n")
                                f.write(text)

                            item_data["saved_to"] = filepath
                            logger.info(f"[Admin] Saved {item.id} text to {filepath}")
                    else:
                        item_data["text_error"] = extraction_result.get("error", "Failed to extract")

                except Exception as e:
                    logger.warning(f"[Admin] Failed to extract text for {item.id}: {e}")
                    item_data["text_error"] = str(e)

        items_preview.append(item_data)

    return {
        "success": True,
        "meeting_id": meeting_id,
        "meeting_title": meeting.title,
        "meeting_date": meeting.date.isoformat() if meeting.date else None,
        "total_items": len(agenda_items),
        "items": items_preview,
    }
