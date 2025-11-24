"""Adapter factory - get the right adapter for each vendor"""

from config import get_logger
from exceptions import VendorError

# Sync adapters
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

# Async adapters
from vendors.adapters.granicus_adapter_async import AsyncGranicusAdapter
from vendors.adapters.iqm2_adapter_async import AsyncIQM2Adapter
from vendors.adapters.legistar_adapter_async import AsyncLegistarAdapter
from vendors.adapters.novusagenda_adapter_async import AsyncNovusAgendaAdapter
from vendors.adapters.primegov_adapter_async import AsyncPrimeGovAdapter

logger = get_logger(__name__).bind(component="vendor")

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

ASYNC_VENDOR_ADAPTERS = {
    "granicus": AsyncGranicusAdapter,
    "iqm2": AsyncIQM2Adapter,
    "legistar": AsyncLegistarAdapter,
    "novusagenda": AsyncNovusAgendaAdapter,
    "primegov": AsyncPrimeGovAdapter,
    # Remaining vendors use sync adapters (will be migrated in Priority 2/3)
    "civicclerk": CivicClerkAdapter,
    "civicplus": CivicPlusAdapter,
    "escribe": EscribeAdapter,
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
        Adapter instance

    Raises:
        VendorError: If vendor is not supported

    Custom city adapters (1:1, high value):
        - berkeley: Berkeley City Council (Drupal CMS)
        - menlopark: Menlo Park City Council (simple table)
    """
    if vendor not in VENDOR_ADAPTERS:
        raise VendorError(
            f"Unsupported vendor: {vendor}",
            vendor=vendor,
            city_slug=city_slug
        )

    adapter_cls = VENDOR_ADAPTERS[vendor]

    if vendor == "legistar" and kwargs.get("api_token"):
        return adapter_cls(city_slug, api_token=kwargs["api_token"])

    return adapter_cls(city_slug)


def get_async_adapter(vendor: str, city_slug: str, **kwargs):
    """Get appropriate async adapter for vendor

    Returns async adapters for migrated vendors (Legistar, PrimeGov, Granicus).
    Falls back to sync adapters for unmigrated vendors with a warning.

    Args:
        vendor: Vendor name (primegov, legistar, etc.) or custom city adapter (berkeley, menlopark)
        city_slug: Vendor-specific city identifier
        **kwargs: Additional adapter-specific arguments (e.g., api_token)

    Returns:
        Async adapter instance (or sync adapter if not yet migrated)

    Raises:
        VendorError: If vendor is not supported

    Migrated to async (Priority 1 complete):
        - legistar: Legistar API/HTML (async)
        - primegov: PrimeGov API/HTML (async)
        - granicus: Granicus HTML scraping (async)
        - iqm2: IQM2 HTML scraping (async)
        - novusagenda: NovusAgenda HTML scraping (async)

    Pending migration (Priority 2/3):
        - civicclerk, civicplus, escribe (monolithic adapters - may add item-level)
        - berkeley, chicago, menlopark (custom adapters)
    """
    if vendor not in ASYNC_VENDOR_ADAPTERS:
        raise VendorError(
            f"Unsupported vendor: {vendor}",
            vendor=vendor,
            city_slug=city_slug
        )

    adapter_cls = ASYNC_VENDOR_ADAPTERS[vendor]

    # Log if using sync fallback
    if vendor not in ["legistar", "primegov", "granicus", "iqm2", "novusagenda"]:
        logger.warning(
            "sync adapter fallback",
            vendor=vendor,
            city_slug=city_slug,
            reason="async migration pending"
        )

    # Handle Legistar api_token
    if vendor == "legistar" and kwargs.get("api_token"):
        return adapter_cls(city_slug, api_token=kwargs["api_token"])

    return adapter_cls(city_slug)
