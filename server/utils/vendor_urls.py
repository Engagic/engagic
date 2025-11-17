"""
Utility to construct vendor source URLs for attribution
"""

import json
import os
from typing import Optional


def get_vendor_source_url(vendor: str, slug: str) -> Optional[str]:
    """
    Construct the source URL for a city's meeting calendar based on vendor and slug.

    Args:
        vendor: Vendor name (legistar, primegov, granicus, etc.)
        slug: City-specific slug used by the vendor

    Returns:
        Full URL to the city's calendar page, or None if vendor unknown

    Example:
        get_vendor_source_url("legistar", "sfgov")
        -> "https://sfgov.legistar.com/Calendar.aspx"
    """
    vendor = vendor.lower().strip()

    # Special handling for Granicus - requires city-specific view_id
    if vendor == "granicus":
        return _get_granicus_url(slug)

    vendor_patterns = {
        "legistar": f"https://{slug}.legistar.com/Calendar.aspx",
        "primegov": f"https://{slug}.primegov.com/public/portal",
        "iqm2": f"https://{slug}.iqm2.com/Citizens/Calendar.aspx",
        "novusagenda": f"https://{slug}.novusagenda.com/agendapublic",
        "escribe": f"https://{slug}.escribemeetings.com",
        "civicclerk": f"https://{slug}.api.civicclerk.com",
        "civicplus": f"https://{slug}.civicplus.com",
        # Custom adapters
        "berkeley": "https://berkeleyca.gov/your-government/city-council/city-council-agendas",
        "menlopark": "https://menlopark.gov/Agendas-and-minutes",
        "fremont": "https://fremont.gov/AgendaCenter",
    }

    return vendor_patterns.get(vendor)


def _get_granicus_url(slug: str) -> Optional[str]:
    """
    Get Granicus URL with city-specific view_id from cache.

    Args:
        slug: Granicus city slug

    Returns:
        Full URL with view_id, or base URL if view_id not found
    """
    view_ids_file = "/root/engagic/data/granicus_view_ids.json"
    base_url = f"https://{slug}.granicus.com"

    # Try to load cached view_ids
    if os.path.exists(view_ids_file):
        try:
            with open(view_ids_file, "r") as f:
                mappings = json.load(f)
                view_id = mappings.get(base_url)
                if view_id:
                    return f"{base_url}/ViewPublisher.php?view_id={view_id}"
        except Exception:
            pass  # Fall through to default

    # Fallback: return base URL without view_id
    # (better than nothing, user can navigate from there)
    return f"{base_url}/ViewPublisher.php"


def get_vendor_display_name(vendor: str) -> str:
    """
    Get human-readable display name for vendor.

    Args:
        vendor: Vendor identifier

    Returns:
        Display name for the vendor
    """
    vendor = vendor.lower().strip()

    display_names = {
        "legistar": "Legistar",
        "primegov": "PrimeGov",
        "granicus": "Granicus",
        "iqm2": "iQM2",
        "novusagenda": "NovusAgenda",
        "escribe": "eScribe",
        "civicclerk": "CivicClerk",
        "civicplus": "CivicPlus",
        "berkeley": "City of Berkeley",
        "menlopark": "City of Menlo Park",
        "fremont": "City of Fremont",
    }

    return display_names.get(vendor, vendor.title())
