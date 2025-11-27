"""Text utilities for search result processing."""

import re


def strip_markdown(text: str) -> str:
    """Remove markdown syntax while preserving text content and <mark> tags."""
    if not text:
        return ""
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # headers
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # bold **
    text = re.sub(r'__(.+?)__', r'\1', text)  # bold __
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', text)  # italic *
    text = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'\1', text)  # italic _
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # links
    text = re.sub(r'`([^`]+)`', r'\1', text)  # inline code
    text = re.sub(r'\s+', ' ', text)  # collapse whitespace
    return text.strip()


def extract_context(text: str, keyword: str, length: int = 300) -> str:
    """Extract a snippet centered on the keyword match."""
    if not text:
        return ""

    text_lower = text.lower()
    keyword_lower = keyword.lower()

    pos = text_lower.find(keyword_lower)
    if pos == -1:
        return text[:length] + ("..." if len(text) > length else "")

    half_length = length // 2
    start = max(0, pos - half_length)
    end = min(len(text), pos + len(keyword) + half_length)

    # Adjust to word boundaries
    if start > 0:
        space_pos = text.rfind(" ", 0, start + 20)
        if space_pos > start - 20:
            start = space_pos + 1

    if end < len(text):
        space_pos = text.find(" ", end - 20)
        if space_pos != -1 and space_pos < end + 20:
            end = space_pos

    snippet = text[start:end]

    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    return snippet
