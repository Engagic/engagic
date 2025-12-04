"""Adapter factory - get the right adapter for each vendor"""

from config import get_logger
from exceptions import VendorError

# Async adapters (primary - all vendors now migrated)
from vendors.adapters.granicus_adapter_async import AsyncGranicusAdapter
from vendors.adapters.iqm2_adapter_async import AsyncIQM2Adapter
from vendors.adapters.legistar_adapter_async import AsyncLegistarAdapter
from vendors.adapters.novusagenda_adapter_async import AsyncNovusAgendaAdapter
from vendors.adapters.primegov_adapter_async import AsyncPrimeGovAdapter
from vendors.adapters.civicclerk_adapter_async import AsyncCivicClerkAdapter
from vendors.adapters.civicplus_adapter_async import AsyncCivicPlusAdapter
from vendors.adapters.escribe_adapter_async import AsyncEscribeAdapter
from vendors.adapters.custom.berkeley_adapter_async import AsyncBerkeleyAdapter
from vendors.adapters.custom.chicago_adapter_async import AsyncChicagoAdapter
from vendors.adapters.custom.menlopark_adapter_async import AsyncMenloParkAdapter

logger = get_logger(__name__).bind(component="vendor")

# VENDOR_ADAPTERS: All async now (migration complete Nov 2025)
VENDOR_ADAPTERS = {
    "granicus": AsyncGranicusAdapter,
    "iqm2": AsyncIQM2Adapter,
    "legistar": AsyncLegistarAdapter,
    "novusagenda": AsyncNovusAgendaAdapter,
    "primegov": AsyncPrimeGovAdapter,
    "civicclerk": AsyncCivicClerkAdapter,
    "civicplus": AsyncCivicPlusAdapter,
    "escribe": AsyncEscribeAdapter,
    "berkeley": AsyncBerkeleyAdapter,
    "chicago": AsyncChicagoAdapter,
    "menlopark": AsyncMenloParkAdapter,
}

# ASYNC_VENDOR_ADAPTERS: Same as VENDOR_ADAPTERS (all async now)
ASYNC_VENDOR_ADAPTERS = VENDOR_ADAPTERS


def get_async_adapter(vendor: str, city_slug: str, **kwargs):
    """Get appropriate async adapter for vendor

    All vendors now use async adapters (migration complete Nov 2025).

    Args:
        vendor: Vendor name (primegov, legistar, etc.) or custom city adapter (berkeley, menlopark)
        city_slug: Vendor-specific city identifier
        **kwargs: Additional adapter-specific arguments (e.g., api_token)

    Returns:
        Async adapter instance

    Raises:
        VendorError: If vendor is not supported

    Supported vendors (all async):
        - legistar: Legistar API/HTML
        - primegov: PrimeGov API/HTML
        - granicus: Granicus HTML scraping
        - iqm2: IQM2 HTML scraping
        - novusagenda: NovusAgenda HTML scraping
        - civicclerk: CivicClerk OData API
        - civicplus: CivicPlus HTML scraping
        - escribe: Escribe HTML scraping
        - berkeley: Berkeley Drupal CMS
        - chicago: Chicago REST API
        - menlopark: Menlo Park PDF extraction
    """
    if vendor not in ASYNC_VENDOR_ADAPTERS:
        raise VendorError(
            f"Unsupported vendor: {vendor}",
            vendor=vendor,
            city_slug=city_slug
        )

    adapter_cls = ASYNC_VENDOR_ADAPTERS[vendor]

    # Handle Legistar api_token
    if vendor == "legistar" and kwargs.get("api_token"):
        return adapter_cls(city_slug, api_token=kwargs["api_token"])

    return adapter_cls(city_slug)
