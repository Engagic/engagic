"""Adapter factory - get the right adapter for each vendor"""

import logging

from vendors.adapters.civicclerk_adapter import CivicClerkAdapter
from vendors.adapters.civicplus_adapter import CivicPlusAdapter
from vendors.adapters.granicus_adapter import GranicusAdapter
from vendors.adapters.iqm2_adapter import IQM2Adapter
from vendors.adapters.legistar_adapter import LegistarAdapter
from vendors.adapters.novusagenda_adapter import NovusAgendaAdapter
from vendors.adapters.primegov_adapter import PrimeGovAdapter

from vendors.adapters.custom.berkeley_adapter import BerkeleyAdapter
from vendors.adapters.custom.menlopark_adapter import MenloParkAdapter

logger = logging.getLogger("engagic")


def get_adapter(vendor: str, city_slug: str, **kwargs):
    """Get appropriate adapter for vendor

    Args:
        vendor: Vendor name (primegov, legistar, etc.) or custom city adapter (berkeley, menlopark)
        city_slug: Vendor-specific city identifier
        **kwargs: Additional adapter-specific arguments (e.g., api_token)

    Returns:
        Adapter instance or None if vendor not supported

    Custom city adapters (1:1, high value):
        - berkeley: Berkeley City Council (Drupal CMS)
        - menlopark: Menlo Park City Council (simple table)
    """
    supported_vendors = {
        "civicclerk",
        "civicplus",
        "granicus",
        "iqm2",
        "legistar",
        "novusagenda",
        "primegov",
        "berkeley",
        "menlopark",
    }

    if vendor not in supported_vendors:
        logger.debug(f"Unsupported vendor: {vendor} for city {city_slug}")
        return None

    if vendor == "civicclerk":
        return CivicClerkAdapter(city_slug)
    elif vendor == "civicplus":
        return CivicPlusAdapter(city_slug)
    elif vendor == "granicus":
        return GranicusAdapter(city_slug)
    elif vendor == "iqm2":
        return IQM2Adapter(city_slug)
    elif vendor == "legistar":
        # NYC requires API token
        api_token = kwargs.get("api_token")
        if api_token:
            return LegistarAdapter(city_slug, api_token=api_token)
        return LegistarAdapter(city_slug)
    elif vendor == "novusagenda":
        return NovusAgendaAdapter(city_slug)
    elif vendor == "primegov":
        return PrimeGovAdapter(city_slug)
    elif vendor == "berkeley":
        return BerkeleyAdapter(city_slug)
    elif vendor == "menlopark":
        return MenloParkAdapter(city_slug)
    else:
        return None
