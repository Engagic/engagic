"""
Email delivery service for userland alert notifications.

Uses Mailgun for reliable email delivery. Adapted from motioncount for free tier.
"""

import logging
import os
from datetime import datetime
from typing import List, Dict, Optional
import requests

from userland.database.db import UserlandDB
from userland.database.models import User, Alert, AlertMatch

logger = logging.getLogger("engagic")


class EmailService:
    """Send alert notifications via Mailgun"""

    def __init__(self, api_key: Optional[str] = None, domain: Optional[str] = None):
        api_key_value = api_key or os.getenv("MAILGUN_API_KEY")
        if not api_key_value:
            raise ValueError("MAILGUN_API_KEY not configured")
        self.api_key: str = api_key_value

        domain_value = domain or os.getenv("MAILGUN_DOMAIN")
        if not domain_value:
            raise ValueError("MAILGUN_DOMAIN not configured")
        self.domain: str = domain_value

        self.from_email = os.getenv("MAILGUN_FROM_EMAIL", f"alerts@{self.domain}")
        self.api_url = f"https://api.mailgun.net/v3/{self.domain}/messages"

    def send_alert_digest(
        self,
        user: User,
        alert: Alert,
        matches: List[AlertMatch]
    ) -> bool:
        """
        Send digest email for an alert.

        Args:
            user: User to notify
            alert: Alert configuration
            matches: List of new matches

        Returns:
            True if sent successfully
        """
        if not user.email:
            logger.warning(f"User {user.name} has no email, skipping")
            return False

        if not matches:
            logger.debug(f"No matches for alert {alert.name}, skipping email")
            return False

        subject = self._build_subject(alert, matches)
        html_content = self._build_html_content(alert, matches)

        try:
            response = requests.post(
                self.api_url,
                auth=("api", self.api_key),
                data={
                    "from": self.from_email,
                    "to": user.email,
                    "subject": subject,
                    "html": html_content
                }
            )

            logger.info(
                f"Sent alert email to {user.email}: "
                f"{alert.name} ({len(matches)} matches), "
                f"status={response.status_code}"
            )
            return response.status_code == 200

        except Exception as e:
            logger.error(f"Failed to send email to {user.email}: {e}")
            return False

    def send_email(self, to_email: str, subject: str, html_body: str) -> bool:
        """
        Send a generic HTML email via Mailgun.

        Args:
            to_email: Recipient email address
            subject: Email subject line
            html_body: HTML content for email body

        Returns:
            True if sent successfully
        """
        try:
            response = requests.post(
                self.api_url,
                auth=("api", self.api_key),
                data={
                    "from": self.from_email,
                    "to": to_email,
                    "subject": subject,
                    "html": html_body
                }
            )
            response.raise_for_status()

            logger.info(
                f"Sent email to {to_email}: {subject}, status={response.status_code}"
            )
            return response.status_code == 200

        except requests.RequestException as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    def _build_subject(self, alert: Alert, matches: List[AlertMatch]) -> str:
        """Build email subject line (matter-aware)"""
        # Check if these are matter matches or string matches
        first_match = matches[0]
        is_matter_match = first_match.match_type == "matter"

        if is_matter_match:
            # Matter match: Show matter info
            criteria = first_match.matched_criteria
            city = criteria.get("city", "Unknown").split(",")[0]
            matter_file = criteria.get("matter_file", "")
            matter_count = len(matches)

            if matter_count == 1:
                return f"{alert.name}: {matter_file} - {city}"
            else:
                return f"{alert.name}: {matter_count} matters in {city}"
        else:
            # String match: Show meeting info
            criteria = first_match.matched_criteria
            city = criteria.get("city", "Unknown").split(",")[0]
            meeting_title = criteria.get("meeting_title", "Meeting")
            item_count = len([m for m in matches if m.item_id])

            if item_count == 0:
                return f"{alert.name}: {city} - {meeting_title[:50]}"
            elif item_count == 1:
                return f"{alert.name}: 1 item in {city} - {meeting_title[:40]}"
            else:
                return f"{alert.name}: {item_count} items in {city} - {meeting_title[:40]}"

    def _build_html_content(self, alert: Alert, matches: List[AlertMatch]) -> str:
        """
        Build HTML email content (matter-aware).

        Detects match type and renders appropriate template:
        - Matter matches: Show timeline, sponsors, canonical summary
        - String matches: Show meeting/item context
        """
        # Check if these are matter matches or string matches
        first_match = matches[0]
        is_matter_match = first_match.match_type == "matter"

        if is_matter_match:
            return self._build_matter_email(alert, matches)
        else:
            return self._build_string_email(alert, matches)

    def _build_string_email(self, alert: Alert, matches: List[AlertMatch]) -> str:
        """Build HTML email for string matches (item-level behavior)"""
        # Get meeting info from first match
        first_match = matches[0]
        criteria = first_match.matched_criteria
        city = criteria.get("city", "Unknown")
        meeting_title = criteria.get("meeting_title", "Meeting")
        date = criteria.get("date", "")

        # Format date
        try:
            dt = datetime.fromisoformat(date)
            date_str = dt.strftime("%B %d, %Y")
        except (ValueError, TypeError):
            date_str = date

        # Count items
        item_count = len([m for m in matches if m.item_id])
        item_word = "item" if item_count == 1 else "items"

        # Build HTML
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>Engagic Alert: {meeting_title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'IBM Plex Mono', 'Menlo', 'Monaco', 'Courier New', monospace;">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f8fafc;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width: 600px; background-color: #ffffff; border: 2px solid #e2e8f0; border-radius: 11px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <!-- Header with Logo -->
                    <tr>
                        <td style="padding: 32px 40px 24px 40px; background-color: #4f46e5; border-radius: 9px 9px 0 0;">
                            <div style="margin-bottom: 16px;">
                                <span style="font-family: 'IBM Plex Mono', monospace; font-size: 18px; font-weight: 600; color: #ffffff; letter-spacing: -0.02em;">engagic</span>
                            </div>
                            <h1 style="margin: 0 0 12px 0; font-size: 24px; font-weight: 600; color: #ffffff; line-height: 1.3; font-family: 'IBM Plex Mono', monospace;">
                                {meeting_title}
                            </h1>
                            <p style="margin: 0 0 8px 0; font-size: 15px; color: #ffffff; opacity: 0.95; font-family: Georgia, serif;">
                                {city} • {date_str}
                            </p>
                            <p style="margin: 0; font-size: 12px; color: #ffffff; opacity: 0.85; font-family: Georgia, serif;">
                                Official Source
                            </p>
                        </td>
                    </tr>

                    <!-- Alert Name -->
                    <tr>
                        <td style="padding: 24px 40px 16px 40px;">
                            <p style="margin: 0; font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; font-family: 'IBM Plex Mono', monospace;">
                                Alert: {alert.name}
                            </p>
                            <p style="margin: 8px 0 0 0; font-size: 15px; color: #475569; font-family: Georgia, serif; line-height: 1.7;">
                                Matched <strong>{item_count} {item_word}</strong> in this meeting
                            </p>
                        </td>
                    </tr>
        """

        # Add each matching item
        for i, match in enumerate(matches):
            criteria = match.matched_criteria
            keyword = criteria.get("keyword", "")
            item_title = criteria.get("item_title")
            context = criteria.get("context", "")
            url = criteria.get("url", "")

            # Truncate context if too long
            if len(context) > 300:
                context = context[:300] + "..."

            if item_title:
                # Item-level match
                html += f"""
                    <!-- Item {i+1} -->
                    <tr>
                        <td style="padding: 0 40px 24px 40px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="border-left: 4px solid #4f46e5; background-color: #f8fafc; border-radius: 6px;">
                                <tr>
                                    <td style="padding: 24px;">
                                        <p style="margin: 0 0 12px 0; font-size: 16px; font-weight: 600; color: #0f172a; line-height: 1.5; font-family: 'IBM Plex Mono', monospace;">
                                            {item_title}
                                        </p>
                                        <p style="margin: 0 0 16px 0; font-size: 13px; color: #64748b; font-family: Georgia, serif;">
                                            Matched: <strong style="color: #475569;">"{keyword}"</strong>
                                        </p>
                                        <p style="margin: 0 0 20px 0; font-size: 14px; color: #475569; line-height: 1.7; font-family: Georgia, serif;">
                                            {context}
                                        </p>
                                        <a href="{url}" style="display: inline-block; padding: 12px 24px; background-color: #4f46e5; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 13px; font-family: 'IBM Plex Mono', monospace;">
                                            View Official Item
                                        </a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                """
            else:
                # Meeting-level match
                html += f"""
                    <!-- Meeting Match {i+1} -->
                    <tr>
                        <td style="padding: 0 40px 24px 40px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="border-left: 4px solid #4f46e5; background-color: #f8fafc; border-radius: 6px;">
                                <tr>
                                    <td style="padding: 24px;">
                                        <p style="margin: 0 0 16px 0; font-size: 13px; color: #64748b; font-family: Georgia, serif;">
                                            Matched: <strong style="color: #475569;">"{keyword}"</strong>
                                        </p>
                                        <p style="margin: 0 0 20px 0; font-size: 14px; color: #475569; line-height: 1.7; font-family: Georgia, serif;">
                                            {context}
                                        </p>
                                        <a href="{url}" style="display: inline-block; padding: 12px 24px; background-color: #4f46e5; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 13px; font-family: 'IBM Plex Mono', monospace;">
                                            View Official Meeting
                                        </a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                """

        # Footer
        html += f"""
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 32px 40px; border-top: 1px solid #e2e8f0;">
                            <p style="margin: 0 0 16px 0; font-size: 12px; color: #475569; font-family: Georgia, serif; line-height: 1.7;">
                                You're receiving this because you subscribed to <strong>{alert.name}</strong> alerts.
                            </p>
                            <p style="margin: 0 0 16px 0; font-size: 12px; color: #64748b; font-family: Georgia, serif; line-height: 1.7;">
                                Engagic is free and open-source. If you find it valuable, please <a href="https://engagic.org/donate" style="color: #8B5CF6; text-decoration: none; font-weight: 600;">support the project</a>.
                            </p>
                            <p style="margin: 0 0 8px 0; font-size: 12px; color: #64748b; font-family: Georgia, serif;">
                                Questions? Visit <a href="https://engagic.org" style="color: #4f46e5; text-decoration: none;">engagic.org</a>
                            </p>
                            <p style="margin: 0; font-size: 12px; font-family: Georgia, serif;">
                                <a href="https://engagic.org/dashboard" style="color: #64748b; text-decoration: underline;">Manage your digests</a>
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

    def _build_matter_email(self, alert: Alert, matches: List[AlertMatch]) -> str:
        """Build HTML email for matter matches (legislative tracking with timeline)"""
        # Get matter info from first match
        first_match = matches[0]
        criteria = first_match.matched_criteria
        city = criteria.get("city", "Unknown")
        matter_file = criteria.get("matter_file", "")
        matter_type = criteria.get("matter_type", "Matter")
        title = criteria.get("title", "")
        appearance_count = criteria.get("appearance_count", 1)
        sponsors = criteria.get("sponsors", [])
        timeline = criteria.get("timeline", [])
        canonical_summary = criteria.get("canonical_summary", "")
        keyword = criteria.get("keyword", "")

        # Build sponsor list
        sponsor_str = ", ".join(sponsors) if sponsors else "None listed"
        if len(sponsor_str) > 100:
            sponsor_str = sponsor_str[:97] + "..."

        # Build timeline HTML
        timeline_html = ""
        for entry in timeline:
            entry_date = entry.get("date", "")
            try:
                dt = datetime.fromisoformat(entry_date)
                date_str = dt.strftime("%b %d, %Y")
            except (ValueError, TypeError):
                date_str = entry_date

            committee = entry.get("committee", "Unknown Committee")
            action = entry.get("action", "Discussed")

            timeline_html += f"""
                <tr>
                    <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0;">
                        <p style="margin: 0; font-size: 13px; color: #0f172a; font-weight: 600; font-family: 'IBM Plex Mono', monospace;">{date_str}</p>
                    </td>
                    <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0;">
                        <p style="margin: 0; font-size: 13px; color: #475569; font-family: Georgia, serif; line-height: 1.7;">{committee}</p>
                    </td>
                    <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0;">
                        <p style="margin: 0; font-size: 13px; color: #475569; font-family: Georgia, serif; line-height: 1.7;">{action}</p>
                    </td>
                </tr>
            """

        # Truncate summary if too long
        if len(canonical_summary) > 500:
            canonical_summary = canonical_summary[:497] + "..."

        # Get URL
        url = criteria.get("url", "#")

        # Build HTML
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>Engagic Alert: {matter_file}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'IBM Plex Mono', 'Menlo', 'Monaco', 'Courier New', monospace;">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f8fafc;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width: 600px; background-color: #ffffff; border: 2px solid #e2e8f0; border-radius: 11px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <!-- Header with Logo -->
                    <tr>
                        <td style="padding: 32px 40px 24px 40px; background-color: #4f46e5; border-radius: 9px 9px 0 0;">
                            <div style="margin-bottom: 16px;">
                                <span style="font-family: 'IBM Plex Mono', monospace; font-size: 18px; font-weight: 600; color: #ffffff; letter-spacing: -0.02em;">engagic</span>
                            </div>
                            <h1 style="margin: 0 0 12px 0; font-size: 24px; font-weight: 600; color: #ffffff; line-height: 1.3; font-family: 'IBM Plex Mono', monospace;">
                                {matter_file}
                            </h1>
                            <p style="margin: 0 0 8px 0; font-size: 15px; color: #ffffff; opacity: 0.95; font-family: Georgia, serif;">
                                {matter_type} • {city}
                            </p>
                            <p style="margin: 0; font-size: 12px; color: #ffffff; opacity: 0.85; font-family: Georgia, serif;">
                                Official Source
                            </p>
                        </td>
                    </tr>

                    <!-- Alert Name -->
                    <tr>
                        <td style="padding: 24px 40px 16px 40px;">
                            <p style="margin: 0; font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; font-family: 'IBM Plex Mono', monospace;">
                                Alert: {alert.name}
                            </p>
                            <p style="margin: 8px 0 0 0; font-size: 15px; color: #475569; font-family: Georgia, serif; line-height: 1.7;">
                                Matched: <strong>"{keyword}"</strong>
                            </p>
                        </td>
                    </tr>

                    <!-- Matter Title -->
                    <tr>
                        <td style="padding: 0 40px 24px 40px;">
                            <h2 style="margin: 0 0 12px 0; font-size: 18px; font-weight: 600; color: #0f172a; line-height: 1.5; font-family: 'IBM Plex Mono', monospace;">
                                {title}
                            </h2>
                            <p style="margin: 0; font-size: 14px; color: #475569; font-family: Georgia, serif; line-height: 1.7;">
                                <strong>Sponsors:</strong> {sponsor_str}
                            </p>
                        </td>
                    </tr>

                    <!-- Summary -->
                    <tr>
                        <td style="padding: 0 40px 24px 40px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="border-left: 4px solid #4f46e5; background-color: #f8fafc; border-radius: 6px;">
                                <tr>
                                    <td style="padding: 24px;">
                                        <p style="margin: 0 0 12px 0; font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; font-family: 'IBM Plex Mono', monospace;">
                                            Summary
                                        </p>
                                        <p style="margin: 0; font-size: 14px; color: #475569; line-height: 1.7; font-family: Georgia, serif;">
                                            {canonical_summary}
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Timeline -->
                    <tr>
                        <td style="padding: 0 40px 24px 40px;">
                            <p style="margin: 0 0 12px 0; font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; font-family: 'IBM Plex Mono', monospace;">
                                Legislative Timeline ({appearance_count} appearance{"s" if appearance_count != 1 else ""})
                            </p>
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="border: 1px solid #e2e8f0; border-radius: 6px;">
                                <tr style="background-color: #f8fafc;">
                                    <th style="padding: 12px 16px; text-align: left; font-size: 12px; color: #475569; font-weight: 600; border-bottom: 2px solid #e2e8f0; font-family: 'IBM Plex Mono', monospace;">Date</th>
                                    <th style="padding: 12px 16px; text-align: left; font-size: 12px; color: #475569; font-weight: 600; border-bottom: 2px solid #e2e8f0; font-family: 'IBM Plex Mono', monospace;">Committee</th>
                                    <th style="padding: 12px 16px; text-align: left; font-size: 12px; color: #475569; font-weight: 600; border-bottom: 2px solid #e2e8f0; font-family: 'IBM Plex Mono', monospace;">Action</th>
                                </tr>
                                {timeline_html}
                            </table>
                        </td>
                    </tr>

                    <!-- CTA Button -->
                    <tr>
                        <td style="padding: 0 40px 32px 40px;" align="center">
                            <a href="{url}" style="display: inline-block; padding: 12px 32px; background-color: #4f46e5; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; font-family: 'IBM Plex Mono', monospace;">
                                View Official Matter Details
                            </a>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 32px 40px; border-top: 1px solid #e2e8f0;">
                            <p style="margin: 0 0 16px 0; font-size: 12px; color: #475569; font-family: Georgia, serif; line-height: 1.7;">
                                You're receiving this because you subscribed to <strong>{alert.name}</strong> alerts.
                            </p>
                            <p style="margin: 0 0 16px 0; font-size: 12px; color: #64748b; font-family: Georgia, serif; line-height: 1.7;">
                                Engagic is free and open-source. If you find it valuable, please <a href="https://engagic.org/donate" style="color: #8B5CF6; text-decoration: none; font-weight: 600;">support the project</a>.
                            </p>
                            <p style="margin: 0 0 8px 0; font-size: 12px; color: #64748b; font-family: Georgia, serif;">
                                Questions? Visit <a href="https://engagic.org" style="color: #4f46e5; text-decoration: none;">engagic.org</a>
                            </p>
                            <p style="margin: 0; font-size: 12px; font-family: Georgia, serif;">
                                <a href="https://engagic.org/dashboard" style="color: #64748b; text-decoration: underline;">Manage your digests</a>
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


def send_daily_digests(db_path: Optional[str] = None) -> Dict[str, int]:
    """
    Send daily digest emails for all unnotified matches.

    Sends 1 email per meeting (not per alert), showing all matching items.

    Args:
        db_path: Path to userland database

    Returns:
        Dict with stats: emails_sent, items_notified, failed, skipped
    """
    db = UserlandDB(db_path) if db_path else UserlandDB(
        os.getenv('USERLAND_DB', '/root/engagic/data/userland.db')
    )
    email_service = EmailService()

    stats = {"emails_sent": 0, "items_notified": 0, "failed": 0, "skipped": 0}

    # Get all active alerts
    active_alerts = db.get_active_alerts()
    logger.info(f"Processing digests for {len(active_alerts)} active alerts")

    for alert in active_alerts:
        # Get unnotified matches for this alert
        matches = db.get_matches(alert_id=alert.id, notified=False)

        if not matches:
            logger.debug(f"No unnotified matches for alert {alert.name}")
            stats["skipped"] += 1
            continue

        # Get user
        user = db.get_user(alert.user_id)
        if not user:
            logger.error(f"User {alert.user_id} not found for alert {alert.name}")
            stats["failed"] += 1
            continue

        # Group matches by meeting_id
        by_meeting = {}
        for match in matches:
            meeting_id = match.meeting_id
            if meeting_id not in by_meeting:
                by_meeting[meeting_id] = []
            by_meeting[meeting_id].append(match)

        logger.info(
            f"Alert '{alert.name}': {len(matches)} items across "
            f"{len(by_meeting)} meetings"
        )

        # Send 1 email per meeting
        for meeting_id, meeting_matches in by_meeting.items():
            # Send email for this meeting
            success = email_service.send_alert_digest(
                user, alert, meeting_matches
            )

            if success:
                # Mark all items in this meeting as notified
                for match in meeting_matches:
                    db.mark_notified(match.id)
                stats["emails_sent"] += 1
                stats["items_notified"] += len(meeting_matches)

                logger.info(
                    f"Sent email: {meeting_matches[0].matched_criteria['meeting_title'][:50]} "
                    f"({len(meeting_matches)} items)"
                )
            else:
                stats["failed"] += 1

    logger.info(
        f"Daily digest complete: "
        f"{stats['emails_sent']} emails sent, "
        f"{stats['items_notified']} items notified, "
        f"{stats['failed']} failed, "
        f"{stats['skipped']} skipped"
    )

    db.close()
    return stats
