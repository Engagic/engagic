"""
Engagic Database Module

Unified database architecture:
- UnifiedDatabase: Single database for all data (cities, meetings, analytics)
- City, Meeting: Data classes for type safety
"""

from .unified_db import UnifiedDatabase, City, Meeting

__all__ = [
    "UnifiedDatabase",
    "City",
    "Meeting",
]
