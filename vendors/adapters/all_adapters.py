"""
Consolidated adapter imports

Imports all city meeting adapters from their individual modules.
This file serves as the public API for the adapters package.

Usage:
    from vendors.adapters.all_adapters import PrimeGovAdapter, CivicClerkAdapter

Adapter Categories:
    API-Based (Clean, ~70-80 lines):
        - PrimeGovAdapter: JSON API
        - CivicClerkAdapter: OData API
        - LegistarAdapter: Legistar Web API (requires token for some cities)

    HTML Scraping (Complex, ~200-250 lines):
        - GranicusAdapter: HTML tables with view_id discovery
        - NovusAgendaAdapter: HTML table scraping
        - CivicPlusAdapter: Homepage scraping with external system detection
"""

from vendors.adapters.base_adapter import BaseAdapter
from vendors.adapters.primegov_adapter import PrimeGovAdapter
from vendors.adapters.civicclerk_adapter import CivicClerkAdapter
from vendors.adapters.granicus_adapter import GranicusAdapter
from vendors.adapters.legistar_adapter import LegistarAdapter
from vendors.adapters.novusagenda_adapter import NovusAgendaAdapter
from vendors.adapters.civicplus_adapter import CivicPlusAdapter
from vendors.adapters.escribe_adapter import EscribeAdapter

__all__ = [
    "BaseAdapter",
    "PrimeGovAdapter",
    "CivicClerkAdapter",
    "GranicusAdapter",
    "LegistarAdapter",
    "NovusAgendaAdapter",
    "CivicPlusAdapter",
    "EscribeAdapter",
]
