import re


def generate_city_banana(city_name: str, state: str) -> str:
    """
    Generate city_banana identifier from city name and state.

    Format: Strip all non-alphanumeric characters from city name,
    convert to lowercase, then append uppercase state code.

    Examples:
        "Palo Alto", "CA" -> "paloaltoCA"
        "St. Louis", "MO" -> "stlouisMO"
        "Winston-Salem", "NC" -> "winstonsalemNC"

    Args:
        city_name: The city name
        state: The state code (2 letters)

    Returns:
        The city_banana identifier
    """
    # Strip all non-alphanumeric characters and convert to lowercase
    city_clean = re.sub(r"[^a-zA-Z0-9]", "", city_name).lower()
    # Append uppercase state code
    return f"{city_clean}{state.upper()}"
