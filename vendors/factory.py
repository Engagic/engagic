"""Adapter factory - get the right adapter for each vendor"""

from typing import Optional

from config import get_logger
from exceptions import VendorError
from pipeline.protocols import MetricsCollector

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

def get_async_adapter(
    vendor: str,
    city_slug: str,
    metrics: Optional[MetricsCollector] = None,
    **kwargs
):
    """Get async adapter for vendor. Raises VendorError if unsupported."""
    if vendor not in VENDOR_ADAPTERS:
        raise VendorError(
            f"Unsupported vendor: {vendor}",
            vendor=vendor,
            city_slug=city_slug
        )

    adapter_cls = VENDOR_ADAPTERS[vendor]

    # Handle Legistar api_token
    if vendor == "legistar" and kwargs.get("api_token"):
        return adapter_cls(city_slug, api_token=kwargs["api_token"], metrics=metrics)

    return adapter_cls(city_slug, metrics=metrics)
