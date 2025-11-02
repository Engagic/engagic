"""
Constants for server utilities

Single source of truth for state mappings and special city names
"""

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
    "stlouis": "St. Louis",
    "stpaul": "St. Paul",
    "ftworth": "Fort Worth",
    "fortworth": "Fort Worth",
}
