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
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from userland.database.db import UserlandDB
from userland.email.emailer import EmailService
from userland.email.templates import DARK_MODE_CSS
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
                        <td style="padding: 32px 40px 24px 40px; background-color: #4f46e5; border-radius: 9px 9px 0 0;">
                            <div style="margin-bottom: 16px;">
                                <span style="font-family: 'IBM Plex Mono', monospace; font-size: 18px; font-weight: 600; color: #ffffff; letter-spacing: -0.02em;">engagic</span>
                            </div>
                            <h1 style="margin: 0 0 8px 0; font-size: 24px; font-weight: 600; color: #ffffff; line-height: 1.3; font-family: 'IBM Plex Mono', monospace;">
                                This week in {city_name}
                            </h1>
                            <p style="margin: 0; font-size: 14px; color: #ffffff; opacity: 0.9; font-family: Georgia, serif;">
                                Your weekly civic digest
                            </p>
                        </td>
                    </tr>
"""

    # Upcoming Meetings Section FIRST (always shown if there are any)
    if upcoming_meetings:
        html += """
                    <tr>
                        <td style="padding: 0 40px 24px 40px;">
                            <h2 style="margin: 0 0 16px 0; font-size: 13px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; font-family: 'IBM Plex Mono', monospace;">
                                Upcoming Meetings This Week
                            </h2>
"""
        for meeting in upcoming_meetings:
            meeting_date_obj = datetime.fromisoformat(meeting['date'])
            meeting_slug = f"{meeting_date_obj.strftime('%Y-%m-%d')}-{meeting['id']}"
            meeting_url = f"{app_url}/{meeting['banana']}/{meeting_slug}"

            html += f"""
                            <div style="margin-bottom: 12px; padding: 16px; background: #f8fafc; border-radius: 6px; border-left: 4px solid #4f46e5;">
                                <p style="margin: 0 0 8px 0; font-size: 15px; font-weight: 600; color: #0f172a; font-family: 'IBM Plex Mono', monospace;">
                                    {format_date(meeting['date'])} - {meeting['title']}
                                </p>
                                <a href="{meeting_url}" style="color: #4f46e5; text-decoration: none; font-size: 14px; font-weight: 600; font-family: 'IBM Plex Mono', monospace;">
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
                        <td style="padding: 0 40px 24px 40px; border-top: 1px solid #e2e8f0;">
                            <h2 style="margin: 24px 0 16px 0; font-size: 13px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; font-family: 'IBM Plex Mono', monospace;">
                                Your Keywords: {', '.join(keywords).upper()}
                            </h2>
"""
        for match in keyword_matches:
            meeting_date_obj = datetime.fromisoformat(match['meeting_date'])
            meeting_slug = f"{meeting_date_obj.strftime('%Y-%m-%d')}-{match['meeting_id']}"
            meeting_url = f"{app_url}/{match['banana']}/{meeting_slug}"
            item_url = f"{meeting_url}#item-{match['item_id']}"

            # Use context field (keyword-highlighted text) instead of summary
            context = match.get('context', match.get('item_summary', ''))
            if len(context) > 300:
                context = context[:297] + "..."

            keyword = match.get('keyword', '')

            html += f"""
                            <div style="margin-bottom: 20px; padding: 24px; background: #f8fafc; border-radius: 6px; border-left: 4px solid #4f46e5;">
                                <p style="margin: 0 0 8px 0; font-size: 16px; font-weight: 600; color: #0f172a; line-height: 1.5; font-family: 'IBM Plex Mono', monospace;">
                                    {match['item_title']}
                                </p>
                                <p style="margin: 0 0 12px 0; font-size: 13px; color: #64748b; font-family: Georgia, serif;">
                                    {match['meeting_title']} • {format_date(match['meeting_date'])}
                                </p>
                                <p style="margin: 0 0 12px 0; font-size: 13px; color: #64748b; font-family: Georgia, serif;">
                                    Matched: <strong style="color: #475569;">"{keyword}"</strong>
                                </p>
                                <p style="margin: 0 0 20px 0; font-size: 14px; color: #475569; line-height: 1.7; font-family: Georgia, serif;">
                                    {context}
                                </p>
                                <a href="{item_url}" style="display: inline-block; padding: 12px 24px; background-color: #4f46e5; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 13px; font-family: 'IBM Plex Mono', monospace;">
                                    View Item
                                </a>
                            </div>
"""
        html += """
                        </td>
                    </tr>
"""

    # Footer
    html += f"""
                    <tr>
                        <td style="padding: 32px 40px; border-top: 1px solid #e2e8f0;">
                            <p style="margin: 0 0 16px 0; font-size: 12px; color: #475569; font-family: Georgia, serif; line-height: 1.7;">
                                You're receiving this because you're watching {city_name}
                            </p>
                            <p style="margin: 0 0 16px 0; font-size: 12px; color: #64748b; font-family: Georgia, serif; line-height: 1.7;">
                                Engagic is free and open-source. If you find it valuable, please <a href="https://engagic.org/donate" style="color: #8B5CF6; text-decoration: none; font-weight: 600;">support the project</a>.
                            </p>
                            <p style="margin: 0 0 8px 0; font-size: 12px; color: #64748b; font-family: Georgia, serif;">
                                Questions? Visit <a href="https://engagic.org" style="color: #4f46e5; text-decoration: none;">engagic.org</a>
                            </p>
                            <p style="margin: 0; font-size: 12px; font-family: Georgia, serif;">
                                <a href="{app_url}/dashboard" style="color: #64748b; text-decoration: underline;">Manage subscription</a>
                                <span style="margin: 0 8px; color: #cbd5e1;">|</span>
                                <a href="{app_url}/unsubscribe" style="color: #64748b; text-decoration: none;">Unsubscribe</a>
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
            keyword_matches = find_keyword_matches(primary_city, keywords, days_ahead=10)

            # Get upcoming meetings (uses UnifiedDatabase)
            upcoming_meetings = get_upcoming_meetings(primary_city, days_ahead=10)

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
