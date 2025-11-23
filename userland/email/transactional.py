"""
Transactional Email Delivery

Magic link emails via Mailgun for authentication.
"""

import logging
import requests
from typing import Optional

from userland.settings import (
    MAILGUN_API_KEY,
    MAILGUN_DOMAIN,
    MAILGUN_FROM_EMAIL,
    APP_URL,
)
from userland.email.templates import (
    DARK_MODE_CSS,
    email_wrapper_start,
    email_wrapper_end,
)

logger = logging.getLogger("userland")


def send_magic_link(
    email: str,
    token: str,
    user_name: Optional[str] = None,
    is_signup: bool = False
) -> bool:
    """
    Send magic link email to user.

    Args:
        email: User email address
        token: Magic link token
        user_name: Optional user name for personalization
        is_signup: True for signup (welcome), False for login (welcome back)

    Returns:
        True if email sent successfully, False otherwise.
    """
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN:
        logger.error("Mailgun not configured. Cannot send magic link.")
        return False

    magic_link = f"{APP_URL}/auth/verify?token={token}"
    name = user_name or email.split('@')[0]

    if is_signup:
        greeting = f"Welcome to Engagic, <strong>{name}</strong>"
        message = "Click the button below to verify your email and access your digest dashboard:"
    else:
        greeting = f"Welcome back, <strong>{name}</strong>"
        message = "Click the button below to access your digest dashboard:"

    subject = "Engagic Login Link"
    html = f"""{email_wrapper_start("Your Engagic Login Link")}
                    <!-- Header -->
                    <tr>
                        <td style="padding: 40px 40px 24px 40px; text-align: center;">
                            <h1 style="margin: 0; font-size: 32px; font-weight: 700; color: #0f172a; letter-spacing: -0.02em;">
                                engagic
                            </h1>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 0 40px 40px 40px;">
                            <p style="margin: 0 0 24px 0; font-size: 18px; line-height: 1.6; color: #0f172a; font-family: Georgia, serif;">
                                {greeting}
                            </p>
                            <p style="margin: 0 0 32px 0; font-size: 15px; line-height: 1.6; color: #475569; font-family: Georgia, serif;">
                                {message}
                            </p>

                            <!-- Button -->
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                <tr>
                                    <td align="center" style="padding: 0 0 32px 0;">
                                        <a href="{magic_link}" style="display: inline-block; padding: 16px 32px; background-color: #4f46e5; color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 15px; font-family: 'IBM Plex Mono', monospace;">
                                            Access Dashboard
                                        </a>
                                    </td>
                                </tr>
                            </table>

                            <p style="margin: 0 0 16px 0; font-size: 13px; line-height: 1.6; color: #64748b; font-family: Georgia, serif;">
                                This link expires in <strong>15 minutes</strong>. If you didn't request this, you can safely ignore this email.
                            </p>

                            <!-- Fallback Link -->
                            <p style="margin: 0; font-size: 12px; line-height: 1.6; color: #94a3b8; font-family: 'IBM Plex Mono', monospace;">
                                Button not working? Copy and paste this link:<br>
                                <a href="{magic_link}" style="color: #4f46e5; word-break: break-all;">{magic_link}</a>
                            </p>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 32px 40px; border-top: 1px solid #e2e8f0; text-align: center;">
                            <p style="margin: 0; font-size: 12px; color: #64748b; font-family: Georgia, serif;">
                                Engagic – Statewide Municipal Intelligence
                            </p>
                        </td>
                    </tr>
{email_wrapper_end()}"""

    text = f"""
    {greeting.replace('<strong>', '').replace('</strong>', '')}

    Click this link to access your digest dashboard:
    {magic_link}

    This link expires in 15 minutes. If you didn't request this, you can safely ignore it.

    --
    Engagic - Statewide Municipal Intelligence
    """

    try:
        response = requests.post(
            f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
            auth=("api", MAILGUN_API_KEY),
            data={
                "from": f"Engagic <{MAILGUN_FROM_EMAIL}>",
                "to": email,
                "subject": subject,
                "text": text,
                "html": html
            },
            timeout=10
        )

        if response.status_code == 200:
            logger.info(f"Magic link sent to {email} (signup={is_signup})")
            return True
        else:
            logger.error(f"Failed to send magic link: {response.status_code} {response.text}")
            return False

    except Exception as e:
        logger.error(f"Error sending magic link: {e}")
        return False
