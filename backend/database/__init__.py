"""
Engagic Database Module

Unified database architecture:
- UnifiedDatabase: Single database for all data (cities, meetings, analytics)
- City, Meeting: Data classes for type safety
- DatabaseManager: Alias to UnifiedDatabase for convenience
"""

from .unified_db import UnifiedDatabase, City, Meeting
from .database_manager import DatabaseManager

__all__ = [
    "UnifiedDatabase",
    "DatabaseManager",
    "City",
    "Meeting",
]
