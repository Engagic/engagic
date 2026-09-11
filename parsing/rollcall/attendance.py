"""Attendance roster from the head of a minutes document.

For a city without a votes API the minutes are the only roster source. Every
template family observed prints one of three shapes near the top:

    Present  7 -  Flynn, Gonzales-Gutierrez, Vice Chair Amanda Sandoval, ...
    Absent  1 -  Romero Campbell
    Members present: Smith, Jones, Lee. Members absent: Kim.
    Mayor Moriwaki, Deputy Mayor Hytopoulos and Councilmembers Lant, Mathews,
    Nelson, and Schneider were present. Councilmember Fantroy-Johnson was absent

Confidence 7/10: the label forms are exact, the narrative form is a sentence
regex and is validated by the tally arithmetic downstream, never trusted on
its own.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

from parsing.rollcall.names import split_names

HEAD_CHARS = 6000

_LABEL_RE = re.compile(
    r"^[ \t]*(?:members?\s+|board\s+members?\s+|councilmembers?\s+|those\s+)?"
    r"(?P<kind>present|absent|excused)\b\s*[:\-–]?\s*(?:(?P<count>\d+)\s*[-–]\s*)?(?P<rest>.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_STOP_RE = re.compile(
    r"^[ \t]*(?:(?:members?\s+|also\s+)?(?:present|absent|excused|staff|also present|others present|"
    r"call to order|pledge|roll call|approval|agenda|minutes|action items|consent|briefings|\d+\.|[A-Z]\.)\b|\s*$)",
    re.IGNORECASE,
)
# Sentences wrap across extracted lines; allow newlines but never a period.
_NARRATIVE_PRESENT_RE = re.compile(
    r"(?P<names>[A-Z][^.:;]{3,400}?)\s+(?:were|was)\s+(?:all\s+)?present\b", re.DOTALL
)
_NARRATIVE_ABSENT_RE = re.compile(
    r"(?P<names>[A-Z][^.:;]{3,200}?)\s+(?:were|was)\s+absent\b", re.DOTALL
)


@dataclass
class Attendance:
    present: List[str] = field(default_factory=list)
    absent: List[str] = field(default_factory=list)
    present_count: Optional[int] = None
    source: str = "none"

    @property
    def known(self) -> bool:
        return bool(self.present)


def _collect(lines: List[str], start: int) -> str:
    """Names continue on following lines until a blank or a new label.

    A wrapped tail ("Stephanie" / "W. Telles") looks like a lettered heading
    to the stop rule; a real heading carries a sentence, a wrapped name does
    not, so a line of three words or fewer after an unterminated line stays.
    """
    out = [lines[start]]
    for line in lines[start + 1:start + 5]:
        stripped = line.strip()
        heading = re.match(r"^(?:[a-z]|\d+(?:\.\d+)*|[A-Z]{2,3})[.)]\s", stripped) or re.search(r"\d", stripped)
        wrapped_tail = (
            len(stripped.split()) <= 3 and not heading and not out[-1].rstrip().endswith(".")
        )
        if not stripped or (_STOP_RE.match(line) and not wrapped_tail) or (heading and not wrapped_tail):
            break
        out.append(stripped)
    return " ".join(out)


def parse_attendance(text: str) -> Attendance:
    head = text[:HEAD_CHARS]
    lines = head.splitlines()
    result = Attendance()
    for i, line in enumerate(lines):
        m = _LABEL_RE.match(line)
        if not m:
            continue
        rest = m.group("rest").strip()
        if rest and rest[0] in ".,:" and len(rest) < 3:
            continue
        blob = _collect([rest] + lines[i + 1:], 0) if rest else _collect(lines, i + 1) if i + 1 < len(lines) else ""
        names = split_names(blob)
        kind = m.group("kind").lower()
        if kind == "present" and names and not result.present:
            result.present = names
            result.present_count = int(m.group("count")) if m.group("count") else None
            result.source = "label"
        elif kind in ("absent", "excused") and names and not result.absent:
            result.absent = names
    if not result.present:
        m = _NARRATIVE_PRESENT_RE.search(head[:3000])
        if m:
            names = split_names(m.group("names").replace("\n", " "))
            if 2 <= len(names) <= 25:
                result.present = names
                result.source = "narrative"
                a = _NARRATIVE_ABSENT_RE.search(head[:3000])
                if a:
                    result.absent = split_names(a.group("names").replace("\n", " "))[-3:]
    return result
