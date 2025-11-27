"""
Custom city adapters - One-off high-value cities without vendor platforms

These adapters are 1:1 with specific cities. Each city has unique HTML structure
and requires custom parsing logic. Unlike vendor adapters (1:many), these don't scale.

Trade-off: High maintenance cost per city, but captures high-value targets
(Berkeley, Menlo Park, etc) that wouldn't otherwise be accessible.

Pattern:
- Inherit from AsyncBaseAdapter
- Implement async fetch_meetings()
- Register in factory.py with vendor="custom_{city}"
- Document URL patterns and HTML structure in adapter docstring

All custom adapters are async (migration complete Nov 2025).
"""

from vendors.adapters.custom.berkeley_adapter_async import AsyncBerkeleyAdapter
from vendors.adapters.custom.chicago_adapter_async import AsyncChicagoAdapter
from vendors.adapters.custom.menlopark_adapter_async import AsyncMenloParkAdapter

__all__ = ["AsyncBerkeleyAdapter", "AsyncChicagoAdapter", "AsyncMenloParkAdapter"]
