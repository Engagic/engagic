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

# A present-list often runs straight into the next roster on the same
# extracted line: "Members Present: A, B, C. Absent: D Guests attending: E".
_INLINE_CUT_RE = re.compile(
    r"\b(?:absent|excused|guests?|staff|also\s+present|others?\s+present|alternates?|"
    r"also\s+in\s+attendance|not\s+present)\b\s*:?",
    re.IGNORECASE,
)

# Words that mark a department, office or role rather than a person.
_NOT_PERSON_RE = re.compile(
    r"\b(?:parks?|recreation|departments?|dept|interns?|staff|city|county|planning|"
    r"directors?|clerks?|attorneys?|engineers?|managers?|works|public|finance|library|police|"
    r"fire|administrators?|administration|services|office|utilities|community|"
    r"development|building|zoning|secretar(?:y|ies)|recorders?|treasurers?|assistants?|"
    r"guests?|alternates?|liaisons?|consultants?|applicants?)\b",
    re.IGNORECASE,
)

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
# "...Council Members were present: Jack Sheard, Mark Stelk, ... Absent: Mike Paulick."
# "Board members in attendance included Andrew Reynolds, Michael Telich and Brian LaFleur."
_NAMES_AFTER_PRESENT_RE = re.compile(
    r"(?:(?:were|was|members)\s+present|\bpresent)\s*(?:\bwere\b|\bwas\b|\bincluded\b|:)\s*"
    r"(?P<names>[^.]{5,400}?)(?:\.\s|\bAbsent\b|$)",
    re.DOTALL | re.IGNORECASE,
)
_IN_ATTENDANCE_RE = re.compile(
    r"in\s+attendance\s+(?:were|included|was)\s*:?\s*(?P<names>[^.]{5,400}?)\.", re.DOTALL | re.IGNORECASE
)
_INLINE_ABSENT_RE = re.compile(r"\bAbsent\s*:\s*(?P<names>[^.\n]{2,200}?)(?:\.|\n|$)", re.IGNORECASE)
# "Present were A, B" reaches the label path with the verb still attached.
_LEADING_VERB_RE = re.compile(r"^\s*(?:were|was|are|is|included|include)\b\s*:?\s*", re.IGNORECASE)


@dataclass
class Attendance:
    present: List[str] = field(default_factory=list)
    absent: List[str] = field(default_factory=list)
    present_count: Optional[int] = None
    source: str = "none"

    @property
    def known(self) -> bool:
        return bool(self.present)

    def drop_staff(self) -> None:
        """Remove role or department tokens that rode in on the same line."""
        self.present = [n for n in self.present if not _NOT_PERSON_RE.search(n)]
        self.absent = [n for n in self.absent if not _NOT_PERSON_RE.search(n)]

    def plausible(self) -> bool:
        return len(self.present) >= 2


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
        blob = _LEADING_VERB_RE.sub("", blob)
        cut = _INLINE_CUT_RE.search(blob)
        if cut and cut.start() > 0:
            blob = blob[:cut.start()]
        names = split_names(blob)
        kind = m.group("kind").lower()
        if kind == "present" and names and not result.present:
            result.present = names
            result.present_count = int(m.group("count")) if m.group("count") else None
            result.source = "label"
        elif kind in ("absent", "excused") and names and not result.absent:
            result.absent = names
    if not result.present:
        for pattern in (_NAMES_AFTER_PRESENT_RE, _IN_ATTENDANCE_RE, _NARRATIVE_PRESENT_RE):
            m = pattern.search(head[:4000])
            if not m:
                continue
            blob = m.group("names").replace("\n", " ")
            cut = _INLINE_CUT_RE.search(blob)
            if cut and cut.start() > 0:
                blob = blob[:cut.start()]
            names = split_names(blob)
            if 2 <= len(names) <= 25:
                result.present = names
                result.source = "narrative"
                break
    result.drop_staff()
    if result.present and not result.plausible():
        result = Attendance()
    if result.present and not result.absent:
        a = _INLINE_ABSENT_RE.search(head[:4000]) or _NARRATIVE_ABSENT_RE.search(head[:4000])
        if a:
            blob = a.group("names").replace("\n", " ")
            cut = _INLINE_CUT_RE.search(blob)
            if cut and cut.start() > 0:
                blob = blob[:cut.start()]
            result.absent = split_names(blob)[-4:]
            result.drop_staff()
    return result
