"""
Search utilities for finding text in meeting and item summaries.
"""

import os
import re
from datetime import datetime
from typing import List, Dict, Optional
from database.db import UnifiedDatabase

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
    except:
        return "unknown_date"

def build_engagic_url(banana: str, meeting_title: str, meeting_date: str, meeting_id: str) -> str:
    """
    Construct full Engagic URL for a meeting.
    
    Args:
        banana: City identifier (e.g., 'nashvilleTN')
        meeting_title: Meeting title (will be slugified)
        meeting_date: ISO date string
        meeting_id: Meeting ID
        
    Returns:
        Full URL like: https://engagic.org/nashvilleTN/metropolitan_council_2025_11_04_2111
    """
    slug = slugify(meeting_title)
    date_part = format_date(meeting_date)
    if not meeting_id:
        meeting_id = "null"
    return f"https://engagic.org/{banana}/{slug}_{date_part}_{meeting_id}"

def search_summaries(
    search_term: str,
    city_banana: Optional[str] = None,
    state: Optional[str] = None,
    case_sensitive: bool = False,
    db_path: Optional[str] = None
) -> List[Dict]:
    """
    Search for text in meeting and item summaries.

    Args:
        search_term: String to search for (e.g., "Beazer Homes", "Uber")
        city_banana: Optional city filter (e.g., 'nashvilleTN')
        state: Optional state filter (e.g., 'CA', 'TN')
        case_sensitive: Whether search should be case-sensitive
        db_path: Optional database path (defaults to env var)

    Returns:
        List of dicts with keys:
            - type: 'meeting' or 'item'
            - url: Full Engagic URL
            - city: City name with state
            - date: Meeting date
            - meeting_title: Meeting title
            - item_title: Item title (only for items)
            - context: Text snippet around the match
            - meeting_id: Meeting ID
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
        SELECT m.id, m.banana, m.title, m.date, m.summary,
               c.name as city_name, c.state
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
        meeting_title = row[2]
        meeting_date = row[3]
        summary = row[4]
        city = f"{row[5]}, {row[6]}"
        
        # Find context around the match
        if case_sensitive:
            match_pos = summary.find(search_term)
        else:
            match_pos = summary.lower().find(search_term.lower())
        
        if match_pos != -1:
            start = max(0, match_pos - 150)
            end = min(len(summary), match_pos + len(search_term) + 150)
            context = summary[start:end]
            if start > 0:
                context = "..." + context
            if end < len(summary):
                context = context + "..."
        else:
            context = summary[:300]
        
        url = build_engagic_url(banana, meeting_title, meeting_date, meeting_id)
        
        results.append({
            'type': 'meeting',
            'url': url,
            'city': city,
            'date': meeting_date,
            'meeting_title': meeting_title,
            'context': context,
            'meeting_id': meeting_id,
            'banana': banana
        })
    
    # Search in item summaries
    query = f'''
        SELECT i.id, i.meeting_id, i.title as item_title, i.summary,
               m.title as meeting_title, m.date, m.banana,
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
        item_title = row[2]
        summary = row[3]
        meeting_title = row[4]
        meeting_date = row[5]
        banana = row[6]
        city = f"{row[7]}, {row[8]}"
        
        # Find context around the match
        if case_sensitive:
            match_pos = summary.find(search_term)
        else:
            match_pos = summary.lower().find(search_term.lower())
        
        if match_pos != -1:
            start = max(0, match_pos - 150)
            end = min(len(summary), match_pos + len(search_term) + 150)
            context = summary[start:end]
            if start > 0:
                context = "..." + context
            if end < len(summary):
                context = context + "..."
        else:
            context = summary[:300]
        
        url = build_engagic_url(banana, meeting_title, meeting_date, meeting_id)
        # Add item anchor for item-level deep linking
        url = f"{url}#item-{item_id}"

        results.append({
            'type': 'item',
            'url': url,
            'city': city,
            'date': meeting_date,
            'meeting_title': meeting_title,
            'item_title': item_title,
            'context': context,
            'meeting_id': meeting_id,
            'item_id': item_id,
            'banana': banana
        })
    
    return results
