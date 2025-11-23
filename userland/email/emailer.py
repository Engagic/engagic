"""
Email delivery service for weekly digest notifications.

Uses Mailgun for reliable email delivery.
WEEKLY DIGEST ONLY - no alert emails.
"""

import logging
import os
from typing import Optional
import requests

logger = logging.getLogger("engagic")


class EmailService:
    """Send weekly digest emails via Mailgun"""

    def __init__(self, api_key: Optional[str] = None, domain: Optional[str] = None):
        api_key_value = api_key or os.getenv("MAILGUN_API_KEY")
        if not api_key_value:
            raise ValueError("MAILGUN_API_KEY not configured")
        self.api_key: str = api_key_value

        domain_value = domain or os.getenv("MAILGUN_DOMAIN")
        if not domain_value:
            raise ValueError("MAILGUN_DOMAIN not configured")
        self.domain: str = domain_value

        self.from_email = os.getenv("MAILGUN_FROM_EMAIL", f"digest@{self.domain}")
        self.api_url = f"https://api.mailgun.net/v3/{self.domain}/messages"

    def send_email(self, to_email: str, subject: str, html_body: str) -> bool:
        """
        Send a weekly digest HTML email via Mailgun.

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
                f"Sent digest to {to_email}: {subject}, status={response.status_code}"
            )
            return response.status_code == 200

        except requests.RequestException as e:
            logger.error(f"Failed to send digest to {to_email}: {e}")
            return False
