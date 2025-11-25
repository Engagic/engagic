"""
Weekly Digest Script

Runs every Sunday at 9am. Sends users a digest of:
1. Keyword matches (items mentioning their keywords)
2. Upcoming meetings this week (all meetings for their city)

Note: "Alert" in the codebase = Weekly Digest Subscription (not real-time alerts)

Usage:
    python3 -m userland.scripts.weekly_digest

Cron:
    0 9 * * 0 cd /root/engagic && .venv/bin/python -m userland.scripts.weekly_digest
"""

import asyncio
import os
import re
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config import config, get_logger
from database.db_postgres import Database
from userland.auth.jwt import generate_unsubscribe_token, init_jwt
from userland.email.emailer import EmailService
from userland.email.templates import DARK_MODE_CSS

logger = get_logger(__name__)


def highlight_keywords(text: str, keywords: List[str]) -> str:
    """
    Highlight all occurrences of keywords in text with HTML strong tags.

    Case-insensitive matching, preserves original case in output.

    Args:
        text: Plain text to search
        keywords: List of keywords to highlight

    Returns:
        HTML string with keywords wrapped in <strong> tags
    """
    if not text or not keywords:
        return text

    # Build regex pattern that matches any keyword (case-insensitive)
    # Use word boundaries to avoid partial word matches
    escaped_keywords = [re.escape(kw) for kw in keywords]
    pattern = r'\b(' + '|'.join(escaped_keywords) + r')\b'

    # Replace with highlighted version
    highlighted = re.sub(
        pattern,
        r'<strong style="color: #4f46e5; font-weight: 600;">\1</strong>',
        text,
        flags=re.IGNORECASE
    )

    return highlighted


def generate_anchor_id(item: Dict[str, Any]) -> str:
    """
    Generate item anchor ID matching frontend logic.

    Priority hierarchy:
    1. agenda_number (meeting-specific position, e.g., "5-E" → "item-5-e")
    2. matter_file (legislative file number, e.g., "BL2025-1005" → "bl2025-1005")
    3. item_id (fallback unique identifier)

    Args:
        item: Dict with optional agenda_number, matter_file, and item_id

    Returns:
        Anchor ID string suitable for URL fragments
    """
    # Priority 1: agenda_number (meeting-specific position)
    if item.get('agenda_number'):
        normalized = item['agenda_number'].lower()
        normalized = re.sub(r'[^a-z0-9]', '-', normalized)  # Replace non-alphanumeric with hyphens
        normalized = re.sub(r'-+', '-', normalized)         # Collapse multiple hyphens
        normalized = normalized.strip('-')                   # Trim leading/trailing hyphens
        return f"item-{normalized}"

    # Priority 2: matter_file (legislative identifier)
    if item.get('matter_file'):
        normalized = item['matter_file'].lower()
        normalized = re.sub(r'[^a-z0-9-]', '-', normalized)  # Keep hyphens, replace others
        return normalized

    # Priority 3: item ID (fallback) - extract just the sequence part
    item_id = item.get('item_id', '')
    if '_' in item_id:
        # Extract sequence from composite ID (city_meeting_sequence)
        sequence = item_id.split('_')[-1]
        return f"item-{sequence}"
    return f"item-{item_id}"


async def get_city_name(db: Database, city_banana: str) -> str:
    """Get formatted city name from banana (e.g., 'paloaltoCA' -> 'Palo Alto, CA')"""
    city = await db.cities.get_city(city_banana)
    if city:
        return f"{city.name}, {city.state}"
    return city_banana  # Fallback


async def get_upcoming_meetings(db: Database, city_banana: str, days_ahead: int = 7) -> List[Dict[str, Any]]:
    """
    Get upcoming meetings for a city in the next N days.

    FILTERS OUT cancelled/postponed meetings.
    Uses Database repository pattern (async PostgreSQL).
    """
    today = datetime.now().date()
    end_date = today + timedelta(days=days_ahead)

    async with db.pool.acquire() as conn:
        query = """
            SELECT id, banana, title, date, agenda_url, packet_url, status
            FROM meetings
            WHERE banana = $1
              AND date >= $2
              AND date <= $3
              AND (status IS NULL OR status NOT IN ('cancelled', 'postponed'))
            ORDER BY date ASC
            LIMIT 50
        """
        rows = await conn.fetch(query, city_banana, today, end_date)

    return [
        {
            'id': row['id'],
            'banana': row['banana'],
            'title': row['title'],
            'date': str(row['date']),
            'agenda_url': row['agenda_url'],
            'packet_url': row['packet_url'],
            'status': row['status']
        }
        for row in rows
    ]


async def find_keyword_matches(
    db: Database,
    city_banana: str,
    keywords: List[str],
    days_ahead: int = 7
) -> List[Dict[str, Any]]:
    """
    Find items in upcoming meetings that mention user's keywords.

    FILTERS OUT cancelled/postponed meetings.
    Uses direct async SQL queries for efficient searching.
    """
    if not keywords:
        return []

    today = datetime.now().date()
    end_date = today + timedelta(days=days_ahead)

    all_matches = []

    async with db.pool.acquire() as conn:
        for keyword in keywords:
            # Search for keyword in item summaries
            query = """
                SELECT i.id as item_id, i.meeting_id, i.title as item_title,
                       i.summary, i.agenda_number, i.matter_file, i.sequence,
                       m.title as meeting_title, m.date, m.banana,
                       m.agenda_url, m.status
                FROM items i
                JOIN meetings m ON i.meeting_id = m.id
                WHERE m.banana = $1
                  AND m.date >= $2
                  AND m.date <= $3
                  AND (m.status IS NULL OR m.status NOT IN ('cancelled', 'postponed'))
                  AND i.summary LIKE $4
                ORDER BY m.date ASC
            """

            rows = await conn.fetch(query, city_banana, today, end_date, f"%{keyword}%")

            for row in rows:
                # Extract context around keyword
                summary = row['summary'] or ""
                keyword_lower = keyword.lower()
                summary_lower = summary.lower()

                # Find keyword position and extract context
                context = ""
                if keyword_lower in summary_lower:
                    pos = summary_lower.index(keyword_lower)
                    start = max(0, pos - 150)
                    end = min(len(summary), pos + 150)
                    context = summary[start:end].strip()
                    if start > 0:
                        context = "..." + context
                    if end < len(summary):
                        context = context + "..."

                all_matches.append({
                    'keyword': keyword,
                    'item_id': row['item_id'],
                    'meeting_id': row['meeting_id'],
                    'item_title': row['item_title'],
                    'item_summary': summary,
                    'item_position': row['agenda_number'] or row['sequence'] or '?',
                    'meeting_title': row['meeting_title'],
                    'meeting_date': str(row['date']),
                    'agenda_url': row['agenda_url'],
                    'banana': row['banana'],
                    'context': context,
                    # Fields needed for proper anchor generation
                    'agenda_number': row['agenda_number'],
                    'matter_file': row['matter_file']
                })

    # Deduplicate by item_id and aggregate matched keywords
    deduplicated = {}
    for match in all_matches:
        item_id = match['item_id']
        if item_id not in deduplicated:
            deduplicated[item_id] = match.copy()
            deduplicated[item_id]['matched_keywords'] = [match['keyword']]
        else:
            # Item already exists, just add this keyword if not already present
            if match['keyword'] not in deduplicated[item_id]['matched_keywords']:
                deduplicated[item_id]['matched_keywords'].append(match['keyword'])

    return list(deduplicated.values())


def build_digest_email(
    user_name: str,
    city_name: str,
    city_banana: str,
    keyword_matches: List[Dict[str, Any]],
    keywords: List[str],
    upcoming_meetings: List[Dict[str, Any]],
    app_url: str,
    unsubscribe_token: str
) -> str:
    """
    Build HTML email for weekly digest.

    Clean format: Upcoming meetings first, then keyword matches.
    Uses shared template components with full dark mode support.
    """

    # Format meeting dates
    def format_date(date_str: str) -> str:
        date_obj = datetime.fromisoformat(date_str)
        return date_obj.strftime("%a, %b %d")

    # Header with branding
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <title>This week in {city_name}</title>
{DARK_MODE_CSS}
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'IBM Plex Mono', 'Menlo', 'Monaco', 'Courier New', monospace;">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f8fafc;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width: 600px; background-color: #ffffff; border: 2px solid #e2e8f0; border-radius: 11px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">

                    <!-- Branded Header -->
                    <tr>
                        <td style="padding: 32px 40px 28px 40px; background-color: #4f46e5; border-radius: 9px 9px 0 0;">
                            <div style="margin-bottom: 20px; display: flex; align-items: center; gap: 16px;">
                                <img src="https://engagic.org/icon-192.png" alt="Engagic" style="width: 48px; height: 48px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);" />
                                <div style="display: inline-block; padding: 6px 14px; background-color: rgba(255, 255, 255, 0.15); border-radius: 6px; backdrop-filter: blur(10px);">
                                    <span style="font-family: 'IBM Plex Mono', monospace; font-size: 18px; font-weight: 700; color: #ffffff; letter-spacing: 0.02em;">engagic</span>
                                </div>
                            </div>
                            <h1 style="margin: 0 0 10px 0; font-size: 26px; font-weight: 700; color: #ffffff; line-height: 1.3; letter-spacing: -0.02em; font-family: 'IBM Plex Mono', monospace;">
                                This week in {city_name}
                            </h1>
                            <p style="margin: 0; font-size: 15px; color: #ffffff; opacity: 0.92; font-family: Georgia, serif; line-height: 1.5;">
                                Your weekly civic digest
                            </p>
                        </td>
                    </tr>
"""

    # Upcoming Meetings Section FIRST (always shown if there are any)
    if upcoming_meetings:
        html += """
                    <tr>
                        <td style="padding: 32px 40px 24px 40px;">
                            <h2 style="margin: 0 0 20px 0; font-size: 13px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.1em; font-family: 'IBM Plex Mono', monospace;">
                                Upcoming Meetings This Week
                            </h2>
"""
        for meeting in upcoming_meetings:
            meeting_date_obj = datetime.fromisoformat(meeting['date'])
            meeting_slug = f"{meeting_date_obj.strftime('%Y-%m-%d')}-{meeting['id']}"
            meeting_url = f"{app_url}/{meeting['banana']}/{meeting_slug}"

            html += f"""
                            <div style="margin-bottom: 16px; padding: 20px 24px; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; border-left: 4px solid #4f46e5; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                                <p style="margin: 0 0 12px 0; font-size: 16px; font-weight: 600; color: #0f172a; line-height: 1.4; font-family: 'IBM Plex Mono', monospace;">
                                    {format_date(meeting['date'])} - {meeting['title']}
                                </p>
                                <a href="{meeting_url}" style="color: #4f46e5; text-decoration: none; font-size: 14px; font-weight: 600; font-family: 'IBM Plex Mono', monospace; transition: color 0.2s;">
                                    View agenda →
                                </a>
                            </div>
"""
        html += """
                        </td>
                    </tr>
"""

    # Keyword Matches Section (if any)
    if keyword_matches:
        html += f"""
                    <tr>
                        <td style="padding: 32px 40px 24px 40px; border-top: 2px solid #e2e8f0;">
                            <h2 style="margin: 0 0 20px 0; font-size: 13px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 0.1em; font-family: 'IBM Plex Mono', monospace;">
                                Your Keywords: {', '.join(keywords).upper()}
                            </h2>
"""
        for match in keyword_matches:
            meeting_date_obj = datetime.fromisoformat(match['meeting_date'])
            meeting_slug = f"{meeting_date_obj.strftime('%Y-%m-%d')}-{match['meeting_id']}"
            meeting_url = f"{app_url}/{match['banana']}/{meeting_slug}"

            # Generate proper anchor matching frontend logic
            anchor = generate_anchor_id(match)
            item_url = f"{meeting_url}#{anchor}"

            # Use context field (keyword-highlighted text) instead of summary
            context = match.get('context', match.get('item_summary', ''))
            if len(context) > 300:
                context = context[:297] + "..."

            # Get all matched keywords (from deduplicated list) or fallback to single keyword
            matched_keywords = match.get('matched_keywords', [match.get('keyword', '')])
            keywords_display = '", "'.join(matched_keywords)

            # Highlight all matched keywords in the context text
            context = highlight_keywords(context, matched_keywords)

            html += f"""
                            <div style="margin-bottom: 24px; padding: 24px; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; border-left: 4px solid #4f46e5; box-shadow: 0 2px 4px rgba(0,0,0,0.06);">
                                <p style="margin: 0 0 10px 0; font-size: 17px; font-weight: 600; color: #0f172a; line-height: 1.4; font-family: 'IBM Plex Mono', monospace;">
                                    {match['item_title']}
                                </p>
                                <p style="margin: 0 0 14px 0; font-size: 13px; color: #64748b; font-family: Georgia, serif; font-style: italic;">
                                    {match['meeting_title']} • {format_date(match['meeting_date'])}
                                </p>
                                <p style="margin: 0 0 14px 0; font-size: 12px; color: #64748b; font-family: Georgia, serif;">
                                    Matched: <strong style="color: #4f46e5; font-weight: 600;">"{keywords_display}"</strong>
                                </p>
                                <p style="margin: 0 0 20px 0; font-size: 14px; color: #334155; line-height: 1.7; font-family: Georgia, serif;">
                                    {context}
                                </p>
                                <a href="{item_url}" style="display: inline-block; padding: 12px 28px; background-color: #4f46e5; color: #ffffff; text-decoration: none; border-radius: 7px; font-weight: 600; font-size: 14px; font-family: 'IBM Plex Mono', monospace; box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2);">
                                    View Item →
                                </a>
                            </div>
"""
        html += """
                        </td>
                    </tr>
"""

    # Footer with one-click unsubscribe (CAN-SPAM compliant)
    unsubscribe_url = f"https://api.engagic.org/api/auth/unsubscribe?token={unsubscribe_token}"
    html += f"""
                    <tr>
                        <td style="padding: 32px 40px; border-top: 1px solid #e2e8f0;">
                            <p style="margin: 0 0 16px 0; font-size: 12px; color: #475569; font-family: Georgia, serif; line-height: 1.7;">
                                You're receiving this because you're watching {city_name}
                            </p>
                            <p style="margin: 0 0 16px 0; font-size: 12px; color: #64748b; font-family: Georgia, serif; line-height: 1.7;">
                                Engagic is free and open-source. If you find it valuable, please <a href="https://engagic.org/about/donate" style="color: #8B5CF6; text-decoration: none; font-weight: 600;">support the project</a>.
                            </p>
                            <p style="margin: 0 0 8px 0; font-size: 12px; color: #64748b; font-family: Georgia, serif;">
                                Questions? Visit <a href="https://engagic.org" style="color: #4f46e5; text-decoration: none;">engagic.org</a>
                            </p>
                            <p style="margin: 0; font-size: 12px; font-family: Georgia, serif;">
                                <a href="{app_url}/dashboard" style="color: #64748b; text-decoration: underline;">Manage subscription</a>
                                <span style="margin: 0 8px; color: #cbd5e1;">|</span>
                                <a href="{unsubscribe_url}" style="color: #64748b; text-decoration: none;">Unsubscribe</a>
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

    return html


async def send_weekly_digest():
    """
    Main function: Send weekly digests to all active users.

    Note: This queries "alerts" but they represent weekly digest subscriptions.
    """

    app_url = os.getenv('APP_URL', 'https://engagic.org')

    # Initialize JWT for unsubscribe token generation
    if config.USERLAND_JWT_SECRET:
        try:
            init_jwt(config.USERLAND_JWT_SECRET)
        except ValueError:
            pass  # Already initialized

    logger.info("Starting weekly digest process...")

    db = await Database.create()
    try:
        email_service = EmailService()

        # Get all active alerts (weekly digest subscriptions)
        active_alerts = await db.userland.get_active_alerts()
        logger.info(f"Found {len(active_alerts)} active alerts")

        sent_count = 0
        error_count = 0

        for alert in active_alerts:
            try:
                # Get user
                user = await db.userland.get_user(alert.user_id)
                if not user:
                    logger.warning(f"User not found for alert {alert.id}")
                    continue

                # Get primary city (first city in alert)
                if not alert.cities or len(alert.cities) == 0:
                    logger.warning(f"Alert {alert.id} has no cities configured")
                    continue

                primary_city = alert.cities[0]
                logger.info(f"Processing digest for {user.email} ({primary_city})...")

                # Get actual city name (not banana)
                city_name = await get_city_name(db, primary_city)

                # Get keyword matches (direct SQL queries)
                keywords = alert.criteria.get('keywords', [])
                keyword_matches = await find_keyword_matches(db, primary_city, keywords, days_ahead=10)

                # Get upcoming meetings (direct SQL queries)
                upcoming_meetings = await get_upcoming_meetings(db, primary_city, days_ahead=10)

                # Skip if no content
                if not keyword_matches and not upcoming_meetings:
                    logger.info(f"No content for {user.email}, skipping")
                    continue

                # Generate unsubscribe token for this user
                unsubscribe_token = generate_unsubscribe_token(user.id)

                # Build email
                html = build_digest_email(
                    user_name=user.name,
                    city_name=city_name,
                    city_banana=primary_city,
                    keyword_matches=keyword_matches,
                    keywords=keywords,
                    upcoming_meetings=upcoming_meetings,
                    app_url=app_url,
                    unsubscribe_token=unsubscribe_token
                )

                # Send email
                subject = f"This week in {city_name}"
                if keyword_matches:
                    subject += f" - {len(keyword_matches)} keyword match{'es' if len(keyword_matches) > 1 else ''}"

                await email_service.send_email(
                    to_email=user.email,
                    subject=subject,
                    html_body=html
                )

                sent_count += 1
                logger.info(f"Sent digest to {user.email}")

            except Exception as e:
                error_count += 1
                logger.error(f"Failed to send digest for alert {alert.id}: {e}")
                continue

        logger.info(f"Weekly digest complete: {sent_count} sent, {error_count} errors")
        return sent_count, error_count
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(send_weekly_digest())
