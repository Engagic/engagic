"""
Geographic utilities for city and state handling
"""

from server.utils.constants import STATE_MAP, STATE_ABBREV_TO_FULL, SPECIAL_CITIES


def normalize_city_name(city_name: str) -> str:
    """Normalize city name for consistent formatting"""
    city = city_name.strip()

    city_lower_nospace = city.lower().replace(" ", "").replace(".", "")
    if city_lower_nospace in SPECIAL_CITIES:
        return SPECIAL_CITIES[city_lower_nospace]

    return city.title()


def parse_city_state_input(input_str: str) -> tuple[str, str]:
    """Parse city, state from user input

    Handles formats like:
    - "Palo Alto, CA"
    - "Palo Alto, California"
    - "Boston Massachusetts"
    - "New York NY"
    - "lasvegas nevada" (normalizes to "Las Vegas, NV")

    Returns: (city_name, state_abbreviation)
    """
    input_str = input_str.strip()

    # Try comma-separated format first: "City, State"
    if "," in input_str:
        parts = [p.strip() for p in input_str.split(",")]
        if len(parts) == 2:
            city, state = parts
            state_lower = state.lower()

            # Check if it's already an abbreviation
            if len(state) == 2 and state.upper() in STATE_MAP.values():
                return normalize_city_name(city), state.upper()
            # Check if it's a full state name
            elif state_lower in STATE_MAP:
                return normalize_city_name(city), STATE_MAP[state_lower]

    # Try space-separated format: "City State" or "City Full State Name"
    words = input_str.split()
    if len(words) >= 2:
        # Try last word as state abbreviation
        last_word = words[-1].lower()
        if len(last_word) == 2 and last_word.upper() in STATE_MAP.values():
            city = " ".join(words[:-1]).strip()
            return normalize_city_name(city), last_word.upper()

        # Try last 1-2 words as full state name
        for num_state_words in [2, 1]:
            if len(words) > num_state_words:
                potential_state = " ".join(words[-num_state_words:]).lower()
                if potential_state in STATE_MAP:
                    city = " ".join(words[:-num_state_words]).strip()
                    return normalize_city_name(city), STATE_MAP[potential_state]

    # No state found
    return input_str, ""


def is_state_query(query: str) -> bool:
    """Check if the query is just a state name or abbreviation"""
    query_lower = query.strip().lower()

    # Check if it's a full state name
    if query_lower in STATE_MAP:
        return True

    # Check if it's a state abbreviation
    if len(query) == 2 and query.upper() in STATE_MAP.values():
        return True

    return False


def get_state_abbreviation(state_input: str) -> str:
    """Convert state input to abbreviation

    Args:
        state_input: State name or abbreviation

    Returns:
        State abbreviation (e.g., "CA") or empty string if invalid
    """
    state_lower = state_input.strip().lower()

    if state_lower in STATE_MAP:
        return STATE_MAP[state_lower]
    elif len(state_input) == 2 and state_input.upper() in STATE_MAP.values():
        return state_input.upper()

    return ""


def get_state_full_name(state_input: str) -> str:
    """Convert state input to full name

    Args:
        state_input: State name or abbreviation

    Returns:
        State full name (e.g., "California") or empty string if invalid
    """
    state_lower = state_input.strip().lower()

    if state_lower in STATE_MAP:
        return " ".join(word.capitalize() for word in state_lower.split())
    elif len(state_input) == 2 and state_input.upper() in STATE_ABBREV_TO_FULL:
        return STATE_ABBREV_TO_FULL[state_input.upper()]

    return ""
