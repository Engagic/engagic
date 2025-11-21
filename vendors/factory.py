"""Adapter factory - get the right adapter for each vendor"""

import logging

from vendors.adapters.civicclerk_adapter import CivicClerkAdapter
from vendors.adapters.civicplus_adapter import CivicPlusAdapter
from vendors.adapters.escribe_adapter import EscribeAdapter
from vendors.adapters.granicus_adapter import GranicusAdapter
from vendors.adapters.iqm2_adapter import IQM2Adapter
from vendors.adapters.legistar_adapter import LegistarAdapter
from vendors.adapters.novusagenda_adapter import NovusAgendaAdapter
from vendors.adapters.primegov_adapter import PrimeGovAdapter

from vendors.adapters.custom.berkeley_adapter import BerkeleyAdapter
from vendors.adapters.custom.chicago_adapter import ChicagoAdapter
from vendors.adapters.custom.menlopark_adapter import MenloParkAdapter

logger = logging.getLogger("engagic")

VENDOR_ADAPTERS = {
    "civicclerk": CivicClerkAdapter,
    "civicplus": CivicPlusAdapter,
    "escribe": EscribeAdapter,
    "granicus": GranicusAdapter,
    "iqm2": IQM2Adapter,
    "legistar": LegistarAdapter,
    "novusagenda": NovusAgendaAdapter,
    "primegov": PrimeGovAdapter,
    "berkeley": BerkeleyAdapter,
    "chicago": ChicagoAdapter,
    "menlopark": MenloParkAdapter,
}


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
    if vendor not in VENDOR_ADAPTERS:
        logger.debug(f"Unsupported vendor: {vendor} for city {city_slug}")
        return None

    adapter_cls = VENDOR_ADAPTERS[vendor]

    if vendor == "legistar" and kwargs.get("api_token"):
        return adapter_cls(city_slug, api_token=kwargs["api_token"])

    return adapter_cls(city_slug)
