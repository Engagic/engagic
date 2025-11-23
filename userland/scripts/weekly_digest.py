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

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from userland.database.db import UserlandDB
from userland.email.emailer import EmailService
from database.db import UnifiedDatabase
from database.search_utils import search_summaries
from config import config

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("engagic.weekly_digest")


def get_city_name(city_banana: str) -> str:
    """Get formatted city name from banana (e.g., 'paloaltoCA' -> 'Palo Alto, CA')"""
    db = UnifiedDatabase(config.UNIFIED_DB_PATH)
    try:
        city = db.get_city(city_banana)
        if city:
            return f"{city.name}, {city.state}"
        return city_banana  # Fallback
    finally:
        db.close()


def get_upcoming_meetings(city_banana: str, days_ahead: int = 7) -> List[Dict[str, Any]]:
    """
    Get upcoming meetings for a city in the next N days.

    FILTERS OUT cancelled/postponed meetings.
    Uses UnifiedDatabase repository pattern (not raw SQL).
    """
    db = UnifiedDatabase(config.UNIFIED_DB_PATH)
    try:
        today = datetime.now().date()
        end_date = today + timedelta(days=days_ahead)

        meetings = db.get_meetings(
            bananas=[city_banana],
            start_date=datetime.combine(today, datetime.min.time()),
            end_date=datetime.combine(end_date, datetime.max.time()),
            limit=50
        )

        # Filter out cancelled/postponed meetings
        result = []
        for meeting in meetings:
            # Skip cancelled or postponed meetings
            if meeting.status and meeting.status.lower() in ['cancelled', 'postponed']:
                continue

            result.append({
                'id': meeting.id,
                'banana': meeting.banana,
                'title': meeting.title,
                'date': meeting.date.isoformat() if meeting.date else None,
                'agenda_url': meeting.agenda_url,
                'packet_url': meeting.packet_url,
                'status': meeting.status
            })

        return result
    finally:
        db.close()


def find_keyword_matches(
    city_banana: str,
    keywords: List[str],
    days_ahead: int = 7
) -> List[Dict[str, Any]]:
    """
    Find items in upcoming meetings that mention user's keywords.

    FILTERS OUT cancelled/postponed meetings.
    Uses search_summaries() from database layer + date/status post-filter.
    """
    if not keywords:
        return []

    today = datetime.now().date()
    end_date = today + timedelta(days=days_ahead)

    all_matches = []
    for keyword in keywords:
        matches = search_summaries(
            search_term=keyword,
            city_banana=city_banana,
            db_path=config.UNIFIED_DB_PATH
        )

        # Post-filter by date range AND status (search_summaries doesn't do this)
        for match in matches:
            if match.get('type') == 'item' and match.get('date'):
                try:
                    match_date = datetime.fromisoformat(match['date']).date()

                    # Skip if outside date range
                    if not (today <= match_date <= end_date):
                        continue

                    # Skip cancelled/postponed meetings
                    meeting_status = match.get('status', '')
                    if meeting_status and meeting_status.lower() in ['cancelled', 'postponed']:
                        continue

                    # Normalize field names for email template
                    all_matches.append({
                        'keyword': keyword,
                        'item_id': match['item_id'],
                        'meeting_id': match['meeting_id'],
                        'item_title': match['item_title'],
                        'item_summary': match.get('summary', ''),
                        'item_position': match.get('agenda_number', match.get('sequence', '?')),
                        'meeting_title': match['meeting_title'],
                        'meeting_date': match['date'],
                        'agenda_url': match.get('agenda_url'),
                        'banana': match['banana'],
                        'context': match.get('context', '')
                    })
                except (ValueError, TypeError):
                    continue

    return all_matches


def build_digest_email(
    user_name: str,
    city_name: str,
    city_banana: str,
    keyword_matches: List[Dict[str, Any]],
    keywords: List[str],
    upcoming_meetings: List[Dict[str, Any]],
    app_url: str
) -> str:
    """
    Build HTML email for weekly digest.

    Format: Similar to old alert digest (better information display)
    with item-level anchor links to specific items.
    """

    # Format meeting dates
    def format_date(date_str: str) -> str:
        date_obj = datetime.fromisoformat(date_str)
        return date_obj.strftime("%b %d, %Y")

    # Header
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'IBM Plex Mono', monospace;">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f8fafc;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width: 600px; background-color: #ffffff; border: 2px solid #e2e8f0; border-radius: 11px;">

                    <!-- Header -->
                    <tr>
                        <td style="padding: 40px 40px 24px 40px; text-align: center;">
                            <h1 style="margin: 0; font-size: 32px; font-weight: 700; color: #0f172a;">
                                engagic
                            </h1>
                            <p style="margin: 8px 0 0 0; font-size: 14px; color: #64748b; font-family: Georgia, serif;">
                                Statewide Municipal Intelligence
                            </p>
                        </td>
                    </tr>

                    <!-- Digest Info -->
                    <tr>
                        <td style="padding: 0 40px 32px 40px; border-bottom: 1px solid #e2e8f0;">
                            <p style="margin: 0; font-size: 15px; color: #475569; font-family: Georgia, serif;">
                                Your digest: <strong>{', '.join(keywords) if keywords else 'all items'}</strong><br>
                                Found <strong>{len(keyword_matches)} item{'s' if len(keyword_matches) != 1 else ''}</strong> in {city_name}
                            </p>
                        </td>
                    </tr>
"""

    # Keyword Matches Section
    if keyword_matches:
        # Group by meeting
        meetings_map: Dict[str, Any] = {}
        for match in keyword_matches:
            mid = match['meeting_id']
            if mid not in meetings_map:
                meetings_map[mid] = {
                    'title': match['meeting_title'],
                    'date': match['meeting_date'],
                    'banana': match['banana'],
                    'agenda_url': match.get('agenda_url'),
                    'items': []
                }
            meetings_map[mid]['items'].append(match)

        for meeting_id, meeting_data in meetings_map.items():
            # Build meeting slug and URL
            meeting_date_obj = datetime.fromisoformat(meeting_data['date'])
            meeting_slug = f"{meeting_date_obj.strftime('%Y-%m-%d')}-{meeting_id}"
            meeting_url = f"{app_url}/{meeting_data['banana']}/{meeting_slug}"

            html += f"""
                    <!-- Meeting: {meeting_data['title']} -->
                    <tr>
                        <td style="padding: 32px 40px; border-bottom: 1px solid #e2e8f0;">
                            <div style="margin-bottom: 16px;">
                                <span style="display: inline-block; padding: 4px 12px; background-color: #f1f5f9; color: #475569; border-radius: 6px; font-size: 12px; font-weight: 600;">
                                    {meeting_data['title'].upper()}
                                </span>
                                <span style="margin-left: 8px; font-size: 13px; color: #64748b; font-family: Georgia, serif;">
                                    {format_date(meeting_data['date'])}
                                </span>
                            </div>
"""

            for item in meeting_data['items']:
                # Build item anchor link
                item_url = f"{meeting_url}#item-{item['item_id']}"
                summary_preview = item['item_summary'][:200] + '...' if item['item_summary'] and len(item['item_summary']) > 200 else item['item_summary'] or ''

                html += f"""
                            <h3 style="margin: 0 0 12px 0; font-size: 18px; font-weight: 600; color: #0f172a; font-family: Georgia, serif;">
                                <a href="{item_url}" style="color: #0f172a; text-decoration: none;">
                                    {item['item_title']}
                                </a>
                            </h3>

                            <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: #475569; font-family: Georgia, serif;">
                                {summary_preview}
                            </p>

                            <p style="margin: 0 0 20px 0; font-size: 13px;">
                                <strong style="color: #4f46e5;">Keywords matched:</strong> {item['keyword']}
                            </p>
"""

            # Add "View full agenda" link if available
            if meeting_data.get('agenda_url'):
                html += f"""
                            <p style="margin: 0; font-size: 14px;">
                                <a href="{meeting_url}" style="color: #4f46e5; text-decoration: none; font-weight: 600;">
                                    View full agenda →
                                </a>
                            </p>
"""

            html += """
                        </td>
                    </tr>
"""
    else:
        html += """
                    <tr>
                        <td style="padding: 32px 40px; border-bottom: 1px solid #e2e8f0;">
                            <p style="color: #64748b; font-size: 14px; font-family: Georgia, serif;">
                                No keyword matches found this week.
                            </p>
                        </td>
                    </tr>
"""

    # Upcoming Meetings Section (if any meetings without matches)
    if upcoming_meetings:
        # Get meeting IDs that already showed in keyword matches
        matched_meeting_ids = set(match['meeting_id'] for match in keyword_matches)

        # Filter to only show meetings that weren't already shown
        unmatched_meetings = [m for m in upcoming_meetings if m['id'] not in matched_meeting_ids]

        if unmatched_meetings:
            html += """
                    <tr>
                        <td style="padding: 32px 40px 16px 40px;">
                            <h2 style="font-size: 16px; font-weight: 600; color: #0f172a; margin: 0; text-transform: uppercase; letter-spacing: 0.05em; font-family: 'IBM Plex Mono', monospace;">
                                Other Upcoming Meetings
                            </h2>
                        </td>
                    </tr>
"""
            for meeting in unmatched_meetings:
                meeting_date_obj = datetime.fromisoformat(meeting['date'])
                meeting_slug = f"{meeting_date_obj.strftime('%Y-%m-%d')}-{meeting['id']}"
                meeting_url = f"{app_url}/{meeting['banana']}/{meeting_slug}"

                html += f"""
                    <tr>
                        <td style="padding: 0 40px 16px 40px;">
                            <p style="margin: 0; font-size: 14px; font-family: Georgia, serif; color: #475569;">
                                {format_date(meeting['date'])} - <a href="{meeting_url}" style="color: #4f46e5; text-decoration: none; font-weight: 600;">{meeting['title']}</a>
                            </p>
                        </td>
                    </tr>
"""

    # Footer
    html += f"""
                    <tr>
                        <td style="padding: 32px 40px; text-align: center;">
                            <p style="margin: 0 0 16px 0; font-size: 13px; color: #64748b; font-family: Georgia, serif;">
                                <a href="{app_url}/dashboard" style="color: #4f46e5; text-decoration: none; font-weight: 600;">View Dashboard</a>
                                <span style="margin: 0 8px; color: #cbd5e1;">•</span>
                                <a href="{app_url}/settings" style="color: #64748b; text-decoration: none;">Manage Digests</a>
                            </p>
                            <p style="margin: 0; font-size: 12px; color: #94a3b8; font-family: Georgia, serif;">
                                Engagic – Statewide Municipal Intelligence
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


def send_weekly_digest():
    """
    Main function: Send weekly digests to all active users.

    Note: This queries "alerts" but they represent weekly digest subscriptions.
    """

    userland_db_path = os.getenv('USERLAND_DB', '/root/engagic/data/userland.db')
    app_url = os.getenv('APP_URL', 'https://engagic.org')

    logger.info("Starting weekly digest process...")

    db = UserlandDB(userland_db_path, silent=True)
    email_service = EmailService()

    # Get all active alerts (weekly digest subscriptions)
    active_alerts = db.get_active_alerts()
    logger.info(f"Found {len(active_alerts)} active alerts")

    sent_count = 0
    error_count = 0

    for alert in active_alerts:
        try:
            # Get user
            user = db.get_user(alert.user_id)
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
            city_name = get_city_name(primary_city)

            # Get keyword matches (uses search_summaries)
            keywords = alert.criteria.get('keywords', [])
            keyword_matches = find_keyword_matches(primary_city, keywords, days_ahead=7)

            # Get upcoming meetings (uses UnifiedDatabase)
            upcoming_meetings = get_upcoming_meetings(primary_city, days_ahead=7)

            # Skip if no content
            if not keyword_matches and not upcoming_meetings:
                logger.info(f"No content for {user.email}, skipping")
                continue

            # Build email
            html = build_digest_email(
                user_name=user.name,
                city_name=city_name,
                city_banana=primary_city,
                keyword_matches=keyword_matches,
                keywords=keywords,
                upcoming_meetings=upcoming_meetings,
                app_url=app_url
            )

            # Send email
            subject = f"This week in {city_name}"
            if keyword_matches:
                subject += f" - {len(keyword_matches)} keyword match{'es' if len(keyword_matches) > 1 else ''}"

            email_service.send_email(
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


if __name__ == "__main__":
    send_weekly_digest()
