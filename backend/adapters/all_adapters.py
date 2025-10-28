"""
Consolidated adapter imports

Imports all city meeting adapters from their individual modules.
This file serves as the public API for the adapters package.

Usage:
    from backend.adapters.all_adapters import PrimeGovAdapter, CivicClerkAdapter

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

from backend.adapters.base_adapter import BaseAdapter
from backend.adapters.primegov_adapter import PrimeGovAdapter
from backend.adapters.civicclerk_adapter import CivicClerkAdapter
from backend.adapters.granicus_adapter import GranicusAdapter
from backend.adapters.legistar_adapter import LegistarAdapter
from backend.adapters.novusagenda_adapter import NovusAgendaAdapter
from backend.adapters.civicplus_adapter import CivicPlusAdapter
from backend.adapters.escribe_adapter import EscribeAdapter

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
