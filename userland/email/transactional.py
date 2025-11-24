"""
Transactional Email Delivery

Magic link emails for authentication via Mailgun.
Uses EmailService for actual sending.
"""

from typing import Optional

from config import config, get_logger
from userland.email.emailer import EmailService
from userland.email.templates import (
    email_wrapper_start,
    email_wrapper_end,
)

logger = get_logger(__name__)


async def send_magic_link(
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
    app_url = config.FRONTEND_URL or "https://engagic.org"
    magic_link = f"{app_url}/auth/verify?token={token}"
    name = user_name or email.split('@')[0]

    if is_signup:
        header_title = f"Welcome to Engagic, {name}"
        header_subtitle = "Your login link is ready"
        message = "Click the button below to verify your email and access your digest dashboard:"
    else:
        header_title = f"Welcome back, {name}"
        header_subtitle = "Your login link is ready"
        message = "Click the button below to access your digest dashboard:"

    subject = "Engagic Login Link"
    html = _build_magic_link_html(header_title, header_subtitle, message, magic_link)
    text = _build_magic_link_text(header_title, header_subtitle, magic_link)

    try:
        email_service = EmailService()
        success = await email_service.send_email(
            to_email=email,
            subject=subject,
            html_body=html,
            text_body=text
        )
        if success:
            logger.info("magic link sent", email=email, is_signup=is_signup)
        return success
    except ValueError as e:
        logger.error("mailgun not configured", error=str(e))
        return False
    except Exception as e:
        logger.error("failed to send magic link", email=email, error=str(e))
        return False


def _build_magic_link_html(
    header_title: str,
    header_subtitle: str,
    message: str,
    magic_link: str
) -> str:
    """Build magic link HTML email template"""
    return f"""{email_wrapper_start("Your Engagic Login Link")}
                    <!-- Header -->
                    <tr>
                        <td style="padding: 32px 40px 28px 40px; background-color: #4f46e5; border-radius: 9px 9px 0 0;">
                            <div style="margin-bottom: 20px; display: flex; align-items: center; gap: 16px;">
                                <img src="https://engagic.org/icon-192.png" alt="Engagic" style="width: 48px; height: 48px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);" />
                                <div style="display: inline-block; padding: 6px 14px; background-color: rgba(255, 255, 255, 0.15); border-radius: 6px; backdrop-filter: blur(10px);">
                                    <span style="font-family: 'IBM Plex Mono', monospace; font-size: 18px; font-weight: 700; color: #ffffff; letter-spacing: 0.02em;">engagic</span>
                                </div>
                            </div>
                            <h1 style="margin: 0 0 10px 0; font-size: 26px; font-weight: 700; color: #ffffff; line-height: 1.3; letter-spacing: -0.02em; font-family: 'IBM Plex Mono', monospace;">
                                {header_title}
                            </h1>
                            <p style="margin: 0; font-size: 15px; color: #ffffff; opacity: 0.92; font-family: Georgia, serif; line-height: 1.5;">
                                {header_subtitle}
                            </p>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 32px 40px 24px 40px;">
                            <p style="margin: 0 0 32px 0; font-size: 15px; line-height: 1.6; color: #475569; font-family: Georgia, serif;">
                                {message}
                            </p>

                            <!-- Button -->
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                <tr>
                                    <td align="center" style="padding: 0 0 32px 0;">
                                        <a href="{magic_link}" style="display: inline-block; padding: 12px 28px; background-color: #4f46e5; color: #ffffff; text-decoration: none; border-radius: 7px; font-weight: 600; font-size: 14px; font-family: 'IBM Plex Mono', monospace; box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2);">
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
                            <p style="margin: 0; font-size: 12px; color: #64748b; font-family: Georgia, serif; line-height: 1.7;">
                                Engagic is free and open-source. If you find it valuable, please <a href="https://engagic.org/about/donate" style="color: #8B5CF6; text-decoration: none; font-weight: 600;">support the project</a>.
                            </p>
                        </td>
                    </tr>
{email_wrapper_end()}"""


def _build_magic_link_text(
    header_title: str,
    header_subtitle: str,
    magic_link: str
) -> str:
    """Build magic link plain text email"""
    return f"""
    {header_title}
    {header_subtitle}

    Click this link to access your digest dashboard:
    {magic_link}

    This link expires in 15 minutes. If you didn't request this, you can safely ignore it.

    --
    Engagic is free and open-source. If you find it valuable, please support the project.
    https://engagic.org/about/donate
    """
