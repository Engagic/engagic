"""
Weekly Digest Script

Runs every Sunday at 9am. Sends users a digest of:
1. Upcoming meetings this week (all meetings for their city)
2. Keyword matches (items mentioning their keywords)

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
from database.db import UnifiedDatabase
from database.search_utils import search_summaries
from config import config

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("engagic.weekly_digest")


def get_upcoming_meetings(city_banana: str, days_ahead: int = 7) -> List[Dict[str, Any]]:
    """
    Get upcoming meetings for a city in the next N days.

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

        # Convert Meeting objects to dicts with necessary fields
        result = []
        for meeting in meetings:
            result.append({
                'id': meeting.id,
                'banana': meeting.banana,
                'title': meeting.title,
                'date': meeting.date.isoformat() if meeting.date else None,
                'agenda_url': meeting.agenda_url,
                'packet_url': meeting.packet_url
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

    Uses search_summaries() from database layer + date post-filter.
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

        # Post-filter by date range (search_summaries doesn't support date filtering)
        for match in matches:
            if match.get('type') == 'item' and match.get('date'):
                try:
                    match_date = datetime.fromisoformat(match['date']).date()
                    if today <= match_date <= end_date:
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
                            'banana': match['banana']
                        })
                except (ValueError, TypeError):
                    continue

    return all_matches


def build_digest_email(
    user_name: str,
    city_name: str,
    upcoming_meetings: List[Dict[str, Any]],
    keyword_matches: List[Dict[str, Any]],
    app_url: str
) -> str:
    """Build HTML email for weekly digest"""

    # Format meeting dates
    def format_date(date_str: str) -> str:
        date_obj = datetime.fromisoformat(date_str)
        return date_obj.strftime("%a, %b %d")

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        @media (prefers-color-scheme: dark) {{
            /* Override backgrounds */
            body {{ background: #1a1a1a !important; }}
            div[style*="background: white"],
            div[style*="background: #f8fafc"] {{ background: #1e293b !important; }}
            div[style*="background: #f3e8ff"] {{ background: #1e1b4b !important; }}

            /* Override text colors */
            h1[style*="color: #0f172a"],
            h2[style*="color: #0f172a"],
            div[style*="color: #0f172a"],
            span[style*="color: #0f172a"] {{ color: #e2e8f0 !important; }}

            p[style*="color: #64748b"],
            span[style*="color: #64748b"] {{ color: #94a3b8 !important; }}

            p[style*="color: #475569"] {{ color: #cbd5e1 !important; }}

            /* Override borders */
            div[style*="border: 2px solid #e2e8f0"],
            div[style*="border-bottom: 2px solid #e2e8f0"] {{ border-color: #334155 !important; }}

            div[style*="border-left: 4px solid #4f46e5"] {{ border-color: #4f46e5 !important; }}
            div[style*="border-left: 4px solid #8B5CF6"] {{ border-color: #8B5CF6 !important; }}

            /* Keep links visible */
            a[style*="color: #4f46e5"],
            a[style*="color: #8B5CF6"] {{ color: #a78bfa !important; }}
            span[style*="color: #4f46e5"] {{ color: #818cf8 !important; }}
        }}
    </style>
</head>
<body style="font-family: 'IBM Plex Mono', 'Menlo', 'Monaco', 'Courier New', monospace; max-width: 600px; margin: 0 auto; padding: 20px; background: #f8fafc;">
    <div style="background: white; border-radius: 11px; padding: 32px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 2px solid #e2e8f0;">
        <div style="margin-bottom: 24px;">
            <span style="font-family: 'IBM Plex Mono', monospace; font-size: 18px; font-weight: 600; color: #4f46e5; letter-spacing: -0.02em;">engagic</span>
        </div>
        <h1 style="font-size: 24px; font-weight: 600; color: #0f172a; margin: 0 0 12px 0; font-family: 'IBM Plex Mono', monospace;">
            This week in {city_name}
        </h1>
        <p style="color: #64748b; margin: 0 0 32px 0; font-size: 14px; font-family: Georgia, serif; line-height: 1.7;">
            Your weekly civic update from engagic
        </p>
"""

    # Upcoming meetings section
    if upcoming_meetings:
        html += """
        <div style="margin-bottom: 40px;">
            <h2 style="font-size: 16px; font-weight: 600; color: #0f172a; margin: 0 0 16px 0; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; font-family: 'IBM Plex Mono', monospace;">
                Upcoming Meetings This Week
            </h2>
"""
        for meeting in upcoming_meetings:
            # Build meeting slug: YYYY-MM-DD-meeting_id
            meeting_date_obj = datetime.fromisoformat(meeting['date'])
            meeting_slug = f"{meeting_date_obj.strftime('%Y-%m-%d')}-{meeting['id']}"
            meeting_url = f"{app_url}/{meeting['banana']}/{meeting_slug}"

            html += f"""
            <div style="margin-bottom: 16px; padding: 20px; background: #f8fafc; border-radius: 6px; border-left: 4px solid #4f46e5;">
                <div style="font-weight: 600; color: #0f172a; margin-bottom: 8px; font-family: 'IBM Plex Mono', monospace; line-height: 1.5;">
                    {format_date(meeting['date'])} - {meeting['title']}
                </div>
                <a href="{meeting_url}" style="color: #4f46e5; text-decoration: none; font-size: 14px; font-weight: 600; font-family: 'IBM Plex Mono', monospace;">
                    View agenda →
                </a>
            </div>
"""
        html += """
        </div>
"""
    else:
        html += """
        <div style="margin-bottom: 40px;">
            <h2 style="font-size: 16px; font-weight: 600; color: #0f172a; margin: 0 0 16px 0; font-family: 'IBM Plex Mono', monospace;">
                Upcoming Meetings This Week
            </h2>
            <p style="color: #64748b; font-size: 14px; font-family: Georgia, serif; line-height: 1.7;">No meetings scheduled for this week.</p>
        </div>
"""

    # Keyword matches section
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
                    'items': []
                }
            meetings_map[mid]['items'].append(match)

        html += """
        <div style="margin-bottom: 32px;">
            <h2 style="font-size: 16px; font-weight: 600; color: #0f172a; margin: 0 0 16px 0; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; font-family: 'IBM Plex Mono', monospace;">
                Your Keywords Mentioned
            </h2>
"""
        for meeting_id, meeting_data in meetings_map.items():
            # Build meeting slug: YYYY-MM-DD-meeting_id
            meeting_date_obj = datetime.fromisoformat(meeting_data['date'])
            meeting_slug = f"{meeting_date_obj.strftime('%Y-%m-%d')}-{meeting_id}"
            meeting_url = f"{app_url}/{meeting_data['banana']}/{meeting_slug}"

            html += f"""
            <div style="margin-bottom: 24px; padding: 20px; background: #f3e8ff; border-radius: 6px; border-left: 4px solid #8B5CF6;">
                <div style="font-weight: 600; color: #0f172a; margin-bottom: 16px; font-family: 'IBM Plex Mono', monospace; line-height: 1.5;">
                    {meeting_data['title']} ({format_date(meeting_data['date'])})
                </div>
"""
            for item in meeting_data['items']:
                # Build item anchor: #item-{item_id}
                item_url = f"{meeting_url}#item-{item['item_id']}"
                summary_preview = item['item_summary'][:150] + '...' if item['item_summary'] and len(item['item_summary']) > 150 else item['item_summary'] or ''

                html += f"""
                <div style="margin-bottom: 16px; padding-left: 12px;">
                    <div style="margin-bottom: 8px;">
                        <span style="background: #8B5CF6; color: white; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; font-family: 'IBM Plex Mono', monospace;">
                            {item['keyword']}
                        </span>
                        <a href="{item_url}" style="color: #0f172a; font-weight: 500; margin-left: 8px; font-family: Georgia, serif; text-decoration: none;">
                            Item {item['item_position']}: {item['item_title']}
                        </a>
                    </div>
                    {f'<p style="color: #475569; font-size: 13px; margin: 4px 0 0 0; line-height: 1.7; font-family: Georgia, serif;">{summary_preview}</p>' if summary_preview else ''}
                </div>
"""
            html += f"""
                <a href="{meeting_url}" style="color: #8B5CF6; text-decoration: none; font-size: 14px; font-weight: 600; font-family: 'IBM Plex Mono', monospace;">
                    View full meeting →
                </a>
            </div>
"""
        html += """
        </div>
"""

    # Footer
    html += f"""
        <div style="margin-top: 40px; padding-top: 24px; border-top: 1px solid #e2e8f0; text-align: center;">
            <p style="color: #64748b; font-size: 12px; margin: 0 0 12px 0; font-family: Georgia, serif; line-height: 1.7;">
                You're receiving this because you're watching {city_name}
            </p>
            <p style="color: #64748b; font-size: 12px; margin: 0; font-family: Georgia, serif;">
                <a href="{app_url}/dashboard" style="color: #4f46e5; text-decoration: none; font-weight: 600;">Manage subscription</a> |
                <a href="{app_url}/unsubscribe" style="color: #64748b; text-decoration: none;">Unsubscribe</a>
            </p>
        </div>
    </div>
</body>
</html>
"""

    return html


def send_weekly_digest():
    """Main function: Send weekly digests to all active users"""

    userland_db_path = os.getenv('USERLAND_DB', '/root/engagic/data/userland.db')
    app_url = os.getenv('APP_URL', 'https://engagic.org')

    logger.info("Starting weekly digest process...")

    db = UserlandDB(userland_db_path, silent=True)
    email_service = EmailService()

    # Get all active alerts
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

            # Get upcoming meetings (uses UnifiedDatabase)
            upcoming_meetings = get_upcoming_meetings(primary_city, days_ahead=7)

            # Get keyword matches (uses search_summaries)
            keywords = alert.criteria.get('keywords', [])
            keyword_matches = find_keyword_matches(primary_city, keywords, days_ahead=7)

            # Skip if no content
            if not upcoming_meetings and not keyword_matches:
                logger.info(f"No content for {user.email}, skipping")
                continue

            # Build email
            city_name = primary_city  # TODO: Get actual city name from engagic.db
            html = build_digest_email(
                user_name=user.name,
                city_name=city_name,
                upcoming_meetings=upcoming_meetings,
                keyword_matches=keyword_matches,
                app_url=app_url
            )

            # Send email
            subject = f"This week in {city_name}"
            if keyword_matches:
                subject += f" - {len(keyword_matches)} keyword matches"

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
