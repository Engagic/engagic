"""
Engagic Database Module - Phase 1 Refactor

New unified database architecture:
- UnifiedDatabase: Single database for all data (cities, meetings, tenants)
- City, Meeting: Data classes for type safety

Legacy (will be removed in Phase 2):
- LocationsDatabase, MeetingsDatabase, AnalyticsDatabase: Old 3-DB system
- DatabaseManager: Backwards-compatible wrapper
"""

from .base_db import BaseDatabase
from .locations_db import LocationsDatabase
from .meetings_db import MeetingsDatabase
from .analytics_db import AnalyticsDatabase
from .database_manager import DatabaseManager

# New unified database (Phase 1)
from .unified_db import UnifiedDatabase, City, Meeting

__all__ = [
    # New unified architecture
    "UnifiedDatabase",
    "City",
    "Meeting",

    # Backwards-compatible wrapper
    "DatabaseManager",

    # Legacy (to be removed in Phase 2)
    "BaseDatabase",
    "LocationsDatabase",
    "MeetingsDatabase",
    "AnalyticsDatabase",
]
