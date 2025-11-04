"""
Flyer generation service

Generates print-ready HTML flyers for civic action.
Converts passive browsing into active participation.
"""

import base64
from io import BytesIO
from typing import Dict, Any, Optional
from database.db import UnifiedDatabase, Meeting, AgendaItem


def generate_meeting_flyer(
    meeting: Meeting,
    item: Optional[AgendaItem],
    position: str,
    custom_message: Optional[str],
    user_name: Optional[str],
    db: UnifiedDatabase,
) -> str:
    """Generate print-ready HTML flyer

    Args:
        meeting: Meeting object
        item: AgendaItem object (None = whole meeting flyer)
        position: "support" | "oppose" | "more_info"
        custom_message: User's custom message (max 500 chars)
        user_name: User's name for signature line
        db: Database instance

    Returns:
        HTML string ready for printing
    """
    # Get city info
    city = db.get_city(banana=meeting.banana)
    city_name = city.name if city else "Unknown City"
    state = city.state if city else ""

    # Build meeting URL for QR code
    meeting_url = f"https://engagic.com/meetings/{meeting.id}"

    # Generate QR code as data URL
    qr_data_url = _generate_qr_code(meeting_url)

    # Build flyer content
    if item:
        # Item-specific flyer
        item_title = item.title or "Agenda Item"
        item_summary = item.summary or "No summary available"
        agenda_section = f"""
        <div class="agenda-item">
            <h2>Agenda Item</h2>
            <h3>{_escape_html(item_title)}</h3>
            <p class="summary">{_escape_html(item_summary)}</p>
        </div>
        """
    else:
        # Whole meeting flyer
        meeting_title = meeting.title or "City Council Meeting"
        agenda_section = f"""
        <div class="agenda-item">
            <h2>Meeting</h2>
            <h3>{_escape_html(meeting_title)}</h3>
        </div>
        """

    # Position label
    position_labels = {
        "support": "✓ SUPPORT",
        "oppose": "✗ OPPOSE",
        "more_info": "? REQUEST MORE INFORMATION"
    }
    position_label = position_labels.get(position, "POSITION UNKNOWN")

    # Custom message section
    message_section = ""
    if custom_message:
        escaped_message = _escape_html(custom_message[:500])  # Max 500 chars
        message_section = f"""
        <div class="custom-message">
            <p>"{escaped_message}"</p>
        </div>
        """

    # Signature section
    signature_section = ""
    if user_name:
        signature_section = f"""
        <div class="signature">
            <p>— {_escape_html(user_name)} —</p>
        </div>
        """

    # Participation info
    participation = meeting.participation or {}
    participation_lines = []

    if participation.get("email"):
        participation_lines.append(f"<p><strong>EMAIL:</strong> {_escape_html(participation['email'])}</p>")

    if participation.get("phone"):
        participation_lines.append(f"<p><strong>PHONE:</strong> {_escape_html(participation['phone'])}</p>")

    if participation.get("zoom_url"):
        zoom_url = participation["zoom_url"]
        participation_lines.append(f"<p><strong>ZOOM:</strong> <a href=\"{_escape_html(zoom_url)}\">{_escape_html(zoom_url)}</a></p>")

    participation_html = "\n".join(participation_lines) if participation_lines else "<p>Contact your city for participation details</p>"

    # Format date
    meeting_date = meeting.date or "Date TBD"

    # Build complete HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Civic Action Flyer - {city_name}</title>
    <style>
        @page {{
            size: letter;
            margin: 0.5in;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #000;
            background: #fff;
            max-width: 8.5in;
            margin: 0 auto;
            padding: 0.5in;
        }}

        .flyer {{
            border: 3px solid #000;
            padding: 1.5rem;
        }}

        .header {{
            text-align: center;
            border-bottom: 2px solid #000;
            padding-bottom: 1rem;
            margin-bottom: 1rem;
        }}

        .header h1 {{
            font-size: 24pt;
            font-weight: 700;
            letter-spacing: 2px;
            margin-bottom: 0.5rem;
        }}

        .meeting-info {{
            margin-bottom: 1.5rem;
        }}

        .meeting-info h2 {{
            font-size: 14pt;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }}

        .meeting-info p {{
            font-size: 11pt;
            margin-bottom: 0.25rem;
        }}

        .agenda-item {{
            margin-bottom: 1.5rem;
            padding: 1rem;
            background: #f5f5f5;
            border-left: 4px solid #000;
        }}

        .agenda-item h2 {{
            font-size: 10pt;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 0.5rem;
            color: #666;
        }}

        .agenda-item h3 {{
            font-size: 14pt;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }}

        .agenda-item .summary {{
            font-size: 10pt;
            line-height: 1.5;
        }}

        .position {{
            margin-bottom: 1.5rem;
            padding: 1rem;
            background: #000;
            color: #fff;
            text-align: center;
        }}

        .position h2 {{
            font-size: 18pt;
            font-weight: 700;
            letter-spacing: 2px;
        }}

        .custom-message {{
            margin-bottom: 1.5rem;
            padding: 1rem;
            border: 2px solid #ccc;
            font-style: italic;
            font-size: 11pt;
        }}

        .signature {{
            text-align: center;
            margin-bottom: 1.5rem;
            font-size: 12pt;
            font-weight: 500;
        }}

        .participation {{
            margin-bottom: 1.5rem;
            padding: 1rem;
            background: #fffacd;
            border: 2px solid #ffd700;
        }}

        .participation h2 {{
            font-size: 12pt;
            font-weight: 700;
            margin-bottom: 0.75rem;
            text-transform: uppercase;
        }}

        .participation p {{
            font-size: 10pt;
            margin-bottom: 0.5rem;
        }}

        .participation a {{
            color: #000;
            text-decoration: underline;
            word-break: break-all;
        }}

        .footer {{
            border-top: 2px solid #000;
            padding-top: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .footer .qr-code {{
            width: 80px;
            height: 80px;
        }}

        .footer .branding {{
            text-align: right;
            font-size: 10pt;
        }}

        .footer .branding p {{
            margin-bottom: 0.25rem;
        }}

        .footer .branding .url {{
            font-weight: 700;
            font-size: 12pt;
        }}

        @media print {{
            body {{
                padding: 0;
            }}

            .flyer {{
                border: 3px solid #000;
            }}
        }}
    </style>
</head>
<body>
    <div class="flyer">
        <div class="header">
            <h1>CIVIC ACTION FLYER</h1>
        </div>

        <div class="meeting-info">
            <h2>{_escape_html(city_name)}{', ' + state if state else ''}</h2>
            <p><strong>Date:</strong> {_escape_html(meeting_date)}</p>
        </div>

        {agenda_section}

        <div class="position">
            <h2>MY POSITION: {position_label}</h2>
        </div>

        {message_section}

        {signature_section}

        <div class="participation">
            <h2>How to Participate</h2>
            {participation_html}
        </div>

        <div class="footer">
            <img src="{qr_data_url}" alt="QR Code to Meeting" class="qr-code">
            <div class="branding">
                <p>Scan QR code to view full agenda</p>
                <p class="url">engagic.com</p>
            </div>
        </div>
    </div>
</body>
</html>"""

    return html


def _generate_qr_code(url: str) -> str:
    """Generate QR code as data URL

    Returns base64-encoded PNG as data URL.
    Falls back to placeholder if qrcode library not available.
    """
    try:
        import qrcode

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to data URL
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()
        img_base64 = base64.b64encode(img_bytes).decode()

        return f"data:image/png;base64,{img_base64}"

    except ImportError:
        # QR code library not available - return placeholder
        # Simple SVG placeholder (40x40 black square)
        svg = '<svg width="80" height="80" xmlns="http://www.w3.org/2000/svg"><rect width="80" height="80" fill="black"/><text x="40" y="45" text-anchor="middle" fill="white" font-size="10">QR</text></svg>'
        svg_base64 = base64.b64encode(svg.encode()).decode()
        return f"data:image/svg+xml;base64,{svg_base64}"


def _escape_html(text: str) -> str:
    """Escape HTML special characters"""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
