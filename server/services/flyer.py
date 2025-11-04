"""
Flyer generation service

Generates print-ready HTML flyers for civic action.
Converts passive browsing into active participation.
"""

import base64
import os
import re
from io import BytesIO
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from database.db import UnifiedDatabase, Meeting, AgendaItem


def _clean_summary_for_flyer(summary: str) -> Tuple[str, str]:
    """Clean summary for flyer display

    Extracts summary, citizen impact, and confidence rating.
    Removes thinking and LLM artifacts for concise print output.

    Returns:
        Tuple of (cleaned_summary, confidence_rating)
    """
    if not summary:
        return "No summary available", ""

    confidence = ""

    # Step 1: Remove thinking section entirely (before "## Summary")
    parts = re.split(r'^## Thinking\s*$', summary, flags=re.MULTILINE)
    if len(parts) > 1:
        summary = parts[1]  # Everything after thinking

    # Step 2: Extract Summary, Citizen Impact, and Confidence sections
    # Split into sections by ## headers
    sections = re.split(r'^##\s+(\w+.*?)$', summary, flags=re.MULTILINE)

    keep_sections = []
    i = 0
    while i < len(sections):
        if i + 1 < len(sections):
            section_name = sections[i + 1].strip().lower()
            section_content = sections[i + 2] if i + 2 < len(sections) else ""

            # Extract confidence separately
            if 'confidence' in section_name:
                confidence = section_content.strip()
            # Keep Summary and Citizen Impact
            elif 'summary' in section_name or 'citizen impact' in section_name or 'impact' in section_name:
                keep_sections.append(section_content.strip())

            i += 2
        else:
            # Remaining content without header
            remaining = sections[i].strip()
            # Check if it's a standalone confidence value
            if remaining and re.match(r'^(high|medium|low)$', remaining, re.IGNORECASE):
                confidence = remaining
            elif remaining:
                keep_sections.append(remaining)
            i += 1

    summary = "\n\n".join(keep_sections)

    # Step 3: Remove LLM preamble patterns
    summary = re.sub(r'=== DOCUMENT \d+ ===', '', summary)
    summary = re.sub(r'--- SECTION \d+ SUMMARY ---', '', summary)
    summary = re.sub(r"Here's a concise summary of the[^:]*:", '', summary, flags=re.IGNORECASE)
    summary = re.sub(r"Here's a summary of the[^:]*:", '', summary, flags=re.IGNORECASE)
    summary = re.sub(r"Here's the key points[^:]*:", '', summary, flags=re.IGNORECASE)
    summary = re.sub(r"Summary of the[^:]*:", '', summary, flags=re.IGNORECASE)

    # Step 4: Clean up markdown for print (keep bullets, remove bold)
    summary = re.sub(r'\*\*([^*]+)\*\*', r'\1', summary)  # Remove bold markdown
    summary = re.sub(r'^[\*\-]\s+', '• ', summary, flags=re.MULTILINE)  # Standardize bullets
    summary = re.sub(r'\n{3,}', '\n\n', summary)  # Collapse extra newlines

    summary = summary.strip()

    # Step 5: Convert to simple HTML
    summary = summary.replace('\n\n', '</p><p>')
    summary = summary.replace('\n', '<br>')

    return f"<p>{summary}</p>", confidence.capitalize()


def _generate_meeting_slug(meeting: Meeting) -> str:
    """Generate meeting slug matching frontend format: {title}_{date}_{id}"""
    title = meeting.title or "meeting"

    # Format date as YYYY_MM_DD
    date_slug = "undated"
    if meeting.date:
        date_slug = meeting.date.strftime("%Y_%m_%d")

    # Clean title: lowercase, alphanumeric only, underscores
    clean_title = re.sub(r'[^a-z0-9\s]', '', title.lower())
    clean_title = re.sub(r'\s+', '_', clean_title)[:50]

    # Format: {title}_{date}_{id}
    return f"{clean_title}_{date_slug}_{meeting.id}"


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
    # Load template
    template_path = Path(__file__).parent / "flyer_template.html"
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()

    # Get city info
    city = db.get_city(banana=meeting.banana)
    city_name = city.name if city else "Unknown City"
    state = city.state if city else ""
    city_display = f"{city_name}{', ' + state if state else ''}"

    # Build meeting URL for QR code (matches frontend routing)
    meeting_slug = _generate_meeting_slug(meeting)
    meeting_url = f"https://engagic.org/{meeting.banana}/{meeting_slug}"

    # Generate QR code as data URL
    qr_data_url = _generate_qr_code(meeting_url)

    # Build flyer content
    confidence_display = ""
    if item:
        # Item-specific flyer
        item_title = item.title or "Agenda Item"
        item_summary_html, confidence = _clean_summary_for_flyer(item.summary or "")
        if confidence:
            confidence_display = f'<div class="confidence-badge">{confidence} Confidence</div>'
        agenda_section = f"""
        <div class="agenda-content">
            <h2 class="agenda-title">{_escape_html(item_title)}</h2>
            <div class="summary">{item_summary_html}</div>
            {confidence_display}
        </div>
        """
    else:
        # Whole meeting flyer
        meeting_title = meeting.title or "City Council Meeting"
        meeting_summary_html, confidence = _clean_summary_for_flyer(meeting.summary or "")
        if confidence:
            confidence_display = f'<div class="confidence-badge">{confidence} Confidence</div>'
        agenda_section = f"""
        <div class="agenda-content">
            <h2 class="agenda-title">{_escape_html(meeting_title)}</h2>
            <div class="summary">{meeting_summary_html}</div>
            {confidence_display}
        </div>
        """

    # Position label
    position_labels = {
        "support": "✓ SUPPORT",
        "oppose": "✗ OPPOSE",
        "more_info": "? REQUEST MORE INFORMATION"
    }
    position_label = position_labels.get(position, "POSITION UNKNOWN")

    # Custom message section (only if provided)
    message_section = ""
    if custom_message and custom_message.strip():
        escaped_message = _escape_html(custom_message[:500].strip())
        message_section = f"""
        <div class="custom-message">
            <p>"{escaped_message}"</p>
        </div>
        """

    # Signature section (only if provided)
    signature_section = ""
    if user_name and user_name.strip():
        escaped_name = _escape_html(user_name[:100].strip())
        signature_section = f"""
        <div class="signature">
            <p>— {escaped_name} —</p>
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
    if meeting.date:
        meeting_date = _escape_html(meeting.date.strftime("%B %d, %Y at %I:%M %p"))
    else:
        meeting_date = "Date TBD"

    # Render template with data (use replace to avoid CSS curly brace conflicts)
    html = template
    html = html.replace('{city_name}', _escape_html(city_name))
    html = html.replace('{city_display}', _escape_html(city_display))
    html = html.replace('{meeting_date}', meeting_date)
    html = html.replace('{agenda_section}', agenda_section)
    html = html.replace('{position_label}', position_label)
    html = html.replace('{message_section}', message_section)
    html = html.replace('{signature_section}', signature_section)
    html = html.replace('{participation_html}', participation_html)
    html = html.replace('{qr_data_url}', qr_data_url)

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
