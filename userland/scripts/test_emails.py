#!/usr/bin/env python3
"""
Email Integration Test Script

FULL END-TO-END TESTING with REAL database data.
Sends all email types to verify styling, formatting, and data flow.

Pulls real meetings and keyword matches from production database.

Usage:
    uv run userland/scripts/test_emails.py your@email.com
    ./deploy.sh test-emails
"""

import os
import sys
import secrets
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from userland.email.transactional import send_magic_link
from userland.email.emailer import EmailService
from userland.scripts.weekly_digest import (
    build_digest_email,
    get_city_name,
    get_upcoming_meetings,
    find_keyword_matches
)


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
    """Send weekly digest with REAL data from database."""

    # Use actual city with real data
    city_banana = "paloaltoCA"
    app_url = os.getenv("APP_URL", "https://engagic.org")

    # Get REAL data from database
    city_name = get_city_name(city_banana)

    # Get REAL upcoming meetings (next 10 days)
    upcoming_meetings = get_upcoming_meetings(city_banana, days_ahead=10)

    # Get REAL keyword matches (next 10 days)
    keywords = ['housing', 'zoning', 'transit', 'development']
    keyword_matches = find_keyword_matches(city_banana, keywords, days_ahead=10)

    # Build digest HTML using actual template function with REAL data
    html = build_digest_email(
        user_name="Test User",
        city_name=city_name,
        city_banana=city_banana,
        keyword_matches=keyword_matches,
        keywords=keywords,
        upcoming_meetings=upcoming_meetings,
        app_url=app_url
    )

    # Send email
    email_service = EmailService()
    match_count = len(keyword_matches)
    meeting_count = len(upcoming_meetings)

    subject = f"This week in {city_name}"
    if match_count > 0:
        subject += f" - {match_count} keyword match{'es' if match_count != 1 else ''}"

    result = email_service.send_email(
        to_email=email,
        subject=subject,
        html_body=html
    )

    print(f"   Status: {'Sent' if result else 'Failed'}")
    print(f"   Real data: {match_count} keyword matches, {meeting_count} upcoming meetings\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_email = sys.argv[1]
    else:
        print("Usage: uv run userland/scripts/test_emails.py your@email.com")
        sys.exit(1)

    send_test_emails(test_email)
