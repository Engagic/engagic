#!/usr/bin/env python3
"""
Email Template Test Script

Sends all email types to verify styling and formatting.
Uses actual template system from refactored codebase.

Usage:
    uv run userland/scripts/test_emails.py your@email.com
"""

import os
import sys
import secrets
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from userland.email.transactional import send_magic_link
from userland.email.emailer import EmailService
from userland.scripts.weekly_digest import build_digest_email


def send_test_emails(email: str):
    """
    Send all email types to test address.

    Args:
        email: Recipient email address
    """
    print(f"Sending test emails to: {email}\n")

    # 1. Magic link (signup)
    print("1. Magic Link - Signup")
    signup_token = secrets.token_urlsafe(32)
    result = send_magic_link(
        email=email,
        token=signup_token,
        user_name="Test User",
        is_signup=True
    )
    print(f"   Status: {'Sent' if result else 'Failed'}\n")

    # 2. Magic link (login)
    print("2. Magic Link - Login")
    login_token = secrets.token_urlsafe(32)
    result = send_magic_link(
        email=email,
        token=login_token,
        user_name="Test User",
        is_signup=False
    )
    print(f"   Status: {'Sent' if result else 'Failed'}\n")

    # 3. Weekly digest
    print("3. Weekly Digest")
    send_test_digest(email)

    print("\nAll test emails sent.")
    print(f"Check inbox: {email}")


def send_test_digest(email: str):
    """Send weekly digest with mock data."""

    # Mock data for digest
    city_name = "Palo Alto, CA"
    city_banana = "paloaltoCA"
    app_url = os.getenv("APP_URL", "https://engagic.org")

    # Mock keyword matches
    keyword_matches = [
        {
            'keyword': 'housing',
            'item_id': 1,
            'meeting_id': 101,
            'item_title': 'Affordable Housing Development at 123 Main Street',
            'item_summary': 'Council will review a proposal for a 45-unit affordable housing development.',
            'item_position': '5A',
            'meeting_title': 'City Council Regular Meeting',
            'meeting_date': (datetime.now() + timedelta(days=3)).isoformat(),
            'agenda_url': 'https://example.com/agenda',
            'banana': city_banana,
            'context': 'Council will review a proposal for a 45-unit affordable housing development. The project includes zoning changes to allow increased density and mixed-use development.'
        },
        {
            'keyword': 'zoning',
            'item_id': 2,
            'meeting_id': 102,
            'item_title': 'Residential Zoning Update - Downtown District',
            'item_summary': 'Proposed amendments to the downtown zoning ordinance.',
            'item_position': '3B',
            'meeting_title': 'Planning Commission Meeting',
            'meeting_date': (datetime.now() + timedelta(days=5)).isoformat(),
            'agenda_url': 'https://example.com/agenda2',
            'banana': city_banana,
            'context': 'Proposed amendments to the downtown zoning ordinance would allow for increased residential density and reduced parking requirements.'
        },
        {
            'keyword': 'housing',
            'item_id': 3,
            'meeting_id': 103,
            'item_title': 'Housing Element Annual Progress Report',
            'item_summary': 'Annual report on housing production and RHNA goals.',
            'item_position': '7C',
            'meeting_title': 'City Council Regular Meeting',
            'meeting_date': (datetime.now() + timedelta(days=6)).isoformat(),
            'agenda_url': 'https://example.com/agenda3',
            'banana': city_banana,
            'context': 'Annual report on housing production and progress toward RHNA goals. The city approved 127 units this year, falling short of the 200-unit target.'
        }
    ]

    # Mock upcoming meetings
    upcoming_meetings = [
        {
            'id': 101,
            'banana': city_banana,
            'title': 'City Council Regular Meeting',
            'date': (datetime.now() + timedelta(days=3)).isoformat(),
            'agenda_url': 'https://example.com/agenda',
            'packet_url': None,
            'status': None
        },
        {
            'id': 102,
            'banana': city_banana,
            'title': 'Planning Commission Meeting',
            'date': (datetime.now() + timedelta(days=5)).isoformat(),
            'agenda_url': 'https://example.com/agenda2',
            'packet_url': None,
            'status': None
        }
    ]

    # Build digest HTML using actual template function
    html = build_digest_email(
        user_name="Test User",
        city_name=city_name,
        city_banana=city_banana,
        keyword_matches=keyword_matches,
        keywords=['housing', 'zoning'],
        upcoming_meetings=upcoming_meetings,
        app_url=app_url
    )

    # Send email
    email_service = EmailService()
    subject = f"This week in {city_name} - 3 keyword matches"

    result = email_service.send_email(
        to_email=email,
        subject=subject,
        html_body=html
    )

    print(f"   Status: {'Sent' if result else 'Failed'}")
    print(f"   Matches: 3 items, 2 upcoming meetings\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_email = sys.argv[1]
    else:
        print("Usage: uv run userland/scripts/test_emails.py your@email.com")
        sys.exit(1)

    send_test_emails(test_email)
