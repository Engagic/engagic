"""
Constants for server utilities

Single source of truth for state mappings, special city names, and entity types.
"""

# Entity types for engagement (watching)
# Users can watch matters, meetings, topics, cities, council members
WATCHABLE_ENTITY_TYPES = {"matter", "meeting", "topic", "city", "council_member"}

# Entity types for feedback (rating/reporting)
# Users can rate or report issues on items, meetings, matters
RATABLE_ENTITY_TYPES = {"item", "meeting", "matter"}

# Issue types for reports
VALID_ISSUE_TYPES = {"inaccurate", "incomplete", "misleading", "offensive", "other"}

# State name to abbreviation mapping
STATE_MAP = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}

# Reverse mapping for state abbreviations to full names
STATE_ABBREV_TO_FULL = {abbrev: name.title() for name, abbrev in STATE_MAP.items()}

# Special city names that need custom formatting
SPECIAL_CITIES = {
    "lasvegas": "Las Vegas",
    "newyork": "New York",
    "losangeles": "Los Angeles",
    "sanfrancisco": "San Francisco",
    "sanjose": "San Jose",
    "sandiego": "San Diego",
    "santaana": "Santa Ana",
    "santabarbara": "Santa Barbara",
    "santaclara": "Santa Clara",
    "santacruz": "Santa Cruz",
    "santamonica": "Santa Monica",
    "santarosa": "Santa Rosa",
    "paloalto": "Palo Alto",
    "mountainview": "Mountain View",
    "redwoodcity": "Redwood City",
    "halfmoonbay": "Half Moon Bay",
    "unioncity": "Union City",
    "fostercity": "Foster City",
    "dalycity": "Daly City",
    "elcerrito": "El Cerrito",
    "elpaso": "El Paso",
    "lacosta": "La Costa",
    "lamesa": "La Mesa",
    "stlouis": "St. Louis",
    "stpaul": "St. Paul",
    "stpetersburg": "St. Petersburg",
    "ftworth": "Fort Worth",
    "fortworth": "Fort Worth",
    "ftlauderdale": "Fort Lauderdale",
    "fortlauderdale": "Fort Lauderdale",
}
