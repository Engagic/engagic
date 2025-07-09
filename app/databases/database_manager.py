import logging
from typing import Dict, Any, Optional, List
from .locations_db import LocationsDatabase
from .meetings_db import MeetingsDatabase
from .analytics_db import AnalyticsDatabase

logger = logging.getLogger("engagic")

class DatabaseManager:
    """Unified interface for all engagic databases"""
    
    def __init__(self, locations_db_path: str, meetings_db_path: str, analytics_db_path: str):
        self.locations = LocationsDatabase(locations_db_path)
        self.meetings = MeetingsDatabase(meetings_db_path)
        self.analytics = AnalyticsDatabase(analytics_db_path)
        
        logger.info("DatabaseManager initialized with separate databases")
    
    # === Locations Database Methods ===
    
    def add_city(self, city_name: str, state: str, city_slug: str, vendor: str, 
                 county: str = None, zipcodes: List[str] = None) -> int:
        """Add a new city with optional zipcodes"""
        return self.locations.add_city(city_name, state, city_slug, vendor, county, zipcodes)
    
    def get_city_by_zipcode(self, zipcode: str) -> Optional[Dict[str, Any]]:
        """Get city information by zipcode"""
        return self.locations.get_city_by_zipcode(zipcode)
    
    def get_city_by_name(self, city_name: str, state: str) -> Optional[Dict[str, Any]]:
        """Get city information by name and state"""
        return self.locations.get_city_by_name(city_name, state)
    
    def get_cities_by_name_only(self, city_name: str) -> List[Dict[str, Any]]:
        """Get all cities matching a name (regardless of state)"""
        return self.locations.get_cities_by_name_only(city_name)
    
    def get_city_by_slug(self, city_slug: str) -> Optional[Dict[str, Any]]:
        """Get city information by slug"""
        return self.locations.get_city_by_slug(city_slug)
    
    def get_all_cities(self) -> List[Dict[str, Any]]:
        """Get all cities with their zipcode information"""
        return self.locations.get_all_cities()
    
    def delete_city(self, city_slug: str) -> bool:
        """Delete a city and all associated data from both locations and meetings"""
        # Delete from locations database
        locations_success = self.locations.delete_city(city_slug)
        
        # Delete meetings for this city
        meetings_deleted = self._delete_meetings_by_city_slug(city_slug)
        
        if locations_success:
            logger.info(f"Deleted city {city_slug} and {meetings_deleted} associated meetings")
        
        return locations_success
    
    def delete_cities_without_vendor(self) -> int:
        """Delete all cities that don't have an associated vendor"""
        # Get cities without vendor first
        cities_to_delete = []
        for city in self.locations.get_all_cities():
            if not city.get('vendor'):
                cities_to_delete.append(city['city_slug'])
        
        # Delete from locations
        count = self.locations.delete_cities_without_vendor()
        
        # Delete associated meetings
        for city_slug in cities_to_delete:
            self._delete_meetings_by_city_slug(city_slug)
        
        return count
    
    def _delete_meetings_by_city_slug(self, city_slug: str) -> int:
        """Helper to delete all meetings for a city slug"""
        with self.meetings.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM meetings WHERE city_slug = ?", (city_slug,))
            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count
    
    # === Meetings Database Methods ===
    
    def store_meeting_data(self, meeting_data: Dict[str, Any]) -> int:
        """Store meeting data"""
        return self.meetings.store_meeting_data(meeting_data)
    
    def store_meeting_summary(self, meeting_data: Dict[str, Any], summary: str, 
                            processing_time: float) -> int:
        """Store processed meeting summary"""
        return self.meetings.store_meeting_summary(meeting_data, summary, processing_time)
    
    def get_meetings_by_city(self, city_slug: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get meetings for a city by slug"""
        return self.meetings.get_meetings_by_city(city_slug, limit)
    
    def get_cached_summary(self, packet_url: str) -> Optional[Dict[str, Any]]:
        """Get cached meeting summary by packet URL"""
        return self.meetings.get_cached_summary(packet_url)
    
    def get_recent_meetings(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get most recently accessed meetings across all cities"""
        return self.meetings.get_recent_meetings(limit)
    
    def get_unprocessed_meetings(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get meetings that don't have processed summaries yet"""
        return self.meetings.get_unprocessed_meetings(limit)
    
    def get_meeting_by_packet_url(self, packet_url: str) -> Optional[Dict[str, Any]]:
        """Get meeting by packet URL"""
        return self.meetings.get_meeting_by_packet_url(packet_url)
    
    def get_processing_queue_stats(self) -> Dict[str, Any]:
        """Get statistics about processing queue"""
        return self.meetings.get_processing_queue_stats()
    
    def delete_cached_summary(self, packet_url: str) -> bool:
        """Delete a cached summary for a specific packet URL"""
        return self.meetings.delete_cached_summary(packet_url)
    
    def cleanup_old_entries(self, days_old: int = 90) -> int:
        """Clean up old cache entries"""
        return self.meetings.cleanup_old_entries(days_old)
    
    # === Analytics Database Methods ===
    
    def log_search(self, search_query: str, search_type: str, city_slug: str = None, 
                  zipcode: str = None, topic_flags: List[str] = None):
        """Log search activity"""
        return self.analytics.log_search(search_query, search_type, city_slug, zipcode, topic_flags)
    
    def log_city_request(self, city_name: str, state: str, search_query: str, 
                        search_type: str, zipcode: str = None, user_ip: str = None) -> int:
        """Log a request for a missing city"""
        return self.analytics.log_city_request(city_name, state, search_query, search_type, zipcode, user_ip)
    
    def get_top_city_requests(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get most requested cities for admin review"""
        return self.analytics.get_top_city_requests(limit)
    
    def get_city_request_stats(self) -> Dict[str, Any]:
        """Get stats on city requests"""
        return self.analytics.get_city_request_stats()
    
    def update_daily_analytics(self, date: str = None) -> Dict[str, Any]:
        """Update daily search analytics"""
        return self.analytics.update_daily_analytics(date)
    
    def get_analytics_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get analytics summary for the last N days"""
        return self.analytics.get_analytics_summary(days)
    
    def cleanup_old_analytics(self, days_old: int = 365) -> int:
        """Clean up old analytics data"""
        return self.analytics.cleanup_old_analytics(days_old)
    
    # === Unified Methods ===
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics from all databases"""
        locations_stats = self.locations.get_db_stats()
        meetings_stats = self.meetings.get_meetings_stats()
        analytics_stats = self.analytics.get_db_stats()
        
        return {
            'cities_count': locations_stats['tables'].get('cities', 0),
            'zipcodes_count': locations_stats['tables'].get('zipcodes', 0),
            'meetings_count': meetings_stats.get('meetings_count', 0),
            'processed_count': meetings_stats.get('processed_count', 0),
            'recent_activity': meetings_stats.get('recent_activity', 0),
            'database_sizes': {
                'locations_kb': locations_stats['file_size_kb'],
                'meetings_kb': self.meetings.get_db_stats()['file_size_kb'],
                'analytics_kb': analytics_stats['file_size_kb']
            }
        }
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health from all databases"""
        try:
            locations_health = {"status": "healthy", "tables": len(self.locations.get_db_stats()['tables'])}
        except Exception as e:
            locations_health = {"status": "error", "error": str(e)}
        
        try:
            meetings_health = {"status": "healthy", "tables": len(self.meetings.get_db_stats()['tables'])}
        except Exception as e:
            meetings_health = {"status": "error", "error": str(e)}
        
        try:
            analytics_health = {"status": "healthy", "tables": len(self.analytics.get_db_stats()['tables'])}
        except Exception as e:
            analytics_health = {"status": "error", "error": str(e)}
        
        overall_status = "healthy"
        if any(db["status"] == "error" for db in [locations_health, meetings_health, analytics_health]):
            overall_status = "degraded"
        
        return {
            "overall_status": overall_status,
            "databases": {
                "locations": locations_health,
                "meetings": meetings_health,
                "analytics": analytics_health
            }
        }