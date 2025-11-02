"""
Custom city adapters - One-off high-value cities without vendor platforms

These adapters are 1:1 with specific cities. Each city has unique HTML structure
and requires custom parsing logic. Unlike vendor adapters (1:many), these don't scale.

Trade-off: High maintenance cost per city, but captures high-value targets
(Berkeley, Menlo Park, etc) that wouldn't otherwise be accessible.

Pattern:
- Inherit from BaseAdapter
- Implement fetch_meetings()
- Register in factory.py with vendor="custom_{city}"
- Document URL patterns and HTML structure in adapter docstring
"""

from vendors.adapters.custom.berkeley_adapter import BerkeleyAdapter
from vendors.adapters.custom.menlopark_adapter import MenloParkAdapter

__all__ = ["BerkeleyAdapter", "MenloParkAdapter"]
