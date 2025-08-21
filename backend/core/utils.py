import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("engagic")


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
    if not city_name or not state:
        raise ValueError("Both city_name and state are required")
    
    # Remove any trailing state info from city_name if present
    city_clean = city_name.split(',')[0].strip()
    
    # Strip all non-alphanumeric characters and convert to lowercase
    city_part = re.sub(r"[^a-zA-Z0-9]", "", city_clean).lower()
    
    # State should be uppercase, alphanumeric only
    state_part = re.sub(r'[^a-zA-Z0-9]', '', state).upper()
    
    if not city_part or not state_part:
        raise ValueError(f"Invalid city_name '{city_name}' or state '{state}'")
    
    # Append uppercase state code
    return f"{city_part}{state_part}"


def standardize_city_identifiers(city_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure city data has proper identifiers according to system rules:
    - city_banana: For ALL internal operations (database keys, internal logic)
    - city_slug: ONLY for vendor API calls
    - city_name: ONLY for user-facing display
    
    Args:
        city_data: Dictionary with city information
        
    Returns:
        Dictionary with standardized identifiers
        
    Raises:
        ValueError: If required fields are missing or invalid
    """
    # TODO: Implement standardization logic that:
    # 1. Generates city_banana if missing using generate_city_banana()
    # 2. Validates city_slug exists for vendor operations
    # 3. Ensures city_name is properly formatted for display
    # 4. Adds validation to prevent duplicate city_bananas
    # 5. Handles edge cases (St. vs Saint, special characters, etc.)
    # Example implementation structure:
    # - Extract city_name and state from city_data
    # - Generate city_banana using generate_city_banana()
    # - Validate city_slug is present if vendor is specified
    # - Normalize city_name for consistent display
    # - Return updated dictionary with all three identifiers
    pass
