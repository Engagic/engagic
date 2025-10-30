"""
Agenda Document Parser and Chunker

Responsibilities:
- Parse document structure (cover page, body content)
- Detect item boundaries
- Extract agenda metadata
- Match items to content
- Split large agendas into processable chunks
"""

import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger("engagic")


class AgendaChunker:
    """Parse and chunk agenda documents by item structure"""

    def __init__(self):
        pass

    def chunk_by_structure(self, pdf_text: str) -> List[Dict[str, Any]]:
        """
        Universal agenda parser. Works by:
        1. Extract cover page agenda listing (source of truth for item metadata)
        2. Find where those items appear in the body text
        3. Split on those boundaries

        Args:
            pdf_text: Full extracted text from PDF

        Returns:
            List of chunks: [{'sequence': int, 'title': str, 'text': str, 'start_page': int}, ...]
        """
        # Normalize page breaks and excessive newlines
        text = re.sub(r"\f+", "\n\n", pdf_text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Step 1: Split cover from body
        cover_end = self._detect_cover_end(text)

        cover_text = text[:cover_end]
        body_text = text[cover_end:]

        logger.info(
            f"[Chunker] Cover ends at {cover_end} ({cover_end / len(text) * 100:.1f}% of doc)"
        )

        # Step 2: Extract item metadata from cover
        agenda_items = self._parse_cover_agenda(cover_text)

        if not agenda_items:
            logger.info("[Chunker] No agenda items found in cover")
            return []

        # If cover is suspiciously small but we found items, it might still be valid
        # Only reject if cover is < 0.5% AND we found very few items
        cover_pct = cover_end / len(text)
        if cover_pct < 0.005 and len(agenda_items) < 3:
            logger.info(
                f"[Chunker] Cover too small ({cover_pct * 100:.1f}%) with only {len(agenda_items)} items - likely false detection"
            )
            return []

        logger.info(f"[Chunker] Found {len(agenda_items)} items in cover section")

        # Step 3: Find where cover items appear in body
        boundaries = self._find_item_boundaries_by_title(body_text, agenda_items)

        if not boundaries or len(boundaries) < 2:
            logger.info(
                f"[Chunker] Insufficient boundaries found by title search (found {len(boundaries) if boundaries else 0})"
            )
            return []

        # Step 4: Create chunks from boundaries
        chunks = []
        for i, boundary in enumerate(boundaries):
            start = boundary["start"]
            end = (
                boundaries[i + 1]["start"]
                if i + 1 < len(boundaries)
                else len(body_text)
            )

            content = body_text[start:end].strip()

            # Keep all agenda items from cover, even if small
            # Small items are typically discussion-only items without staff reports
            if len(content) < 100:
                logger.debug(
                    f"[Chunker] Item {boundary['item_id']} has minimal content ({len(content)} chars)"
                )

            # Extract page number - search first 5000 chars since headers might not be immediate
            search_window = content[:5000] if len(content) > 5000 else content
            page_match = re.search(r"--- PAGE (\d+) ---", search_window)
            start_page = int(page_match.group(1)) if page_match else None

            chunks.append(
                {
                    "sequence": i + 1,
                    "title": f"{boundary['item_id']}. {boundary['title']}",
                    "text": content,
                    "start_page": start_page,
                }
            )

        logger.info(
            f"[Chunker] Created {len(chunks)} chunks from {len(agenda_items)} cover items"
        )

        return chunks if len(chunks) >= 2 else []

    def chunk_by_patterns(
        self, text: str, max_chunk_size: int = 75000
    ) -> List[Dict[str, Any]]:
        """
        Fallback pattern-based chunking (original two-pass approach).
        Used when structural chunking fails.

        Args:
            text: Full extracted text
            max_chunk_size: Maximum characters per chunk

        Returns:
            List of chunks with metadata
        """
        # PASS 1: Find agenda items in the first portion (likely table of contents)
        # Assume agenda is in first 20% or 50K chars, whichever is smaller
        agenda_section_size = min(int(len(text) * 0.2), 50000)
        agenda_section = text[:agenda_section_size]

        # Find the actual agenda section (between section markers and before content)
        # Common section headers that indicate start of real agenda items
        start_markers = [
            r"BUSINESS\s+ITEMS?",
            r"ACTION\s+ITEMS?",
            r"CONSENT\s+(CALENDAR|AGENDA)",
            r"REGULAR\s+AGENDA",
            r"DISCUSSION\s+ITEMS?",
            r"PUBLIC\s+HEARINGS?",
            r"INFORMATION\s+REPORTS?",
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
            r"ADJOURNMENT",
            r"^\d+\s+(MINUTES|TRANSCRIPT)",  # Line-numbered minutes/transcripts
            r"Item\s+\d+[:\s]+Staff Report Pg\.",  # Actual item content
        ]

        agenda_end = agenda_section_size
        found_end_marker = False
        for marker_pattern in end_markers:
            match = re.search(
                marker_pattern,
                agenda_section[agenda_start:],
                re.IGNORECASE | re.MULTILINE,
            )
            if match:
                agenda_end = agenda_start + match.start()
                found_end_marker = True
                break

        # Only use narrow range if we found BOTH markers, otherwise search full section
        if found_start_marker and found_end_marker:
            actual_agenda = agenda_section[agenda_start:agenda_end]
            logger.debug(
                f"[Chunker] Using marker-based range: {agenda_start}-{agenda_end}"
            )
        else:
            actual_agenda = agenda_section
            agenda_start = 0
            agenda_end = agenda_section_size
            logger.debug(
                "[Chunker] No clear markers found, searching full agenda section"
            )

        agenda_patterns = [
            (
                r"\n\s*(\d+)\.\s*\n\s*([A-Z][^\n]{10,200})",
                "numbered",
            ),  # "1.\n Title" (multiline)
            (
                r"\n\s*(\d+)\.\s+([A-Z][^\n]{10,200})",
                "numbered_inline",
            ),  # "1. Title" (same line)
            (r"\n\s*([A-Z])\.\s*\n\s*([A-Z][^\n]{10,200})", "lettered"),  # "A.\n Title"
            (r"\n\s*([A-Z])\.\s+([A-Z][^\n]{10,200})", "lettered_inline"),
            (r"\n\s*(Item\s+\d+)[:\s]+([^\n]{10,200})", "item"),  # "Item 1: NAME"
        ]

        # Extract agenda items with their titles
        agenda_items = []
        for pattern, item_type in agenda_patterns:
            for match in re.finditer(pattern, actual_agenda, re.IGNORECASE):
                item_num = match.group(1)
                item_title = match.group(2).strip()

                # Skip if this looks like a line number (single word or very short)
                if len(item_title) < 15 or item_title.upper() in [
                    "MINUTES",
                    "PARKS",
                    "RECREATION",
                    "COMMISSION",
                    "MEETING",
                    "REGULAR",
                ]:
                    continue

                # Clean up title - remove extra whitespace, CEQA status, etc
                item_title = re.sub(r"\s+", " ", item_title)
                item_title = re.sub(
                    r";?\s*CEQA[^;]*$", "", item_title, flags=re.IGNORECASE
                )

                agenda_items.append(
                    {
                        "number": item_num,
                        "title": item_title[:150],  # Cap title length
                        "type": item_type,
                        "agenda_pos": agenda_start + match.start(),
                    }
                )

        if not agenda_items:
            logger.info(
                f"[Chunker] No agenda items found in agenda section (searched {len(actual_agenda)} chars between markers)"
            )
            return []

        logger.info(
            f"[Chunker] Found {len(agenda_items)} items in agenda section (between positions {agenda_start}-{agenda_end})"
        )

        # PASS 2: Find where these items appear again in the body
        # Search for item titles in the remainder of the document
        split_points = [0]  # Start of document

        for item in agenda_items:
            # Create search patterns for this item title
            # Try exact match and fuzzy match (accounting for line breaks, extra spaces)
            title_pattern = re.escape(
                item["title"][:50]
            )  # Use first 50 chars for matching
            title_pattern = title_pattern.replace(
                r"\ ", r"\s+"
            )  # Allow flexible whitespace

            # Search starting after the agenda section
            search_start = agenda_section_size
            match = re.search(title_pattern, text[search_start:], re.IGNORECASE)

            if match:
                boundary_pos = search_start + match.start()
                split_points.append(boundary_pos)
                logger.debug(
                    f"[Chunker] Found '{item['number']}. {item['title'][:40]}...' at position {boundary_pos}"
                )
            else:
                # Fallback: search for just the item number pattern
                num_pattern = rf"\n\s*{re.escape(item['number'])}\.\s+"
                match = re.search(num_pattern, text[search_start:])
                if match:
                    boundary_pos = search_start + match.start()
                    split_points.append(boundary_pos)
                    logger.debug(
                        f"[Chunker] Found item {item['number']} (by number only) at position {boundary_pos}"
                    )

        split_points = sorted(set(split_points))
        split_points.append(len(text))

        logger.info(
            f"[Chunker] Found {len(split_points) - 2} boundaries in {len(text)} chars document"
        )

        # If too few boundaries found, not worth chunking
        if len(split_points) < 3:  # Need at least 2 items (0, item1, end)
            logger.info(
                f"[Chunker] Only {len(split_points) - 2} boundaries found - processing monolithically"
            )
            return []

        # Create chunks at every boundary
        # Each chunk should correspond to an agenda item's detailed content
        chunks = []
        for i in range(1, len(split_points)):
            chunk_text = text[split_points[i - 1] : split_points[i]]

            # Try to match this chunk to an agenda item
            chunk_start_pos = split_points[i - 1]
            matching_item = None

            for item in agenda_items:
                # Skip first chunk (agenda header)
                if chunk_start_pos == 0:
                    continue
                # Try to find the item number at the start of this chunk
                chunk_preview = chunk_text[:200]
                if re.search(rf"\n\s*{re.escape(item['number'])}\.\s+", chunk_preview):
                    matching_item = item
                    break

            chunks.append(
                {
                    "start_pos": split_points[i - 1],
                    "end_pos": split_points[i],
                    "text": chunk_text,
                    "agenda_item": matching_item,
                }
            )

        # Filter out chunks that are too small (likely agenda header) and combine if needed
        meaningful_chunks = []
        for chunk in chunks:
            # Skip very small chunks (likely just agenda section)
            if len(chunk["text"]) < 1000 and chunk["start_pos"] == 0:
                logger.debug(
                    f"[Chunker] Skipping small header chunk ({len(chunk['text'])} chars)"
                )
                continue
            meaningful_chunks.append(chunk)

        if len(meaningful_chunks) <= 1:
            logger.info(
                f"[Chunker] Only {len(meaningful_chunks)} meaningful chunks - processing monolithically"
            )
            return []

        # Cap at reasonable number of chunks
        if len(meaningful_chunks) > 50:
            logger.warning(
                f"[Chunker] {len(meaningful_chunks)} chunks detected - too many! Processing monolithically"
            )
            return []

        logger.info(
            f"[Chunker] Created {len(meaningful_chunks)} chunks from {len(agenda_items)} agenda items"
        )

        # Convert chunks to items with metadata
        result = []
        for i, chunk in enumerate(meaningful_chunks):
            # Use the matched agenda item if we found one
            if chunk["agenda_item"]:
                item_num = chunk["agenda_item"]["number"]
                title = f"{item_num}. {chunk['agenda_item']['title']}"
            else:
                # Fallback: try to extract title from chunk
                title = f"Section {i + 1}"
                chunk_preview = chunk["text"][:300]
                for pattern, _ in agenda_patterns:
                    match = re.search(pattern, chunk_preview, re.IGNORECASE)
                    if match:
                        title_text = (
                            match.group(2).strip()
                            if match.lastindex and match.lastindex >= 2
                            else ""
                        )
                        if title_text:
                            title = f"{match.group(1)}. {title_text[:100]}"
                        break

            # Try to extract page number
            page_match = re.search(r"--- PAGE (\d+) ---", chunk["text"][:500])
            start_page = int(page_match.group(1)) if page_match else None

            result.append(
                {
                    "sequence": i + 1,
                    "title": title,
                    "text": chunk["text"],
                    "start_page": start_page,
                }
            )

        return result

    def _detect_cover_end(self, text: str) -> int:
        """
        Find where cover page ends and item content begins.
        Signals: first occurrence of repeating report headers, or large structural shift.

        Args:
            text: Full document text

        Returns:
            Character position where cover ends
        """
        # Common report header patterns (require newline before for specificity)
        report_headers = [
            r"\n\s*REPORT TO THE",
            r"\n\s*Item \d+\s*\n\s*Staff Report",  # "Item 4\n Staff Report"
            r"\n\s*STAFF REPORT\s*\n",  # Must be on own line
            r"\n\s*ACTION ITEM\s*\n",
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
            logger.debug(
                f"[Chunker] Found pattern '{found_pattern}' at position {earliest_pos}"
            )

        # Better fallback: find first page break after significant content
        if earliest_pos == len(text):
            logger.debug("[Chunker] No report headers found, using density analysis")
            # Look for content density change (agenda is dense, reports have whitespace)
            chunks = [text[i : i + 2000] for i in range(0, min(len(text), 20000), 2000)]
            for i, chunk in enumerate(chunks[1:], 1):
                # Count newlines per 100 chars as density metric
                density = chunk.count("\n") / (len(chunk) / 100)
                prev_density = chunks[i - 1].count("\n") / (len(chunks[i - 1]) / 100)
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

        Args:
            cover_text: Text of cover section

        Returns:
            List of agenda items: [{'item_id': str, 'item_number': int, 'title': str, ...}, ...]
        """
        items = []

        # Use regex patterns that work across line boundaries
        # Pattern 1: Numbered items (multiline and same-line)
        numbered_patterns = [
            r"\n\s*(\d+)\.\s*\n\s*([A-Z][^\n]{10,200})",  # "1.\n Title" (multiline)
            r"\n\s*(\d+)\.\s+([A-Z][^\n]{10,200})",  # "1. Title" (same line)
        ]

        for pattern in numbered_patterns:
            for match in re.finditer(pattern, "\n" + cover_text):
                num = int(match.group(1))
                title = match.group(2).strip()

                # Extract duration if present (e.g., "– 45 minutes")
                duration = None
                duration_match = re.search(
                    r"[–—-]\s*(\d+)\s*minutes?", title, re.IGNORECASE
                )
                if duration_match:
                    duration = int(duration_match.group(1))
                    title = title[: duration_match.start()].strip()

                # Skip if title is too short or looks like junk
                if len(title) < 10 or title.upper() in [
                    "MINUTES",
                    "AGENDA",
                    "MEETING",
                    "REPORTS",
                ]:
                    continue

                # Clean up title
                title = re.sub(r"\s+", " ", title)

                items.append(
                    {
                        "item_id": str(num),
                        "item_number": num,
                        "title": title[:150],  # Cap length
                        "duration": duration,
                        "is_subsection": False,
                    }
                )

        # Dedupe by item_id (prefer first occurrence)
        seen = set()
        deduped = []
        for item in items:
            if item["item_id"] not in seen:
                seen.add(item["item_id"])
                deduped.append(item)

        # Sort by item number
        deduped.sort(key=lambda x: x["item_number"])

        return deduped

    def _find_item_boundaries_by_title(
        self, body_text: str, agenda_items: List[Dict]
    ) -> List[Dict]:
        """
        Find where each cover agenda item appears in the body text.
        Searches for item titles from cover, using fuzzy matching.

        Args:
            body_text: Document body content
            agenda_items: Items extracted from cover

        Returns:
            List of boundaries: [{'start': int, 'item_id': str, 'title': str, ...}, ...]
        """
        boundaries = []

        for item in agenda_items:
            title = item["title"]
            item_id = item["item_id"]
            found = False

            # Strategy 1: Try exact title match (flexible whitespace)
            title_pattern = re.escape(title[:80])  # Use first 80 chars
            title_pattern = title_pattern.replace(
                r"\ ", r"\s+"
            )  # Allow flexible whitespace

            match = re.search(title_pattern, body_text, re.IGNORECASE)

            if match:
                boundaries.append(
                    {
                        "start": match.start(),
                        "item_id": item_id,
                        "title": title,
                        "match_type": "exact_title",
                    }
                )
                logger.debug(
                    f"[Chunker] Found item {item_id} by exact title at position {match.start()}"
                )
                found = True

            # Strategy 2: Try shorter title match (first 40 chars)
            if not found and len(title) > 40:
                short_pattern = re.escape(title[:40]).replace(r"\ ", r"\s+")
                match = re.search(short_pattern, body_text, re.IGNORECASE)
                if match:
                    boundaries.append(
                        {
                            "start": match.start(),
                            "item_id": item_id,
                            "title": title,
                            "match_type": "short_title",
                        }
                    )
                    logger.debug(
                        f"[Chunker] Found item {item_id} by short title at position {match.start()}"
                    )
                    found = True

            # Strategy 3: Try "Item X" pattern in footers
            if not found:
                footer_pattern = rf"Item\s+{re.escape(item_id)}[\s:]"
                match = re.search(footer_pattern, body_text, re.IGNORECASE)
                if match:
                    boundaries.append(
                        {
                            "start": match.start(),
                            "item_id": item_id,
                            "title": title,
                            "match_type": "footer_item",
                        }
                    )
                    logger.debug(
                        f"[Chunker] Found item {item_id} by footer at position {match.start()}"
                    )
                    found = True

            # Strategy 4: Try "Staff Report" header with item number nearby
            if not found:
                staff_report_pattern = rf"(?:Staff Report|STAFF REPORT).{{0,200}}?(?:Item\s+{re.escape(item_id)}|Report\s+#.*{re.escape(item_id)})"
                match = re.search(
                    staff_report_pattern, body_text, re.IGNORECASE | re.DOTALL
                )
                if match:
                    boundaries.append(
                        {
                            "start": match.start(),
                            "item_id": item_id,
                            "title": title,
                            "match_type": "staff_report",
                        }
                    )
                    logger.debug(
                        f"[Chunker] Found item {item_id} by staff report pattern at position {match.start()}"
                    )
                    found = True

            if not found:
                logger.warning(
                    f"[Chunker] Could not find item {item_id} '{title[:50]}...' in body text"
                )

        # Sort by position in document
        boundaries.sort(key=lambda x: x["start"])

        logger.info(
            f"[Chunker] Found {len(boundaries)}/{len(agenda_items)} items in body"
        )

        return boundaries
