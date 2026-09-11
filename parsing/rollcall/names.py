"""Name hygiene shared by attendance and vote-list parsing."""

import re
import unicodedata
from typing import List

# Honorifics and offices that precede a name in minutes. Kept generous on
# purpose: a stripped title never harms resolution, a retained one breaks it.
_TITLE_RE = re.compile(
    r"^\s*(?:"
    r"vice[- ]?chair(?:person|woman|man)?|chair(?:person|woman|man)?|"
    r"ald(?:\.|erman|erwoman|erperson)?|council\s*(?:member|man|woman|or|person)|"
    r"councilmember|councilor|commissioner|supervisor|trustee|director|"
    r"board\s+member|member|deputy\s+mayor|mayor\s+pro\s*[- ]?tem|mayor|"
    r"president\s+pro\s*[- ]?tem|president|selectman|selectwoman|selectperson|"
    r"representative|senator|judge|dr|mr|mrs|ms|miss|hon)\.?\s+",
    re.IGNORECASE,
)
_SUFFIX_RE = re.compile(r"\s*,?\s*(?:jr\.?|sr\.?|ii|iii|iv)\s*$", re.IGNORECASE)
_PARENS_RE = re.compile(r"\([^)]*\)")
_SPLIT_RE = re.compile(r"\s*(?:,|;|\band\b|&)\s*")


def fold(text: str) -> str:
    """Accent-insensitive lowercase key: 'Joaquín Baca' and 'Joaquin Baca' are one person."""
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    ).lower()


def looks_like_name(text: str) -> bool:
    words = text.split()
    return 1 <= len(words) <= 4 and not re.search(r"[\d:;/]", text)


def clean_name(raw: str) -> str:
    """Strip titles, parentheticals and trailing punctuation; collapse whitespace."""
    name = _PARENS_RE.sub("", raw)
    name = re.sub(r"\s+", " ", name).strip(" ,.;:-–")
    previous = None
    while previous != name:
        previous = name
        name = _TITLE_RE.sub("", name).strip(" ,.")
    return name


def split_names(blob: str) -> List[str]:
    """'Flynn, Gilmore, and Hinds' / 'Supervisor Tam; Supervisor Miley' -> names."""
    names = []
    for part in _SPLIT_RE.split(blob):
        cleaned = clean_name(part)
        if cleaned and looks_like_name(cleaned) and not re.fullmatch(r"(?:none|nil|n/a|-)", cleaned, re.I):
            names.append(cleaned)
    return names
