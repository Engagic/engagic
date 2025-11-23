"""
Shared Email Template Components

Single source of truth for Engagic email design.
Provides reusable components with consistent styling and full dark mode support.
"""

# Dark mode CSS (universal across all email templates)
DARK_MODE_CSS = """
    <style>
        :root {
            color-scheme: light dark;
            supported-color-schemes: light dark;
        }
        @media (prefers-color-scheme: dark) {
            body, table { background-color: #1a1a1a !important; }
            td[style*="background-color: #ffffff"],
            div[style*="background: #ffffff"] { background-color: #1e293b !important; }
            td[style*="background-color: #f8fafc"],
            div[style*="background: #f8fafc"],
            table[style*="background-color: #f8fafc"] { background-color: #0f172a !important; }

            p[style*="color: #0f172a"],
            span[style*="color: #0f172a"],
            div[style*="color: #0f172a"],
            h1[style*="color: #0f172a"],
            h2[style*="color: #0f172a"] { color: #e2e8f0 !important; }

            p[style*="color: #475569"],
            span[style*="color: #475569"],
            div[style*="color: #475569"] { color: #cbd5e1 !important; }

            p[style*="color: #64748b"],
            span[style*="color: #64748b"],
            div[style*="color: #64748b"] { color: #94a3b8 !important; }

            p[style*="color: #334155"],
            span[style*="color: #334155"],
            div[style*="color: #334155"] { color: #e2e8f0 !important; }

            td[style*="border: 2px solid #e2e8f0"],
            table[style*="border: 2px solid #e2e8f0"],
            td[style*="border-top: 1px solid #e2e8f0"],
            td[style*="border-bottom: 1px solid #e2e8f0"] { border-color: #334155 !important; }

            td[style*="border-left: 4px solid"],
            div[style*="border-left: 3px solid"] { border-color: #4f46e5 !important; }

            a[style*="background-color: #4f46e5"] { background-color: #4f46e5 !important; color: #ffffff !important; }
        }
    </style>
"""


def email_wrapper_start(title: str = "Engagic") -> str:
    """
    Start of email HTML structure with dark mode support.

    Args:
        title: Email title for <title> tag

    Returns:
        HTML string for email header and wrapper start
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <title>{title}</title>
{DARK_MODE_CSS}
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'IBM Plex Mono', 'Menlo', 'Monaco', 'Courier New', monospace;">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f8fafc;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width: 600px; background-color: #ffffff; border: 2px solid #e2e8f0; border-radius: 11px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">"""


def email_wrapper_end() -> str:
    """End of email HTML structure"""
    return """
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def header_section(
    title: str,
    subtitle: str = "",
    meta: str = "",
    show_logo: bool = True
) -> str:
    """
    Branded header section with logo.

    Args:
        title: Main heading text
        subtitle: Optional subtitle line
        meta: Optional metadata line (e.g., "Official Source")
        show_logo: Whether to show "engagic" logo above title

    Returns:
        HTML string for header section
    """
    logo_html = """
                            <div style="margin-bottom: 16px;">
                                <span style="font-family: 'IBM Plex Mono', monospace; font-size: 18px; font-weight: 600; color: #ffffff; letter-spacing: -0.02em;">engagic</span>
                            </div>""" if show_logo else ""

    subtitle_html = f"""
                            <p style="margin: 0 0 8px 0; font-size: 15px; color: #ffffff; opacity: 0.95; font-family: Georgia, serif;">
                                {subtitle}
                            </p>""" if subtitle else ""

    meta_html = f"""
                            <p style="margin: 0; font-size: 12px; color: #ffffff; opacity: 0.85; font-family: Georgia, serif;">
                                {meta}
                            </p>""" if meta else ""

    return f"""
                    <tr>
                        <td style="padding: 32px 40px 24px 40px; background-color: #4f46e5; border-radius: 9px 9px 0 0;">{logo_html}
                            <h1 style="margin: 0; font-size: 24px; font-weight: 600; color: #ffffff; line-height: 1.3; font-family: 'IBM Plex Mono', monospace;">
                                {title}
                            </h1>{subtitle_html}{meta_html}
                        </td>
                    </tr>"""


def footer_section(
    alert_name: str = "",
    city_name: str = "",
    show_donation: bool = True,
    dashboard_url: str = "https://engagic.org/dashboard",
    unsubscribe_url: str = "https://engagic.org/unsubscribe"
) -> str:
    """
    Standard footer with manage/unsubscribe links.

    Args:
        alert_name: Optional alert name for subscription context
        city_name: Optional city name for subscription context
        show_donation: Whether to show donation CTA
        dashboard_url: URL for manage subscription link
        unsubscribe_url: URL for unsubscribe link

    Returns:
        HTML string for footer section
    """
    if alert_name:
        subscription_text = f"You're receiving this because you subscribed to <strong>{alert_name}</strong> alerts."
    elif city_name:
        subscription_text = f"You're receiving this because you're watching {city_name}"
    else:
        subscription_text = "You're receiving this email from Engagic."

    donation_html = """
                            <p style="margin: 0 0 16px 0; font-size: 12px; color: #64748b; font-family: Georgia, serif; line-height: 1.7;">
                                Engagic is free and open-source. If you find it valuable, please <a href="https://engagic.org/about/donate" style="color: #8B5CF6; text-decoration: none; font-weight: 600;">support the project</a>.
                            </p>""" if show_donation else ""

    return f"""
                    <tr>
                        <td style="padding: 32px 40px; border-top: 1px solid #e2e8f0;">
                            <p style="margin: 0 0 16px 0; font-size: 12px; color: #475569; font-family: Georgia, serif; line-height: 1.7;">
                                {subscription_text}
                            </p>{donation_html}
                            <p style="margin: 0 0 8px 0; font-size: 12px; color: #64748b; font-family: Georgia, serif;">
                                Questions? Visit <a href="https://engagic.org" style="color: #4f46e5; text-decoration: none;">engagic.org</a>
                            </p>
                            <p style="margin: 0; font-size: 12px; font-family: Georgia, serif;">
                                <a href="{dashboard_url}" style="color: #64748b; text-decoration: underline;">Manage your digests</a>
                                <span style="margin: 0 8px; color: #cbd5e1;">|</span>
                                <a href="{unsubscribe_url}" style="color: #64748b; text-decoration: none;">Unsubscribe</a>
                            </p>
                        </td>
                    </tr>"""


def item_card(
    title: str,
    context: str,
    keyword: str = "",
    url: str = "",
    button_text: str = "View Item"
) -> str:
    """
    Reusable item card with keyword highlighting.

    Args:
        title: Item title
        context: Highlighted context text (from search_summaries)
        keyword: Matched keyword (shown as label)
        url: Link to item
        button_text: CTA button text

    Returns:
        HTML string for item card
    """
    keyword_html = f"""
                                        <p style="margin: 0 0 16px 0; font-size: 13px; color: #64748b; font-family: Georgia, serif;">
                                            Matched: <strong style="color: #475569;">"{keyword}"</strong>
                                        </p>""" if keyword else ""

    button_html = f"""
                                        <a href="{url}" style="display: inline-block; padding: 12px 24px; background-color: #4f46e5; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 13px; font-family: 'IBM Plex Mono', monospace;">
                                            {button_text}
                                        </a>""" if url else ""

    return f"""
                    <tr>
                        <td style="padding: 0 40px 24px 40px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="border-left: 4px solid #4f46e5; background-color: #f8fafc; border-radius: 6px;">
                                <tr>
                                    <td style="padding: 24px;">
                                        <p style="margin: 0 0 12px 0; font-size: 16px; font-weight: 600; color: #0f172a; line-height: 1.5; font-family: 'IBM Plex Mono', monospace;">
                                            {title}
                                        </p>{keyword_html}
                                        <p style="margin: 0 0 20px 0; font-size: 14px; color: #475569; line-height: 1.7; font-family: Georgia, serif;">
                                            {context}
                                        </p>{button_html}
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>"""


def simple_button(url: str, text: str, centered: bool = True) -> str:
    """
    Simple CTA button.

    Args:
        url: Button link
        text: Button text
        centered: Whether to center the button

    Returns:
        HTML string for button
    """
    align_attr = ' align="center"' if centered else ''

    return f"""
                    <tr>
                        <td style="padding: 0 40px 32px 40px;"{align_attr}>
                            <a href="{url}" style="display: inline-block; padding: 12px 32px; background-color: #4f46e5; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; font-family: 'IBM Plex Mono', monospace;">
                                {text}
                            </a>
                        </td>
                    </tr>"""


def section_header(text: str, padding: str = "24px 40px 16px 40px") -> str:
    """
    Section header with uppercase styling.

    Args:
        text: Header text
        padding: CSS padding value

    Returns:
        HTML string for section header
    """
    return f"""
                    <tr>
                        <td style="padding: {padding};">
                            <p style="margin: 0; font-size: 13px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; font-family: 'IBM Plex Mono', monospace;">
                                {text}
                            </p>
                        </td>
                    </tr>"""


def text_content(text: str, padding: str = "0 40px 24px 40px", size: int = 15) -> str:
    """
    Simple text content row.

    Args:
        text: Content text (supports HTML)
        padding: CSS padding value
        size: Font size in pixels

    Returns:
        HTML string for text content
    """
    return f"""
                    <tr>
                        <td style="padding: {padding};">
                            <p style="margin: 0; font-size: {size}px; color: #475569; font-family: Georgia, serif; line-height: 1.7;">
                                {text}
                            </p>
                        </td>
                    </tr>"""
