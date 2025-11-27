"""Text utilities for search result processing."""


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
