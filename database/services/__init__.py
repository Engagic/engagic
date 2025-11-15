"""
Database Services

Business logic layer extracted from facade for better separation of concerns.
"""

from database.services.meeting_ingestion import MeetingIngestionService

__all__ = ['MeetingIngestionService']
