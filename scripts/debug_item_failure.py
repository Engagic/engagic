#!/usr/bin/env python3
"""
Debug script to test item processing and capture full input/output
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import UnifiedDatabase
from parsing.pdf import PdfExtractor
from analysis.llm.summarizer import GeminiSummarizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

def main():
    # Initialize
    db = UnifiedDatabase("/root/engagic/data/engagic.db")

    # Get a specific failed item
    item_id = "1347733_7697872"  # SF item with attachments but no summary

    conn = db.get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, meeting_id, title, attachments, sequence
        FROM items
        WHERE id = ?
    """, (item_id,))

    row = cursor.fetchone()
    if not row:
        logger.error(f"Item {item_id} not found")
        return

    item_id, meeting_id, title, attachments_json, sequence = row

    logger.info(f"Processing item: {title[:100]}")

    # Parse attachments
    try:
        attachments = json.loads(attachments_json)
        logger.info(f"Found {len(attachments)} attachments")
    except:
        logger.error("Failed to parse attachments JSON")
        return

    # Extract text from all attachments
    all_text = []
    total_pages = 0
    extractor = PdfExtractor()

    for att in attachments:
        url = att.get("url")
        if not url or not url.endswith(".pdf"):
            continue

        logger.info(f"Extracting text from {url}")
        try:
            result = extractor.extract_from_url(url)
            if result['success']:
                all_text.append(result['text'])
                total_pages += result['page_count']
                logger.info(f"Extracted {result['page_count']} pages, {len(result['text'])} chars")
            else:
                logger.error(f"Extraction failed: {result.get('error')}")
        except Exception as e:
            logger.error(f"Failed to extract: {e}")

    if not all_text:
        logger.error("No text extracted from any attachment")
        return

    combined_text = "\n\n".join(all_text)
    logger.info(f"Total: {total_pages} pages, {len(combined_text)} chars")

    # Show input details
    logger.info("=" * 80)
    logger.info("ITEM TITLE:")
    logger.info("=" * 80)
    logger.info(title)
    logger.info("=" * 80)

    # Check for problematic characters
    has_quotes = '"' in combined_text
    has_single_quotes = "'" in combined_text
    has_newlines = '\n' in combined_text
    has_backslashes = '\\' in combined_text

    logger.info("CHARACTER ANALYSIS:")
    logger.info(f"  Contains double quotes: {has_quotes}")
    logger.info(f"  Contains single quotes: {has_single_quotes}")
    logger.info(f"  Contains newlines: {has_newlines}")
    logger.info(f"  Contains backslashes: {has_backslashes}")
    logger.info("=" * 80)

    logger.info("INPUT TEXT (first 2000 chars):")
    logger.info("=" * 80)
    logger.info(combined_text[:2000])
    logger.info("=" * 80)

    logger.info("INPUT TEXT (last 2000 chars):")
    logger.info("=" * 80)
    logger.info(combined_text[-2000:])
    logger.info("=" * 80)

if __name__ == "__main__":
    main()
