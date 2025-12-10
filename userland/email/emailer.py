"""
Async email delivery service using Mailgun API.

Provides unified email sending for:
- Weekly digest notifications
- Magic link authentication (via transactional.py)
"""

import httpx
from typing import Optional

from config import config, get_logger

logger = get_logger(__name__)


class EmailService:
    """Async email service using Mailgun API"""

    def __init__(self):
        if not config.MAILGUN_API_KEY or not config.MAILGUN_DOMAIN:
            raise ValueError("Mailgun configuration missing (MAILGUN_API_KEY, MAILGUN_DOMAIN)")
        self.api_key = config.MAILGUN_API_KEY  # Store validated key
        self.api_url = f"https://api.mailgun.net/v3/{config.MAILGUN_DOMAIN}/messages"
        self.from_email = config.MAILGUN_FROM_EMAIL or f"alerts@{config.MAILGUN_DOMAIN}"

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        from_address: Optional[str] = None
    ) -> bool:
        """Send email via Mailgun API (async)

        Args:
            to_email: Recipient email address
            subject: Email subject line
            html_body: HTML content for email body
            text_body: Plain text fallback (optional, defaults to html_body)
            from_address: Override sender (e.g., "Engagic Digest <digest@engagic.org>")

        Returns:
            True if sent successfully, False otherwise
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.api_url,
                    auth=("api", self.api_key),
                    data={
                        "from": from_address or self.from_email,
                        "to": to_email,
                        "subject": subject,
                        "html": html_body,
                        "text": text_body or html_body,
                    },
                    timeout=10
                )
                response.raise_for_status()
                logger.info("email sent", to=to_email, subject=subject[:50])
                return True
            except httpx.HTTPError as e:
                logger.error("email send failed", to=to_email, error=str(e))
                return False
