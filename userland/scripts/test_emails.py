#!/usr/bin/env python3
"""
Test script to send sample emails to check styling.

Sends one of each email type to the specified email address.
"""

import sys
import secrets
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from userland.email.transactional import send_magic_link
from userland.email.emailer import EmailService
from userland.database.db import UserlandDB
from userland.settings import USERLAND_DB


def send_test_emails(email: str):
    """
    Send test emails to check styling.

    Args:
        email: Email address to send tests to
    """
    print(f"Sending test emails to: {email}\n")

    # 1. Signup magic link
    print("1. Sending signup magic link...")
    signup_token = secrets.token_urlsafe(32)
    signup_result = send_magic_link(
        email=email,
        token=signup_token,
        user_name="Test User",
        is_signup=True
    )
    print(f"   Result: {'Success' if signup_result else 'Failed'}\n")

    # 2. Login magic link
    print("2. Sending login magic link...")
    login_token = secrets.token_urlsafe(32)
    login_result = send_magic_link(
        email=email,
        token=login_token,
        user_name="Test User",
        is_signup=False
    )
    print(f"   Result: {'Success' if login_result else 'Failed'}\n")

    # 3. Digest email (using actual user data if available, or mock)
    print("3. Sending digest email...")
    try:
        db = UserlandDB(USERLAND_DB)

        # Try to get user from database
        user = db.get_user_by_email(email)

        if user:
            # Get user's alerts
            alerts = db.get_alerts(user_id=user.id)

            if alerts:
                # Get recent matches for first alert
                alert = alerts[0]
                matches = db.get_matches(
                    alert_id=alert.id,
                    limit=5,
                    notified_only=False
                )

                if matches:
                    # Send actual digest with real data
                    email_service = EmailService()
                    digest_result = email_service.send_alert_digest(
                        user=user,
                        alert=alert,
                        matches=matches
                    )
                    print(f"   Sent digest with {len(matches)} real matches")
                    print(f"   Result: {'Success' if digest_result else 'Failed'}\n")
                else:
                    # No matches, send mock digest
                    print("   No matches found, sending mock digest...")
                    send_mock_digest(email)
            else:
                print("   No alerts found, sending mock digest...")
                send_mock_digest(email)
        else:
            print(f"   User not found in database, sending mock digest...")
            send_mock_digest(email)

    except Exception as e:
        print(f"   Error accessing database: {e}")
        print("   Sending mock digest...")
        send_mock_digest(email)

    print("\nAll test emails sent!")
    print(f"Check your inbox at: {email}")


def send_mock_digest(email: str):
    """Send a mock digest email with sample data."""
    email_service = EmailService()

    subject = "Engagic Digest: housing, zoning (3 items)"

    html_body = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Engagic Digest</title>
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
                                Your digest: <strong>housing, zoning</strong><br>
                                Found <strong>3 items</strong> in Palo Alto, CA
                            </p>
                        </td>
                    </tr>

                    <!-- Match 1 -->
                    <tr>
                        <td style="padding: 32px 40px; border-bottom: 1px solid #e2e8f0;">
                            <div style="margin-bottom: 16px;">
                                <span style="display: inline-block; padding: 4px 12px; background-color: #f1f5f9; color: #475569; border-radius: 6px; font-size: 12px; font-weight: 600;">
                                    CITY COUNCIL
                                </span>
                                <span style="margin-left: 8px; font-size: 13px; color: #64748b; font-family: Georgia, serif;">
                                    Dec 4, 2025
                                </span>
                            </div>

                            <h3 style="margin: 0 0 12px 0; font-size: 18px; font-weight: 600; color: #0f172a; font-family: Georgia, serif;">
                                Affordable Housing Development at 123 Main Street
                            </h3>

                            <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: #475569; font-family: Georgia, serif;">
                                Council will review a proposal for a 45-unit affordable housing development. The project includes <mark style="background-color: #fef08a;">zoning</mark> changes to allow increased density and mixed-use development. Staff recommends approval with conditions related to parking and community benefits.
                            </p>

                            <p style="margin: 0; font-size: 13px;">
                                <strong style="color: #4f46e5;">Keywords matched:</strong> housing, zoning
                            </p>
                        </td>
                    </tr>

                    <!-- Match 2 -->
                    <tr>
                        <td style="padding: 32px 40px; border-bottom: 1px solid #e2e8f0;">
                            <div style="margin-bottom: 16px;">
                                <span style="display: inline-block; padding: 4px 12px; background-color: #f1f5f9; color: #475569; border-radius: 6px; font-size: 12px; font-weight: 600;">
                                    PLANNING COMMISSION
                                </span>
                                <span style="margin-left: 8px; font-size: 13px; color: #64748b; font-family: Georgia, serif;">
                                    Dec 3, 2025
                                </span>
                            </div>

                            <h3 style="margin: 0 0 12px 0; font-size: 18px; font-weight: 600; color: #0f172a; font-family: Georgia, serif;">
                                Residential Zoning Update - Downtown District
                            </h3>
                            <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: #475569; font-family: Georgia, serif;">
                                Proposed amendments to the downtown <mark style="background-color: #fef08a;">zoning</mark> ordinance would allow for increased residential density and reduced parking requirements. Changes align with state <mark style="background-color: #fef08a;">housing</mark> mandates and the city's RHNA obligations.
                            </p>

                            <p style="margin: 0; font-size: 13px;">
                                <strong style="color: #4f46e5;">Keywords matched:</strong> housing, zoning
                            </p>
                        </td>
                    </tr>

                    <!-- Match 3 -->
                    <tr>
                        <td style="padding: 32px 40px; border-bottom: 1px solid #e2e8f0;">
                            <div style="margin-bottom: 16px;">
                                <span style="display: inline-block; padding: 4px 12px; background-color: #f1f5f9; color: #475569; border-radius: 6px; font-size: 12px; font-weight: 600;">
                                    CITY COUNCIL
                                </span>
                                <span style="margin-left: 8px; font-size: 13px; color: #64748b; font-family: Georgia, serif;">
                                    Dec 1, 2025
                                </span>
                            </div>

                            <h3 style="margin: 0 0 12px 0; font-size: 18px; font-weight: 600; color: #0f172a; font-family: Georgia, serif;">
                                Housing Element Annual Progress Report
                            </h3>

                            <p style="margin: 0 0 16px 0; font-size: 14px; line-height: 1.6; color: #475569; font-family: Georgia, serif;">
                                Annual report on <mark style="background-color: #fef08a;">housing</mark> production and progress toward RHNA goals. The city approved 127 units this year, falling short of the 200-unit target. Staff proposes streamlined permitting and <mark style="background-color: #fef08a;">zoning</mark> reforms to accelerate production.
                            </p>

                            <p style="margin: 0; font-size: 13px;">
                                <strong style="color: #4f46e5;">Keywords matched:</strong> housing, zoning
                            </p>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 32px 40px; text-align: center;">
                            <p style="margin: 0 0 16px 0; font-size: 13px; color: #64748b; font-family: Georgia, serif;">
                                <a href="https://engagic.org/dashboard" style="color: #4f46e5; text-decoration: none; font-weight: 600;">View Dashboard</a>
                                <span style="margin: 0 8px; color: #cbd5e1;">•</span>
                                <a href="https://engagic.org/settings" style="color: #64748b; text-decoration: none;">Manage Digests</a>
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

    result = email_service.send_email(email, subject, html_body)
    print(f"   Result: {'Success' if result else 'Failed'}\n")


if __name__ == "__main__":
    # Get email from command line or use default
    if len(sys.argv) > 1:
        test_email = sys.argv[1]
    else:
        # Default to the existing user in the database
        test_email = "ibansadowski12@gmail.com"

    send_test_emails(test_email)
