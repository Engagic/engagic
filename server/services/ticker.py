"""
Ticker service for generating news ticker items from meetings
"""

import re
from typing import Dict, Any, Optional
from datetime import datetime

from database.db import UnifiedDatabase


def extract_excerpt(summary: str, prefer_middle: bool = True) -> str:
    """
    Extract the most interesting excerpt from a meeting summary.

    Scores sentences based on:
    - Dollar amounts (high value)
    - Action words (proposed, approved, etc.)
    - Numbers and percentages
    - Position in text (prefer middle)
    - Length (prefer substantial sentences)

    Returns: Clean, readable excerpt suitable for ticker display
    """
    if not summary:
        return ""

    # Remove markdown headers, bold, and common boilerplate
    cleaned = summary
    cleaned = re.sub(r'#{1,6}\s+', '', cleaned)
    cleaned = re.sub(r'\*\*', '', cleaned)
    cleaned = re.sub(r'\*', '', cleaned)
    cleaned = re.sub(r"Here's a summary[^:]*:", '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Here is a summary[^:]*:", '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"This summary[^:]*:", '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"This is a summary[^:]*:", '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Summary of[^:]*:", '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Key Agenda Items", '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Date:[^Time]*", '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Time:[^Location]*", '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Location:[^\n]*", '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"Meeting Summary[^-]*-[^-]*-[^T]*", '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    # Split into sentences (filter out very short ones)
    sentences = [s.strip() for s in re.split(r'[.!?]+', cleaned) if len(s.strip()) > 30]

    if not sentences:
        return cleaned[:150]

    # Score sentences to find the most interesting one
    scored_sentences = []
    for idx, sentence in enumerate(sentences):
        score = 0

        # Prefer middle sentences (skip intro/outro boilerplate)
        if idx > 0 and idx < len(sentences) - 1:
            score += 10

        # Look for dollar amounts (strong signal of important content)
        if re.search(r'\$[\d,]+', sentence):
            score += 15

        # Look for action words (policy decisions)
        if re.search(r'(proposed|approved|amendment|ordinance|agreement|contract|budget|allocate|establish|require)', sentence, re.IGNORECASE):
            score += 10

        # Look for numbers (percentages, counts - concrete data)
        if re.search(r'\d+%|\d+ (units|homes|acres|projects)', sentence):
            score += 8

        # Penalize very short sentences
        if len(sentence) < 50:
            score -= 5

        # Prefer longer, detailed sentences
        if len(sentence) > 100:
            score += 5

        scored_sentences.append({'sentence': sentence, 'score': score, 'idx': idx})

    # Get highest scoring sentence
    scored_sentences.sort(key=lambda x: x['score'], reverse=True)
    excerpt = scored_sentences[0]['sentence'].strip()

    # Truncate if too long (ticker display constraint)
    if len(excerpt) > 200:
        excerpt = excerpt[:197] + '...'

    return excerpt


def generate_ticker_item(meeting: Dict[str, Any], db: UnifiedDatabase) -> Optional[Dict[str, str]]:
    """
    Generate a single ticker item from a meeting.

    Args:
        meeting: Meeting dict with banana, date, title, summary, items, etc.

    Returns:
        Ticker item dict with city, date, excerpt, url or None if invalid
    """
    banana = meeting.get('banana')
    if not banana:
        return None

    # Look up city from database (single source of truth)
    city = db.get_city(banana=banana)
    if not city:
        return None

    city_name = city.name
    state = city.state

    # Format date
    try:
        date_obj = datetime.fromisoformat(meeting['date'].replace('Z', '+00:00'))
        date_str = date_obj.strftime('%b %-d, %Y')
    except Exception:
        return None

    # Extract excerpt (prefer item summaries, fall back to meeting summary)
    excerpt = ""

    # Try to get excerpt from items first (more specific and juicy)
    items = meeting.get('items', [])
    if items:
        items_with_summaries = [item for item in items if item.get('summary')]
        if items_with_summaries:
            # Pick a random item (backend will handle randomization)
            import random
            random_item = random.choice(items_with_summaries)
            excerpt = extract_excerpt(random_item['summary'])

    # Fall back to meeting summary
    if not excerpt and meeting.get('summary'):
        excerpt = extract_excerpt(meeting['summary'])

    # Skip if no valid excerpt
    if not excerpt or len(excerpt) < 20:
        return None

    # Generate meeting URL
    # Format: /{banana}/{meeting_slug}
    # meeting_slug must match frontend format: {title}_{date}_{id}
    try:
        meeting_id = meeting.get('id')
        if not meeting_id:
            return None

        date_obj = datetime.fromisoformat(meeting['date'].replace('Z', '+00:00'))
        year = date_obj.year
        month = str(date_obj.month).zfill(2)
        day = str(date_obj.day).zfill(2)
        date_slug = f"{year}_{month}_{day}"

        # Clean title: lowercase, alphanumeric only, underscores
        title = meeting.get('title', 'meeting')
        title_slug = re.sub(r'[^a-z0-9]+', '_', title.lower()).strip('_')[:50]

        # Format matches frontend generateMeetingSlug: {title}_{date}_{id}
        meeting_slug = f"{title_slug}_{date_slug}_{meeting_id}"
        url = f"/{banana}/{meeting_slug}"
    except Exception:
        return None

    return {
        'city': f"{city_name}, {state}",
        'date': date_str,
        'excerpt': excerpt,
        'url': url
    }
