"""
DEPRECATED: This module is deprecated and should not be used.

The adapter architecture has migrated to async/await patterns with a factory-based
routing system that handles both async and sync adapters.

For async adapters (recommended), use:
    from vendors.factory import get_async_adapter
    adapter = get_async_adapter("primegov", "paloalto")

For sync adapters (legacy fallback), use:
    from vendors.factory import get_adapter
    adapter = get_adapter("primegov", "paloalto")

Direct imports are discouraged because:
1. No automatic async/sync fallback handling
2. No vendor-specific routing logic
3. No centralized adapter configuration

This file is kept for backward compatibility only and provides no functionality.
All adapter usage should go through the factory pattern.

Async adapters available:
- AsyncLegistarAdapter (via get_async_adapter("legistar", slug))
- AsyncPrimeGovAdapter (via get_async_adapter("primegov", slug))
- AsyncGranicusAdapter (via get_async_adapter("granicus", slug))

Sync adapters (legacy, 8 vendors still unmigrated):
- IQM2Adapter, NovusAgendaAdapter, CivicClerkAdapter, CivicPlusAdapter,
  EscribeAdapter, BerkeleyAdapter, ChicagoAdapter, MenloParkAdapter
"""

# This module intentionally provides no exports
# Use vendors.factory.get_async_adapter() or vendors.factory.get_adapter() instead
__all__ = []
