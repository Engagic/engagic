"""
Search utilities for finding text in meeting and item summaries.
"""

import os
import re
from datetime import datetime
from typing import List, Dict, Optional
from database.db import UnifiedDatabase

def strip_markdown(text: str) -> str:
    """
    Remove markdown formatting for cleaner search and display.

    Handles:
    - Bold/italic (**text**, *text*, __text__, _text_)
    - Headers (# Header)
    - Links ([text](url))
    - List markers (-, *, 1.)

    Args:
        text: Raw markdown text

    Returns:
        Plain text without markdown syntax
    """
    if not text:
        return text

    # Headers (must come before bold/italic to avoid leaving orphaned #)
    text = re.sub(r'#{1,6}\s+', '', text)

    # Bold/italic (nested patterns: **bold**, __bold__, *italic*, _italic_)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold**
    text = re.sub(r'__(.+?)__', r'\1', text)      # __bold__
    text = re.sub(r'\*(.+?)\*', r'\1', text)      # *italic*
    text = re.sub(r'_(.+?)_', r'\1', text)        # _italic_

    # Links [text](url) -> text
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)

    # List markers at start of line
    text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    return text

def slugify(text: str) -> str:
    """Convert text to URL-friendly slug"""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '_', text)
    return text.strip('_')

def format_date(date_str: Optional[str]) -> str:
    """Convert ISO date to YYYY_MM_DD format"""
    if not date_str:
        return "unknown_date"
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime('%Y_%m_%d')
    except (ValueError, AttributeError):
        return "unknown_date"

def build_engagic_url(banana: str, meeting_date: str, meeting_id: str) -> str:
    """
    Construct full Engagic URL for a meeting using clean date-id format.

    Args:
        banana: City identifier (e.g., 'nashvilleTN')
        meeting_date: ISO date string
        meeting_id: Meeting ID

    Returns:
        Full URL like: https://engagic.org/nashvilleTN/2025-11-04-2111
    """
    if not meeting_id:
        meeting_id = "null"

    try:
        dt = datetime.fromisoformat(meeting_date.replace('Z', '+00:00'))
        date_slug = dt.strftime('%Y-%m-%d')
    except (ValueError, AttributeError):
        date_slug = "undated"

    return f"https://engagic.org/{banana}/{date_slug}-{meeting_id}"

def parse_summary_sections(summary: str) -> Dict[str, Optional[str]]:
    """
    Parse summary markdown to extract Thinking and Summary sections.

    Handles multiple formats:
    - ## Thinking (heading format from engagic frontend)
    - **Thinking** (bold inline format)
    - Thinking (bare text at start)

    Args:
        summary: Full summary markdown (may contain Thinking section)

    Returns:
        dict with keys:
            - thinking: Content of Thinking section (if present)
            - summary: Content of Summary section (without Thinking)
    """
    if not summary:
        return {'thinking': None, 'summary': ''}

    # Check for "## Thinking" heading format first
    parts = re.split(r'^## Thinking\s*$', summary, flags=re.MULTILINE)
    if len(parts) >= 2:
        before = parts[0].strip()
        after_thinking = parts[1]

        # Find next section heading to split thinking from summary
        next_section = re.search(r'^##\s+', after_thinking, flags=re.MULTILINE)

        if next_section:
            thinking_end = next_section.start()
            thinking_content = after_thinking[:thinking_end].strip()
            summary_content = after_thinking[thinking_end:].strip()
            full_summary = (before + '\n\n' + summary_content).strip() if before else summary_content
            return {
                'thinking': thinking_content,
                'summary': full_summary
            }

        # No next section - everything after is thinking
        return {
            'thinking': after_thinking.strip(),
            'summary': before if before else ''
        }

    # Check for inline "Thinking ... Summary:" format
    # Look for "Summary:" marker which indicates where actual summary starts
    summary_marker = re.search(r'\b(?:##\s*)?Summary\s*:?\s*', summary, flags=re.IGNORECASE)

    if summary_marker:
        # Everything before "Summary:" is thinking (if it mentions "Thinking")
        before_summary = summary[:summary_marker.start()].strip()
        after_summary = summary[summary_marker.end():].strip()

        # Check if the before part contains "Thinking"
        if re.search(r'\bThinking\b', before_summary, flags=re.IGNORECASE):
            # Strip "Thinking" or "**Thinking**" prefix from thinking content
            thinking_clean = re.sub(r'^(?:\*\*)?Thinking(?:\*\*)?\s*', '', before_summary, flags=re.IGNORECASE).strip()
            return {
                'thinking': thinking_clean,
                'summary': after_summary
            }
        else:
            # No thinking, but found Summary: marker
            return {
                'thinking': None,
                'summary': after_summary
            }

    # No clear markers - return full summary
    return {'thinking': None, 'summary': summary}


def search_summaries(
    search_term: str,
    city_banana: Optional[str] = None,
    state: Optional[str] = None,
    case_sensitive: bool = False,
    db_path: Optional[str] = None
) -> List[Dict]:
    """
    Search for text in meeting and item summaries.

    Returns complete meeting/item objects with all display data needed
    for motioncount frontend (attachments, agenda URLs, full summaries, etc).

    Args:
        search_term: String to search for (e.g., "Beazer Homes", "Uber")
        city_banana: Optional city filter (e.g., 'nashvilleTN')
        state: Optional state filter (e.g., 'CA', 'TN')
        case_sensitive: Whether search should be case-sensitive
        db_path: Optional database path (defaults to env var)

    Returns:
        List of dicts with keys:
            - type: 'meeting' or 'item'
            - url: Full Engagic URL (for reference only)
            - city: City name with state
            - date: Meeting date (ISO string)
            - meeting_title: Meeting title
            - item_title: Item title (only for items)
            - context: Text snippet around match (from Summary section)
            - summary: Full summary markdown (Thinking section removed)
            - thinking: Thinking section markdown (if present)
            - agenda_url: HTML agenda URL (if available)
            - packet_url: PDF packet URL (if available)
            - attachments: Item attachments (only for items)
            - topics: Extracted topics
            - participation: Meeting participation info
            - meeting_id: Meeting ID (integer)
            - item_id: Item ID (only for items)
            - banana: City banana
    """
    if db_path is None:
        db_path = os.getenv('ENGAGIC_UNIFIED_DB', '/root/engagic/data/engagic.db')

    db = UnifiedDatabase(db_path)
    conn = db.conn

    results = []
    like_pattern = f'%{search_term}%'

    # Build filter clauses
    filters = []
    city_params = [like_pattern]

    if city_banana:
        filters.append("m.banana = ?")
        city_params.append(city_banana)

    if state:
        filters.append("c.state = ?")
        city_params.append(state.upper())

    city_filter = ""
    if filters:
        city_filter = " AND " + " AND ".join(filters)

    # Search in meeting summaries
    query = f'''
        SELECT m.id, m.banana, c.name as city_name, c.state
        FROM meetings m
        JOIN cities c ON m.banana = c.banana
        WHERE m.summary IS NOT NULL
          AND m.summary LIKE ?
          {city_filter}
        ORDER BY m.date DESC
    '''

    cursor = conn.execute(query, city_params)

    for row in cursor.fetchall():
        meeting_id = row[0]
        banana = row[1]
        city = f"{row[2]}, {row[3]}"

        # Fetch complete meeting object
        meeting = db.get_meeting(meeting_id)
        if not meeting:
            continue

        # Parse summary sections
        sections = parse_summary_sections(meeting.summary or '')
        summary_only = sections['summary']
        thinking = sections['thinking']

        # Strip markdown for context search
        clean_summary = strip_markdown(summary_only)

        # Find context around the match in Summary section (not Thinking)
        if case_sensitive:
            match_pos = clean_summary.find(search_term)
        else:
            match_pos = clean_summary.lower().find(search_term.lower())

        if match_pos != -1:
            start = max(0, match_pos - 150)
            end = min(len(clean_summary), match_pos + len(search_term) + 150)
            context = clean_summary[start:end]
            if start > 0:
                context = "..." + context
            if end < len(clean_summary):
                context = context + "..."
        else:
            context = clean_summary[:300]

        url = build_engagic_url(banana, meeting.date.isoformat() if meeting.date else None, meeting.id)

        results.append({
            'type': 'meeting',
            'url': url,
            'city': city,
            'date': meeting.date.isoformat() if meeting.date else None,
            'meeting_title': meeting.title,
            'context': context,
            'summary': summary_only,
            'thinking': thinking,
            'agenda_url': meeting.agenda_url,
            'packet_url': meeting.packet_url,
            'topics': meeting.topics,
            'participation': meeting.participation,
            'meeting_status': meeting.status,
            'meeting_id': meeting.id,
            'banana': banana
        })

    # Search in item summaries
    query = f'''
        SELECT i.id, i.meeting_id, m.banana,
               c.name as city_name, c.state
        FROM items i
        JOIN meetings m ON i.meeting_id = m.id
        JOIN cities c ON m.banana = c.banana
        WHERE i.summary IS NOT NULL
          AND i.summary LIKE ?
          {city_filter}
        ORDER BY m.date DESC
    '''

    cursor = conn.execute(query, city_params)

    for row in cursor.fetchall():
        item_id = row[0]
        meeting_id = row[1]
        banana = row[2]
        city = f"{row[3]}, {row[4]}"

        # Fetch complete meeting object
        meeting = db.get_meeting(meeting_id)
        if not meeting:
            continue

        # Fetch complete item object
        items = db.get_agenda_items(meeting_id)
        item = next((i for i in items if i.id == item_id), None)
        if not item:
            continue

        # Parse summary sections (items can also have Thinking sections)
        sections = parse_summary_sections(item.summary or '')
        summary_only = sections['summary']
        thinking = sections['thinking']

        # Strip markdown for context search
        clean_summary = strip_markdown(summary_only)

        # Find context around the match in Summary section (not Thinking)
        if case_sensitive:
            match_pos = clean_summary.find(search_term)
        else:
            match_pos = clean_summary.lower().find(search_term.lower())

        if match_pos != -1:
            start = max(0, match_pos - 150)
            end = min(len(clean_summary), match_pos + len(search_term) + 150)
            context = clean_summary[start:end]
            if start > 0:
                context = "..." + context
            if end < len(clean_summary):
                context = context + "..."
        else:
            context = clean_summary[:300]

        url = build_engagic_url(banana, meeting.date.isoformat() if meeting.date else None, meeting.id)

        # Generate human-readable anchor (prefer matter_file, then agenda_number, fallback to item.id)
        if item.matter_file:
            anchor = re.sub(r'[^a-z0-9-]', '-', item.matter_file.lower())
        elif item.agenda_number:
            clean = re.sub(r'[^a-z0-9]', '-', item.agenda_number.lower())
            clean = re.sub(r'-+', '-', clean).strip('-')
            anchor = f'item-{clean}'
        else:
            anchor = f"item-{item.id}"

        url = f"{url}#{anchor}"

        results.append({
            'type': 'item',
            'url': url,
            'city': city,
            'date': meeting.date.isoformat() if meeting.date else None,
            'meeting_title': meeting.title,
            'item_title': item.title,
            'context': context,
            'summary': summary_only,
            'thinking': thinking,
            'agenda_url': meeting.agenda_url,
            'packet_url': meeting.packet_url,
            'attachments': item.attachments,
            'topics': item.topics,
            'item_sequence': item.sequence,
            'meeting_id': meeting.id,
            'item_id': item.id,
            'banana': banana,
            # Matter fields (new)
            'matter_id': item.matter_id,
            'matter_file': item.matter_file,
            'matter_type': item.matter_type,
            'agenda_number': item.agenda_number,
            'sponsors': item.sponsors
        })

    return results
