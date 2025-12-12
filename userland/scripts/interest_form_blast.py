"""
Interest Form Response Email Script

Sends personalized announcement emails to summer interest form respondents,
announcing that weekly digests are now live.

Usage:
    # Preview (dry-run)
    uv run python -m userland.scripts.interest_form_blast /path/to/respondents.csv

    # Actually send
    uv run python -m userland.scripts.interest_form_blast /path/to/respondents.csv --send
"""

import asyncio
import csv
import sys
from pathlib import Path

from userland.email.emailer import EmailService


def extract_first_name(full_name: str) -> str:
    """Extract first name from 'First Last' or just 'First'."""
    return full_name.strip().split()[0] if full_name.strip() else "there"


def build_announcement_email(first_name: str) -> str:
    """Build a clean, readable HTML email."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="color-scheme" content="light dark">
    <title>Engagic</title>
    <style>
        @media (prefers-color-scheme: dark) {{
            body {{ background-color: #1a1a1a !important; }}
            .container {{ background-color: #262626 !important; }}
            .text {{ color: #e5e5e5 !important; }}
            .subtext {{ color: #a3a3a3 !important; }}
            a {{ color: #818cf8 !important; }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: system-ui, -apple-system, sans-serif;">
    <table role="presentation" width="100%" style="background-color: #f5f5f5;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" class="container" width="560" style="max-width: 560px; background-color: #ffffff; border-radius: 8px;">
                    <tr>
                        <td style="padding: 40px;">
                            <p class="text" style="margin: 0 0 24px 0; font-size: 16px; line-height: 1.6; color: #171717;">
                                Hello {first_name},
                            </p>
                            <p class="text" style="margin: 0 0 16px 0; font-size: 16px; line-height: 1.6; color: #171717;">
                                You believed in Engagic before it was public. Now we're live and ready to welcome you.
                            </p>
                            <p class="text" style="margin: 0 0 16px 0; font-size: 16px; line-height: 1.6; color: #171717;">
                                We've made incredible progress since our presentation this summer. Find summaries and participation info. Stay informed and make your voice heard!
                            </p>
                            <p class="text" style="margin: 0 0 16px 0; font-size: 16px; line-height: 1.6; color: #171717;">
                                Your most requested feature, weekly digests, are now live! <a href="https://engagic.org/signup" style="color: #4f46e5;">Sign up for an account here</a>, and then add your city. You'll receive one every Sunday.
                            </p>
                            <p class="text" style="margin: 0 0 16px 0; font-size: 16px; line-height: 1.6; color: #171717;">
                                If you know anyone who needs to see this, share this and send them our way. We're actively looking for contributors and partners.
                            </p>
                            <p class="text" style="margin: 0 0 24px 0; font-size: 16px; line-height: 1.6; color: #171717;">
                                Thank you for your interest in Engagic and continued support.
                            </p>
                            <p class="text" style="margin: 0 0 8px 0; font-size: 16px; line-height: 1.6; color: #171717;">
                                Best Wishes,
                            </p>
                            <p class="text" style="margin: 0 0 24px 0; font-size: 16px; line-height: 1.6; color: #171717;">
                                Iban
                            </p>
                            <p style="margin: 0 0 32px 0;">
                                <a href="https://engagic.org" style="color: #4f46e5; font-size: 16px;">engagic.org</a>
                            </p>
                            <p style="margin: 0; text-align: center;">
                                <img src="https://engagic.org/icon-192.png" alt="" width="32" height="32" style="opacity: 0.6; border-radius: 6px;">
                            </p>
                        </td>
                    </tr>
                </table>
                <p style="margin: 24px 0 0 0; font-size: 12px; color: #737373; text-align: center;">
                    You're receiving this because you signed up for the Engagic interest form.<br>
                    This is a one-time announcement.
                </p>
            </td>
        </tr>
    </table>
</body>
</html>"""


def build_plain_text(first_name: str) -> str:
    """Plain text version of the email."""
    return f"""Hello {first_name},

You believed in Engagic before it was public. Now we're live and ready to welcome you.

We've made incredible progress since our presentation this summer. Find summaries and participation info. Stay informed and make your voice heard!

Your most requested feature, weekly digests, are now live! Sign up for an account here: https://engagic.org/signup, and then add your city. You'll receive one every Sunday.

If you know anyone who needs to see this, share this and send them our way. We're actively looking for contributors and partners.

Thank you for your interest in Engagic and continued support.

Best Wishes,
Iban

engagic.org

---
You're receiving this because you signed up for the Engagic interest form.
This is a one-time announcement."""


def load_respondents(csv_path: Path) -> list[dict]:
    """Load respondents from CSV file."""
    respondents = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Handle both formats: 'name'/'email' or interest form columns
            name = row.get('Name', row.get('name', '')).strip()
            email = row.get('Email (to send you updates)', row.get('email', '')).strip()
            if email:  # Email is required
                respondents.append({
                    'name': name,
                    'email': email,
                    'first_name': extract_first_name(name)
                })
    return respondents


async def send_emails(respondents: list[dict], dry_run: bool = True) -> tuple[int, int]:
    """Send emails to all respondents. Returns (success_count, failure_count)."""
    if dry_run:
        print("\n=== DRY RUN MODE ===")
        print("No emails will be sent. Use --send to actually send.\n")

        for r in respondents:
            print(f"Would send to: {r['first_name']} <{r['email']}>")

        print(f"\nTotal: {len(respondents)} emails would be sent")
        print("\nPreview of email body:")
        print("-" * 60)
        sample = respondents[0] if respondents else {'first_name': 'Friend'}
        print(f"To: {sample.get('email', 'sample@example.com')}")
        print("From: Engagic <hello@engagic.org>")
        print("Subject: Engagic Augmentation Lab Interest Form Response")
        print("-" * 60)
        print(build_plain_text(sample['first_name']))
        print("-" * 60)
        return (len(respondents), 0)

    # Actually send
    print("\n=== SENDING EMAILS ===\n")
    service = EmailService()
    success = 0
    failed = 0

    for r in respondents:
        html = build_announcement_email(r['first_name'])
        text = build_plain_text(r['first_name'])
        result = await service.send_email(
            to_email=r['email'],
            subject="Engagic Augmentation Lab Interest Form Response",
            html_body=html,
            text_body=text,
            from_address="Engagic <hello@engagic.org>"
        )
        if result:
            print(f"Sent: {r['first_name']} <{r['email']}>")
            success += 1
        else:
            print(f"FAILED: {r['first_name']} <{r['email']}>")
            failed += 1

    print(f"\nDone: {success} sent, {failed} failed")
    return (success, failed)


async def send_test_email(test_email: str) -> bool:
    """Send a single test email."""
    print(f"\n=== SENDING TEST EMAIL to {test_email} ===\n")
    service = EmailService()
    html = build_announcement_email("Friend")
    text = build_plain_text("Friend")
    result = await service.send_email(
        to_email=test_email,
        subject="Engagic Augmentation Lab Interest Form Response",
        html_body=html,
        text_body=text,
        from_address="Engagic <hello@engagic.org>"
    )
    if result:
        print(f"Test email sent to {test_email}")
    else:
        print(f"FAILED to send test email to {test_email}")
    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python -m userland.scripts.interest_form_blast <csv_path> [options]")
        print()
        print("CSV format: Name,Email (to send you updates)")
        print()
        print("Options:")
        print("  --send              Actually send emails (default is dry-run)")
        print("  --test <email>      Send a single test email to this address")
        sys.exit(1)

    # Check for test mode first
    if "--test" in sys.argv:
        test_idx = sys.argv.index("--test")
        if test_idx + 1 >= len(sys.argv):
            print("Error: --test requires an email address")
            sys.exit(1)
        test_email = sys.argv[test_idx + 1]
        asyncio.run(send_test_email(test_email))
        return

    csv_path = Path(sys.argv[1])
    dry_run = "--send" not in sys.argv

    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    respondents = load_respondents(csv_path)

    if not respondents:
        print("Error: No valid respondents found in CSV")
        sys.exit(1)

    print(f"Loaded {len(respondents)} respondents from {csv_path}")

    asyncio.run(send_emails(respondents, dry_run=dry_run))


if __name__ == "__main__":
    main()
