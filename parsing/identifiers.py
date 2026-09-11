"""Durable identifier extraction from agenda text.

Legislative bodies act on the same thing repeatedly: a contract goes to
committee, then to the full council, then comes back as an amendment. Vendors
rarely expose a stable key for that -- many mint a fresh backend id per agenda --
but the government's own text almost always cites one: a contract number, a law
department file number, a zoning case number.

Extracting that identifier turns a pile of unrelated items into one matter with
one canonical summary and a real timeline.

A wrong identifier is expensive and not self-correcting: it permanently merges
unrelated items into one city_matters row under a single summary. Every pattern
here is therefore anchored on an explicit label and refuses to guess from bare
numbers. Validated against 30 real agendas across 14 cities: 110 matches, zero
false positives.
"""

import re
from typing import List, Optional, Tuple

# (class label, matter_type, pattern). Order is priority order.
#
# The emitted matter_file is namespaced by class ("Contract 6007968", not
# "6007968") because a contract number and a court case number can collide
# numerically inside one city.
IDENTIFIER_PATTERNS: List[Tuple[str, str, str]] = [
    # Contract No. 6007968 / 6006718-A1 (AMEND 1) / 6007823-D / 6007381-R.
    #
    # Two guards, both learned from real corpus damage:
    #   - The suffix group must consume at least one character. An
    #     optional-content group happily captures a dangling hyphen
    #     ("Contract 210044-"), and "6006718-100% City Funding" captures a
    #     funding share as an amendment suffix.
    #   - "Master Contract" is skipped. Alameda County writes "Master Contract
    #     No. 902683; Procurement Contract No. 30090" -- the master is a
    #     vendor-level umbrella, so keying on it would merge every distinct
    #     agreement with that vendor into a single matter. The procurement
    #     number in the same sentence is the item's actual identity.
    ("Contract", "Contract",
     r"\bContract\s*(?:No\.?|Number|#)\s*"
     r"([0-9]{4,10}(?:-(?!\d{1,3}%)[A-Za-z0-9]{1,4})?)\b"),
    # File No. L25-8029 (Detroit law dept) / File #SD25-0033 (Los Altos Hills site
    # development) / File No. CM25-19446 (Tampa) / File No. 15120 (workers' comp).
    # The type stays generic: cities file lawsuits, permits and rezonings alike
    # under "File No.".
    # "CASE FILE NO. 2026-07-V" (Odessa) is one file, not "File 2026": a bare
    # number that continues into a dashed code is never the whole identifier.
    ("File", "File",
     r"\bFile\s*(?:No\.?|#)\s*"
     r"([A-Za-z]{0,2}[0-9]{2}-[0-9]{3,6}|[0-9]{4}-[0-9]{2,3}-[A-Za-z0-9]{1,5}|[0-9]{4,6}(?!-[A-Za-z0-9]))\b"),
    # Unlabelled law-department file cited mid-sentence: "...24-016365-NF; L24-01403 (VI)".
    # Same settlement, same durable handle, so it must key identically to the
    # sibling items that do label it -- otherwise one lawsuit becomes two matters.
    ("File", "Settlement", r"\b(L[0-9]{2}-[0-9]{3,6})\b"),
    # Case No. 25-011182 / Case #26-041 / Case No. 25-cv-10245 / Case No. W24-00043
    ("Case", "Case",
     r"\bCase\.?\s*(?:No\.?|#)\s*([A-Za-z]{0,2}[0-9]{2}-(?:[A-Za-z]{2}-)?[0-9]{3,6})\b"),
    # Petition No. 1234 (street vacations, encroachments)
    ("Petition", "Petition",
     r"\bPetition\s*(?:No\.?|Number|#)\s*([0-9]{3,7}(?:-[A-Za-z0-9]{1,3})?)\b"),
]

_COMPILED = [
    (label, matter_type, re.compile(pattern, re.IGNORECASE))
    for label, matter_type, pattern in IDENTIFIER_PATTERNS
]

# Legislative instrument numbers. These are searched only in the title and the
# head of the body: an ordinance body routinely cites the ordinances it amends
# ("...amending Ordinance No. 1187..."), and keying on a cited number would
# merge the amendment into the thing it amends. The head of an item is where
# the instrument names itself.
#
# Token shape: optional letter prefix, digits, up to two dashed suffixes
# ("2026-05", "1234", "O-26-12", "RS2026-118", "25-08-A"). A bare year with no
# dash ("Ordinance No. 2026") is rejected as a probable typo or date.
_INSTRUMENT_TOKEN = (
    r"([A-Za-z]{0,4}-?(?:[0-9]{1,2},[0-9]{3}|[0-9]{1,6})(?:-[A-Za-z0-9.]{1,6}){0,2})\b"
)
# A cited instrument is not the item's own: "amending Ordinance No. 1187",
# "per CA Assembly Bill No. 481". Matches preceded by these are skipped.
_CITATION_BEFORE_RE = re.compile(
    r"(?:amend\w*|repeal\w*|rescind\w*|supersed\w*|assembly|senate|house)"
    r"\s+(?:\w+\s+){0,2}$",
    re.IGNORECASE,
)
HEAD_IDENTIFIER_PATTERNS: List[Tuple[str, str, str]] = [
    ("Ordinance", "Ordinance",
     r"\bOrdinance\s*(?:No\.?|Number|#)\s*:?\s*" + _INSTRUMENT_TOKEN),
    ("Resolution", "Resolution",
     r"\bResolution\s*(?:No\.?|Number|#)\s*:?\s*" + _INSTRUMENT_TOKEN),
    # "Board Bill 107" (St. Louis), "Council Bill 120345" (Seattle), "Bill No. 25-123".
    ("Bill", "Bill",
     r"\b(?:(?:Board|Council)\s+Bill|Bill\s*(?:No\.?|Number|#))\s*:?\s*" + _INSTRUMENT_TOKEN),
]
_HEAD_COMPILED = [
    (label, matter_type, re.compile(pattern, re.IGNORECASE))
    for label, matter_type, pattern in HEAD_IDENTIFIER_PATTERNS
]
HEAD_CHARS = 300

# Unlabelled codes that are only trusted in the title, where a chunker or
# vendor put the document's own heading. Emitted raw (no class prefix): the
# prefix letters are the namespace, and API vendors store the same shape
# ("BL2025-1098") unprefixed, so a city migrating vendors keys identically.
#
# Leading legislative file token: "2026-412 Approve..." / "24-0123 Ordinance...".
# 4-digit-year or 2-digit-year prefix only, so "03-25" (a date) never matches.
# An alphanumeric sub-file suffix is part of the identity: Los Angeles files
# every appointment under "22-1200-S49", and the S-numbers are distinct items.
_LEADING_FILE_RE = re.compile(
    r"^\s*((?:(?:19|20)\d{2}-\d{1,6}|\d{2}-\d{3,6})(?:-[A-Z]{1,2}\d{1,4})?)(?![0-9])(?!-\d)"
)
_WORD_RE = re.compile(r"[A-Za-z]{4}")
# Parenthesised department code: "(PC-11015)" / "(GEN-1284)" (Oklahoma City).
_PAREN_CODE_RE = re.compile(r"\(([A-Z]{1,5}-[0-9]{3,6})\)")
# Prefixed year-numbered code: "CU-26-012", "RES-2026-14", "PUD-24-007".
# The middle group must be year-shaped so "US-101-..." style names never
# match; two-digit years are limited to 2015-2029 so "CC-06-15" (a date-like
# committee code) does not key.
# Year-last form: "O-079-26" / "R-112-26" (Louisville ordinances and resolutions).
_DASH_CODE_RE = re.compile(
    r"\b([A-Z]{2,5}-(?:1[5-9]|2[0-9]|(?:19|20)[0-9]{2})-[0-9]{2,6}(?:-[0-9]{1,6}){0,2}"
    r"|[A-Z]{1,5}-[0-9]{3,4}-(?:1[5-9]|2[0-9]))\b"
)


def extract_leading_file_token(title: Optional[str]) -> Optional[str]:
    """Leading legislative file number from an item title, or None.

    The remainder must carry a real word (bare numerics never link), and a
    year + valid MMDD shape ("2026-0615") is treated as a date, not a file.
    """
    m = _LEADING_FILE_RE.match(title or "")
    if not m:
        return None
    token = m.group(1)
    if not _WORD_RE.search((title or "")[m.end():]):
        return None
    first, _, second = token.partition("-")
    if len(first) == 4:
        # "2026-2027 Budget" / "2027-28 Work Plan" are fiscal-year ranges.
        if len(second) == 4 and second.startswith(("19", "20")):
            return None
        if len(second) == 2 and 0 < int(second) - int(first) % 100 <= 10:
            return None
        if len(second) == 4:
            mm, dd = int(second[:2]), int(second[2:])
            if 1 <= mm <= 12 and 1 <= dd <= 31:
                return None
    return token


def _is_bare_year(token: str) -> bool:
    return bool(re.fullmatch(r"(?:19|20)[0-9]{2}", token))


def extract_identifier(*texts: Optional[str]) -> Optional[Tuple[str, str]]:
    """Return (matter_file, matter_type) for the first labelled identifier found.

    Texts are searched as one document in the order given, so callers should pass
    the most authoritative source first (title before body).

    Amendment suffixes are preserved: 6006718-A1 is a distinct council action from
    6006718, and merging them would blur an award into its amendment under one
    canonical summary.
    """
    haystack = "\n".join(text for text in texts if text)
    if not haystack:
        return None

    title = texts[0] if texts else None
    body = "\n".join(text for text in texts[1:] if text)

    # Precedence, confidence 8/10: labelled durable handles anywhere in the text
    # (contract, file, case, petition) outrank instrument numbers, which
    # outrank unlabelled title codes. A resolution approving a contract keys on
    # the contract, since that is what recurs across committee, council and
    # amendment.
    for label, matter_type, pattern in _COMPILED:
        for match in pattern.finditer(haystack):
            # ``Master`` is a descriptor, not a stable action identity. Check
            # the actual whitespace before each match rather than encoding two
            # fixed-width lookbehinds: title/body text may contain tabs or
            # multiple spaces, and a false positive would merge every child
            # agreement beneath one umbrella matter.
            if label == "Contract" and re.search(
                r"master\s+$", haystack[:match.start()], re.IGNORECASE
            ):
                continue
            return f"{label} {match.group(1).upper()}", matter_type

    head = "\n".join(text for text in (title, body[:HEAD_CHARS]) if text)
    for label, matter_type, pattern in _HEAD_COMPILED:
        for match in pattern.finditer(head):
            if _is_bare_year(match.group(1)):
                continue
            if _CITATION_BEFORE_RE.search(head[max(0, match.start() - 40):match.start()]):
                continue
            return f"{label} {match.group(1).upper()}", matter_type

    leading = extract_leading_file_token(title)
    if leading:
        return leading, None
    for pattern in (_PAREN_CODE_RE, _DASH_CODE_RE):
        match = pattern.search(title or "")
        if match:
            return match.group(1), None

    return None
