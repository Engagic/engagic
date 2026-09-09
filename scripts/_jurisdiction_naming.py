"""Shared naming helpers for jurisdiction bananas.

Used by db_viewer (interactive add) and boardbook_bulk_import (batch add).

The rule (2026-09-09): a banana is a simple, typeable, unambiguous
representation of the jurisdiction. The default is the name plus the state
code, which is as unique as it gets: "San Mateo" and "San Mateo County" are
two names people use, so sanmateoCA and sanmateocountyCA; "Prosper ISD" is
prosperisdTX. The contraction or vernacular is the fallback, used only when
name + state would be overloaded, overly convoluted, or out of line with
what locals actually say: Palo Alto Unified School District is "PAUSD" to
everyone who lives there (pausdCA), the Association of Bay Area Governments
is "ABAG" (abagCA). The caller supplies that vernacular.

What this replaces: a generator that stripped the district words people use
("Unified School District", "ISD") down to a bare stem and then bolted a
class code back on (sd/usd/csd/psd) to recover what it had thrown away.
That produced paloaltousdCA, manufactured collisions between distinct names,
and needed a disambiguation pass to undo itself. Jurisdiction type lives in
the `type` column; the banana does not encode it.

Bananas are the primary key and the only identity we rely on (never vendor
slugs, Census ids, or other external designations). Existing bananas are
frozen. This module only shapes new ones.
"""

import re
import unicodedata


def to_banana_slug(name: str) -> str:
    """ASCII-fold + strip non-alphanumeric. Diacritics survive as base letters
    (La Canada -> lacanada, not lacaada).
    """
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]", "", ascii_only).lower()


# Single-letter acronym dots: 'C.I.S.D.' -> 'CISD', 'I.S.D' -> 'ISD'.
# Some directory listings (BoardBook included) render district acronyms with
# periods. The slug would drop the dots anyway; this keeps the intermediate
# name readable for prompts and logs.
_ACRONYM_DOTS_RE = re.compile(r"\b((?:[A-Za-z]\.){2,})")

# Parenthetical disambiguator like "Wylie ISD (Collin County)" or
# "Rocksprings ISD (069901)". Alphabetic content is part of how the directory
# tells two same-named districts apart, so it stays in the banana with the
# filler words removed ('Collin County' -> 'collin'). Numeric content is a
# bookkeeping code (TEA ids) and is dropped.
_PAREN_RE = re.compile(r"\s*\(([^)]+)\)\s*")
_PAREN_QUALIFIER_NOISE_RE = re.compile(
    r"\b(county|parish|borough|district|isd|cisd|usd)\b", re.IGNORECASE
)

# MN/IL directory convention: "Independent School District [No.] NNN [town]".
# The leading legal form is bookkeeping; locals say "Eden Prairie Schools" or
# "ISD 748". Strip the prefix; if nothing but the number remains, the banana
# is isd<NNN>, which is what people say for those districts.
_NUMBERED_PREFIX_RE = re.compile(
    r"^(?:independent\s+school\s+district|school\s+district)"
    r"(?:\s+(?:no\.?|number|#))?\s*#?\s*(\d+(?:-\d+)?)\s*",
    re.IGNORECASE,
)


def _strip_acronym_dots(name: str) -> str:
    return _ACRONYM_DOTS_RE.sub(lambda m: m.group(1).replace(".", ""), name)


def _split_paren_tag(name: str) -> tuple[str, str]:
    """Return (name without the parenthetical, slug tag to append or '')."""
    match = _PAREN_RE.search(name)
    if not match:
        return name, ""
    inner = match.group(1)
    cleaned = (name[: match.start()] + name[match.end():]).strip()
    digit_count = sum(c.isdigit() for c in inner)
    if digit_count > len(inner) / 2:
        return cleaned, ""
    return cleaned, to_banana_slug(_PAREN_QUALIFIER_NOISE_RE.sub("", inner))


def vernacular_stem(name: str) -> str:
    """Slug of a jurisdiction name as written, minus directory bookkeeping.

    Examples:
      'San Mateo'                                             -> 'sanmateo'
      'San Mateo County'                                      -> 'sanmateocounty'
      'Prosper ISD'                                           -> 'prosperisd'
      'Los Angeles Unified School District'                   -> 'losangelesunifiedschooldistrict'
      'Wylie ISD (Collin County)'                             -> 'wylieisdcollin'
      'Rocksprings ISD (069901)'                              -> 'rockspringsisd'
      'Independent School District #272 Eden Prairie Schools' -> 'edenprairieschools'
      'Independent School District 748'                       -> 'isd748'
      'C.I.S.D. of Rice'                                      -> 'cisdofrice'
    """
    cleaned, paren_tag = _split_paren_tag(_strip_acronym_dots(name.strip()))
    numbered = _NUMBERED_PREFIX_RE.match(cleaned)
    if numbered:
        remainder = cleaned[numbered.end():].strip()
        cleaned = remainder or f"isd{numbered.group(1).replace('-', '')}"
    return to_banana_slug(cleaned) + paren_tag


def make_banana(name: str, state: str, vernacular: str | None = None) -> str:
    """Banana for a new jurisdiction: name + state by default.

    `vernacular` is the fallback for when name + state would be overloaded,
    convoluted, or not what people say ('Palo Alto Unified School District'
    -> 'PAUSD' -> pausdCA; 'Association of Bay Area Governments' -> abagCA).
    """
    state = state.strip().upper()
    if len(state) != 2:
        raise ValueError(f"state must be a 2-letter code, got {state!r}")
    stem = vernacular_stem(vernacular.strip()) if vernacular and vernacular.strip() else vernacular_stem(name)
    if not stem:
        raise ValueError(f"name {name!r} produced an empty banana stem")
    return stem + state


def find_banana_collisions(
    rows: list, *, banana_key: str = "banana"
) -> dict[str, list[int]]:
    """Map each banana claimed by more than one row to the row indices.

    With vernacular stems, two distinct names collide only when they differ
    by punctuation or spacing alone ('St. Louis Park' vs 'St Louis Park'),
    which almost always means one entity listed twice. Callers should hold
    both rows for review rather than invent a suffix.
    """
    by_banana: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        by_banana.setdefault(row[banana_key], []).append(index)
    return {banana: indices for banana, indices in by_banana.items() if len(indices) > 1}
