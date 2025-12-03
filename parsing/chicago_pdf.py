"""Chicago PDF agenda parser

Parses Chicago City Council PDF agendas to extract record numbers and item hints.

PDF structure (from sample):
```
1. (O2025-0019668) Amendment of ordinance passed on November 7, 2023 regarding
   acquisition of property at 11414 S Halsted St from Albertsons LLC...
   (Introduced by Alderman Mosley)
2. (O2025-0018827) Amendment of Municipal Code Sections 2-44-080...
```

Pattern:
- Record numbers: (O2025-0019668), (R2025-0001234), (SO2025-0001234), etc.
- Format: Letter(s) + 4-digit year + hyphen + 7-digit sequence
- Items often numbered: "1.", "2.", etc.
- Titles span multiple lines until next item or section

Confidence: 8/10 - Record number format is consistent across Chicago agendas
"""

import re
from typing import Dict, Any


# Record number pattern: (O2025-0019668), (R2025-0001234), (SO2025-1234567)
# Letter prefix varies: O (Ordinance), R (Resolution), SO (Substitute Ordinance), etc.
RECORD_PATTERN = re.compile(r'\(([A-Z]{1,3}\d{4}-\d{7})\)')

# Numbered item pattern: "1.", "2.", "3." at line start
NUMBERED_ITEM_PATTERN = re.compile(r'^\s*(\d+)\.\s*', re.MULTILINE)


def parse_chicago_agenda_pdf(pdf_text: str) -> Dict[str, Any]:
    """
    Parse Chicago PDF agenda to extract record numbers.

    Args:
        pdf_text: Full text extracted from PDF

    Returns:
        {
            'items': [
                {
                    'record_number': 'O2025-0019668',
                    'sequence': 1,
                    'title_hint': 'Amendment of ordinance...'
                }
            ]
        }
    """
    items = []
    seen_records = set()

    # Find all record numbers with their positions
    for match in RECORD_PATTERN.finditer(pdf_text):
        record_number = match.group(1)

        # Skip duplicates (same record may appear multiple times)
        if record_number in seen_records:
            continue
        seen_records.add(record_number)

        # Look for numbered prefix before record number (e.g., "1. (O2025-...")
        # Search in the 50 chars before the match
        prefix_start = max(0, match.start() - 50)
        prefix_text = pdf_text[prefix_start:match.start()]

        # Find last number in prefix (e.g., "1." in "...some text\n1. ")
        sequence = len(items) + 1  # Default: order of appearance
        num_matches = list(re.finditer(r'(\d+)\.\s*$', prefix_text))
        if num_matches:
            sequence = int(num_matches[-1].group(1))

        # Extract title hint: text after record number until newline or next pattern
        title_start = match.end()
        title_end = title_start + 200  # Limit search
        title_text = pdf_text[title_start:min(title_end, len(pdf_text))]

        # Clean title: take until we hit another record number or section header
        title_hint = _extract_title_hint(title_text)

        items.append({
            'record_number': record_number,
            'sequence': sequence,
            'title_hint': title_hint,
        })

    # Sort by sequence for consistent ordering
    items.sort(key=lambda x: x['sequence'])

    return {'items': items}


def _extract_title_hint(text: str) -> str:
    """
    Extract a clean title hint from text following a record number.

    Stops at:
    - Another record number pattern
    - Section headers (e.g., "Department of Housing")
    - Parenthetical notes like "(City-Wide)", "(Introduced by...)"
    - Excessive whitespace/newlines

    Confidence: 7/10 - Title extraction is heuristic
    """
    # Stop at next record number
    next_record = RECORD_PATTERN.search(text)
    if next_record:
        text = text[:next_record.start()]

    # Stop at parenthetical notes
    paren_stop = re.search(r'\n\s*\((?:City-Wide|Introduced|Ward|Direct)', text, re.IGNORECASE)
    if paren_stop:
        text = text[:paren_stop.start()]

    # Stop at section headers (line starting with caps word)
    section_stop = re.search(r'\n[A-Z][a-z]+ (?:of|and) [A-Z]', text)
    if section_stop:
        text = text[:section_stop.start()]

    # Clean up
    title = ' '.join(text.split())  # Normalize whitespace
    title = title.strip(' .')

    # Truncate if too long
    if len(title) > 300:
        title = title[:297] + '...'

    return title
