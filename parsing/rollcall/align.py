"""Align a minutes document to the meeting's own agenda items.

Minutes are generated from the agenda we already parsed, so the candidate
set for any vote is the handful of items in that one meeting and the
question is only where each item starts in the text. Ladder, most to least
reliable: the matter file number printed beside the item, the agenda number
at a line start, the item title itself. Anchors must appear in agenda order;
an out-of-order match is a false positive and is dropped (longest increasing
subsequence over document offsets).

Confidence 7/10. Title matching is the weak rung: chunker titles can be
garbage for PDF-born agendas, and then the item simply has no block.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence

_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "to", "for", "in", "on", "at", "by", "with",
    "from", "as", "is", "be", "that", "this", "city", "county", "council", "approve",
    "approval", "consider", "consideration", "action", "item", "regarding", "re",
}


@dataclass
class Anchor:
    item: Any
    start: int
    rung: str


def _file_pattern(matter_file: str) -> Optional[re.Pattern]:
    core = matter_file.split(" ", 1)[1] if " " in matter_file else matter_file
    core = core.strip()
    if len(core) < 4:
        return None
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(core) + r"(?![A-Za-z0-9])", re.IGNORECASE)


def _agenda_pattern(agenda_number: str) -> Optional[re.Pattern]:
    number = agenda_number.strip().rstrip(".)")
    if not number or len(number) > 12:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)+", number) and not re.fullmatch(r"\d{1,2}\.[A-Za-z0-9]{1,2}", number):
        return None  # "43.7" / "732.50" are measurements the chunker mistook for numbering
    if re.fullmatch(r"\d{1,2}|[a-zA-Z]", number):
        # "7." or "a." at a line start is unique enough only with a word after it
        return re.compile(r"^[ \t]*" + re.escape(number) + r"[.)]\s+(?=[A-Za-z])", re.MULTILINE)
    return re.compile(r"^[ \t]*" + re.escape(number) + r"[.)]?\s+(?=[A-Za-z(\"'])", re.MULTILINE)


def _title_words(title: str) -> List[str]:
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", title.lower()) if w not in _STOPWORDS]
    return words[:8]


def _title_match(text_lower: str, lines_lower: List[str], line_offsets: List[int], title: str) -> Optional[int]:
    words = _title_words(title)
    if len(words) < 3:
        return None
    probe = r"\W+(?:\w+\W+){0,3}?".join(re.escape(w) for w in words[:5])
    m = re.search(probe, text_lower)
    if m:
        return m.start()
    # Fuzzy fallback only over lines that share the title's rarest word;
    # SequenceMatcher over every line of a 40-page document is quadratic.
    target = " ".join(words)
    rare = max(words, key=len)
    best, best_ratio = None, 0.0
    for offset, line in zip(line_offsets, lines_lower):
        if len(line) < 20 or rare not in line:
            continue
        matcher = SequenceMatcher(None, target, " ".join(_title_words(line)))
        if matcher.quick_ratio() < 0.8:
            continue
        ratio = matcher.ratio()
        if ratio > best_ratio:
            best, best_ratio = offset, ratio
    return best if best_ratio >= 0.8 else None


def _longest_increasing(anchors: List[Anchor]) -> List[Anchor]:
    if not anchors:
        return anchors
    n = len(anchors)
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if anchors[j].start < anchors[i].start and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    end = max(range(n), key=lambda k: best[k])
    chain = []
    while end != -1:
        chain.append(anchors[end])
        end = prev[end]
    return list(reversed(chain))


def anchor_items(text: str, items: Sequence[Any]) -> List[Anchor]:
    """Items in agenda order with their start offset in the minutes, where found.

    Each item is a mapping with title, agenda_number, matter_file, sequence.
    """
    text_lower = text.lower()
    lines = text.splitlines()
    line_offsets, pos = [], 0
    for line in lines:
        line_offsets.append(pos)
        pos += len(line) + 1
    lines_lower = [line.lower() for line in lines]

    anchors: List[Anchor] = []
    for item in sorted(items, key=lambda it: it.get("sequence") or 0):
        start, rung = None, ""
        if item.get("matter_file"):
            pattern = _file_pattern(str(item["matter_file"]))
            m = pattern.search(text) if pattern else None
            if m:
                start, rung = m.start(), "matter_file"
        if start is None and item.get("agenda_number"):
            pattern = _agenda_pattern(str(item["agenda_number"]))
            m = pattern.search(text) if pattern else None
            if m:
                start, rung = m.start(), "agenda_number"
        if start is None and item.get("title"):
            found = _title_match(text_lower, lines_lower, line_offsets, str(item["title"]))
            if found is not None:
                start, rung = found, "title"
        if start is not None:
            # Snap to the line start so the previous block never swallows
            # this item's numbering ("b.") as a trailing name fragment.
            start = text.rfind("\n", 0, start) + 1
            anchors.append(Anchor(item=item, start=start, rung=rung))
    return _longest_increasing(anchors)


def blocks(text: str, anchors: List[Anchor]) -> List[Dict[str, Any]]:
    """[{item, start, end, rung}] covering each anchored item to the next anchor."""
    out = []
    for i, anchor in enumerate(anchors):
        end = anchors[i + 1].start if i + 1 < len(anchors) else len(text)
        out.append({"item": anchor.item, "start": anchor.start, "end": end, "rung": anchor.rung})
    return out
