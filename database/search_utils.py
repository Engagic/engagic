"""
Search utilities for finding text in meeting and item summaries.
"""

import re
from datetime import datetime
from typing import List, Dict, Optional
from database.db import UnifiedDatabase
from config import config

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

def build_engagic_url(banana: str, meeting_date: Optional[str], meeting_id: str) -> str:
    """
    Construct full Engagic URL for a meeting using clean date-id format.

    Args:
        banana: City identifier (e.g., 'nashvilleTN')
        meeting_date: ISO date string (may be None)
        meeting_id: Meeting ID

    Returns:
        Full URL like: https://engagic.org/nashvilleTN/2025-11-04-2111
    """
    if not meeting_id:
        meeting_id = "null"

    try:
        if meeting_date:
            dt = datetime.fromisoformat(meeting_date.replace('Z', '+00:00'))
            date_slug = dt.strftime('%Y-%m-%d')
        else:
            date_slug = "undated"
    except (ValueError, AttributeError):
        date_slug = "undated"

    return f"https://engagic.org/{banana}/{date_slug}-{meeting_id}"

def search_summaries(
    search_term: str,
    city_banana: Optional[str] = None,
    state: Optional[str] = None,
    case_sensitive: bool = False,
    db_path: Optional[str] = None
) -> List[Dict]:
    """
    Search for text in meeting and item summaries (individual occurrences).

    Note: For searching matter-level canonical summaries (deduplicated across meetings),
    use search_matters() instead.

    Returns complete meeting/item objects with all display data including
    matter fields for items that are part of tracked matters.

    Args:
        search_term: String to search for (e.g., "Beazer Homes", "Uber")
        city_banana: Optional city filter (e.g., 'nashvilleTN')
        state: Optional state filter (e.g., 'CA', 'TN')
        case_sensitive: Whether search should be case-sensitive
        db_path: Optional database path (defaults to env var)

    Returns:
        List of dicts with keys:
            - type: 'meeting' or 'item'
            - url: Full Engagic URL with clean slug (e.g., /nashvilleTN/2025-11-04-2111#bl2025-1005)
            - city: City name with state
            - date: Meeting date (ISO string)
            - meeting_title: Meeting title
            - item_title: Item title (only for items)
            - context: Text snippet around match
            - summary: Full summary markdown
            - agenda_url: HTML agenda URL (if available)
            - packet_url: PDF packet URL (if available)
            - attachments: Item attachments (only for items)
            - topics: Extracted topics
            - participation: Meeting participation info (only for meetings)
            - meeting_id: Meeting ID (string)
            - item_id: Item ID (only for items)
            - banana: City banana
            - matter_id: Matter ID (only for items with matters)
            - matter_file: Official matter file like "BL2025-1005" (only for items with matters)
            - matter_type: Matter type (Ordinance, Resolution, etc.) (only for items with matters)
            - agenda_number: Agenda position like "1." or "K. 87" (only for items)
            - sponsors: Sponsor names (only for items with matters)
    """
    if db_path is None:
        db_path = config.UNIFIED_DB_PATH

    db = UnifiedDatabase(db_path)
    try:
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
    
            # Strip markdown for context search
            clean_summary = strip_markdown(meeting.summary or '')
    
            # Find context around the match
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
                'summary': meeting.summary,
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
    
            # Strip markdown for context search
            clean_summary = strip_markdown(item.summary or '')
    
            # Find context around the match
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
    
            # Generate anchor matching frontend/backend logic: agenda_number > matter_file > item.id
            if item.agenda_number:
                clean = re.sub(r'[^a-z0-9]', '-', item.agenda_number.lower())
                clean = re.sub(r'-+', '-', clean).strip('-')
                anchor = f'item-{clean}'
            elif item.matter_file:
                anchor = re.sub(r'[^a-z0-9-]', '-', item.matter_file.lower())
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
                'summary': item.summary,
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
    finally:
        db.close()


def search_matters(
    search_term: str,
    city_banana: Optional[str] = None,
    state: Optional[str] = None,
    case_sensitive: bool = False,
    db_path: Optional[str] = None
) -> List[Dict]:
    """
    Search for text in canonical matter summaries (matter-level search).

    Uses Matter objects from MatterRepository for consistency with other search functions.

    Args:
        search_term: String to search for (e.g., "Beazer Homes", "affordable housing")
        city_banana: Optional city filter (e.g., 'nashvilleTN')
        state: Optional state filter (e.g., 'CA', 'TN')
        case_sensitive: Whether search should be case-sensitive
        db_path: Optional database path (defaults to env var)

    Returns:
        List of dicts with keys:
            - type: 'matter'
            - city: City name with state
            - matter_id: Matter ID
            - matter_file: Official matter file (e.g., "BL2025-1005")
            - matter_type: Type (Ordinance, Resolution, etc.)
            - title: Matter title
            - sponsors: Sponsor names (array, deserialized from JSON)
            - context: Text snippet around match
            - summary: Full canonical summary
            - topics: Canonical topics (array, deserialized from JSON)
            - appearance_count: Number of times this matter appeared
            - first_seen: First appearance date
            - last_seen: Most recent appearance date
            - banana: City banana
            - timeline_url: URL to view matter timeline
    """
    if db_path is None:
        db_path = config.UNIFIED_DB_PATH

    db = UnifiedDatabase(db_path)
    try:
        # Use repository method to get Matter objects
        matters = db.search_matters(search_term, city_banana, state, case_sensitive)

        results = []

        for matter in matters:
            # Get city name from cities table
            city_row = db.conn.execute(
                "SELECT name, state FROM cities WHERE banana = ?",
                (matter.banana,)
            ).fetchone()
    
            if not city_row:
                continue
    
            city = f"{city_row[0]}, {city_row[1]}"
    
            # Matter objects automatically deserialize JSON fields
            # Topics and sponsors are already lists
            sponsors = matter.sponsors if matter.sponsors else []
            topics = matter.canonical_topics if matter.canonical_topics else []
    
            # Strip markdown for context search
            clean_summary = strip_markdown(matter.canonical_summary or '')
    
            # Find context around the match
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
    
            # Build timeline URL
            if matter.matter_file:
                anchor = re.sub(r'[^a-z0-9-]', '-', matter.matter_file.lower())
            else:
                anchor = matter.id
            timeline_url = f"https://engagic.org/{matter.banana}?view=matters#{anchor}"
    
            results.append({
                'type': 'matter',
                'city': city,
                'matter_id': matter.id,
                'matter_file': matter.matter_file,
                'matter_type': matter.matter_type,
                'title': matter.title,
                'sponsors': sponsors,
                'context': context,
                'summary': matter.canonical_summary,
                'topics': topics,
                'appearance_count': matter.appearance_count,
                'first_seen': matter.first_seen.isoformat() if matter.first_seen else None,
                'last_seen': matter.last_seen.isoformat() if matter.last_seen else None,
                'banana': matter.banana,
                'timeline_url': timeline_url
            })
    
        return results
    finally:
        db.close()
