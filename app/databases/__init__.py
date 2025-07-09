"""
Engagic Database Module

Provides separate databases for different domains:
- LocationsDatabase: Cities, states, zipcodes
- MeetingsDatabase: Meeting data and processing cache
- AnalyticsDatabase: Usage metrics and demand tracking
"""

from .base_db import BaseDatabase
from .locations_db import LocationsDatabase
from .meetings_db import MeetingsDatabase
from .analytics_db import AnalyticsDatabase
from .database_manager import DatabaseManager

__all__ = [
    'BaseDatabase',
    'LocationsDatabase', 
    'MeetingsDatabase',
    'AnalyticsDatabase',
    'DatabaseManager'
]