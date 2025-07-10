import sqlite3
import logging
import hashlib
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from .base_db import BaseDatabase

logger = logging.getLogger("engagic")

class MeetingsDatabase(BaseDatabase):
    """Database for meeting data and processing cache"""
    
    def _init_database(self):
        """Initialize the meetings database schema"""
        schema = """
        -- Meetings table - meeting data cache
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_slug TEXT NOT NULL,  -- Reference to city (no FK since it's in different DB)
            meeting_id TEXT,
            meeting_name TEXT,
            meeting_date DATETIME,
            packet_url TEXT NOT NULL,
            meeting_hash TEXT,  -- Hash of meeting details for change detection
            raw_packet_size INTEGER,
            processed_summary TEXT,
            processing_time_seconds REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(packet_url)
        );

        -- Processing cache table - LLM processing cache
        CREATE TABLE IF NOT EXISTS processing_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            packet_url TEXT NOT NULL UNIQUE,
            content_hash TEXT,
            raw_text_size INTEGER,
            cleaned_text_size INTEGER,
            summary_size INTEGER,
            processing_duration_seconds REAL,
            cache_hit_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Create indices for performance
        CREATE INDEX IF NOT EXISTS idx_meetings_city_slug ON meetings(city_slug);
        CREATE INDEX IF NOT EXISTS idx_meetings_packet_url ON meetings(packet_url);
        CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(meeting_date);
        CREATE INDEX IF NOT EXISTS idx_cache_url ON processing_cache(packet_url);
        CREATE INDEX IF NOT EXISTS idx_cache_hash ON processing_cache(content_hash);
        """
        self.execute_script(schema)
    
    def store_meeting_data(self, meeting_data: Dict[str, Any]) -> int:
        """Store meeting data"""
        city_slug = meeting_data.get('city_slug')
        logger.debug(f"Storing meeting data for {city_slug}: {meeting_data.get('meeting_name', 'Unknown')}")
        
        if not city_slug:
            raise ValueError("city_slug required in meeting_data")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Generate hash for change detection
            meeting_hash = self._generate_meeting_hash(meeting_data)
            
            # Serialize packet_url if it's a list
            packet_url = meeting_data.get('packet_url')
            if isinstance(packet_url, list):
                packet_url = json.dumps(packet_url)
            
            # Insert meeting
            cursor.execute("""
                INSERT OR REPLACE INTO meetings 
                (city_slug, meeting_id, meeting_name, meeting_date, packet_url, meeting_hash, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                city_slug,
                meeting_data.get('meeting_id'),
                meeting_data.get('meeting_name'),
                meeting_data.get('meeting_date'),
                packet_url,
                meeting_hash
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def _generate_meeting_hash(self, meeting_data: Dict[str, Any]) -> str:
        """Generate hash of meeting data for change detection"""
        # Use key meeting details for hash
        hash_data = {
            'meeting_id': meeting_data.get('meeting_id'),
            'meeting_name': meeting_data.get('meeting_name'),
            'meeting_date': meeting_data.get('meeting_date'),
            'packet_url': meeting_data.get('packet_url')
        }
        
        # Sort keys for consistent hashing
        hash_string = json.dumps(hash_data, sort_keys=True)
        return hashlib.md5(hash_string.encode()).hexdigest()
    
    def has_meeting_changed(self, meeting_data: Dict[str, Any]) -> bool:
        """Check if meeting data has changed since last sync"""
        packet_url = meeting_data.get('packet_url')
        if not packet_url:
            return True  # No URL means it's new
        
        new_hash = self._generate_meeting_hash(meeting_data)
        
        # Serialize packet_url if it's a list for DB lookup
        lookup_url = packet_url
        if isinstance(packet_url, list):
            lookup_url = json.dumps(packet_url)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT meeting_hash FROM meetings WHERE packet_url = ?",
                (lookup_url,)
            )
            
            result = cursor.fetchone()
            if not result:
                return True  # New meeting
            
            existing_hash = result[0]
            return existing_hash != new_hash  # Changed if hashes differ
    
    def get_city_meeting_frequency(self, city_slug: str, days: int = 30) -> int:
        """Get meeting count for a city in the last N days"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT COUNT(*) FROM meetings 
                   WHERE city_slug = ? 
                   AND created_at >= datetime('now', '-{} days')""".format(days),
                (city_slug,)
            )
            
            result = cursor.fetchone()
            return result[0] if result else 0
    
    def get_city_last_sync(self, city_slug: str) -> Optional[datetime]:
        """Get the last sync time for a city"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT MAX(created_at) FROM meetings 
                   WHERE city_slug = ?""",
                (city_slug,)
            )
            
            result = cursor.fetchone()
            if result and result[0]:
                return datetime.fromisoformat(result[0])
            return None
    
    def store_meeting_summary(self, meeting_data: Dict[str, Any], summary: str, 
                            processing_time: float) -> int:
        """Store processed meeting summary"""
        city_slug = meeting_data.get('city_slug')
        logger.info(f"Storing meeting summary for {city_slug}: {len(summary)} chars, {processing_time:.2f}s")
        
        if not city_slug:
            raise ValueError("city_slug required in meeting_data")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Serialize packet_url if it's a list
            packet_url = meeting_data.get('packet_url')
            if isinstance(packet_url, list):
                packet_url = json.dumps(packet_url)
            
            # Insert/update meeting with summary
            cursor.execute("""
                INSERT OR REPLACE INTO meetings 
                (city_slug, meeting_id, meeting_name, meeting_date, packet_url, 
                 processed_summary, processing_time_seconds, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                city_slug,
                meeting_data.get('meeting_id'),
                meeting_data.get('meeting_name'),
                meeting_data.get('meeting_date'),
                packet_url,
                summary,
                processing_time
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def _deserialize_packet_url(self, packet_url: str):
        """Deserialize packet_url if it's a JSON string"""
        if packet_url and packet_url.startswith('['):
            try:
                return json.loads(packet_url)
            except json.JSONDecodeError:
                return packet_url
        return packet_url
    
    def get_meetings_by_city(self, city_slug: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get meetings for a city by slug"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT *
                FROM meetings
                WHERE city_slug = ?
                ORDER BY meeting_date DESC, last_accessed DESC
                LIMIT ?
            """, (city_slug, limit))
            
            meetings = []
            for row in cursor.fetchall():
                meeting = dict(row)
                meeting['packet_url'] = self._deserialize_packet_url(meeting.get('packet_url'))
                meetings.append(meeting)
            return meetings
    
    def get_cached_summary(self, packet_url) -> Optional[Dict[str, Any]]:
        """Get cached meeting summary by packet URL"""
        logger.debug(f"Checking cache for packet: {packet_url}")
        
        # Serialize packet_url if it's a list for DB lookup
        lookup_url = packet_url
        if isinstance(packet_url, list):
            lookup_url = json.dumps(packet_url)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT *
                FROM meetings
                WHERE packet_url = ? AND processed_summary IS NOT NULL
            """, (lookup_url,))
            
            row = cursor.fetchone()
            if row:
                # Update last accessed
                cursor.execute("""
                    UPDATE meetings SET last_accessed = CURRENT_TIMESTAMP 
                    WHERE packet_url = ?
                """, (lookup_url,))
                conn.commit()
                logger.debug(f"Cache hit for packet: {packet_url}")
                meeting = dict(row)
                meeting['packet_url'] = self._deserialize_packet_url(meeting.get('packet_url'))
                return meeting
            logger.debug(f"Cache miss for packet: {packet_url}")
            return None
    
    def get_recent_meetings(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get most recently accessed meetings across all cities"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT *
                FROM meetings
                ORDER BY last_accessed DESC
                LIMIT ?
            """, (limit,))
            
            meetings = []
            for row in cursor.fetchall():
                meeting = dict(row)
                meeting['packet_url'] = self._deserialize_packet_url(meeting.get('packet_url'))
                meetings.append(meeting)
            return meetings
    
    def get_unprocessed_meetings(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get meetings that don't have processed summaries yet"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT *
                FROM meetings
                WHERE processed_summary IS NULL AND packet_url IS NOT NULL
                ORDER BY meeting_date ASC, created_at ASC
                LIMIT ?
            """, (limit,))
            
            meetings = []
            for row in cursor.fetchall():
                meeting = dict(row)
                meeting['packet_url'] = self._deserialize_packet_url(meeting.get('packet_url'))
                meetings.append(meeting)
            return meetings
    
    def get_meeting_by_packet_url(self, packet_url) -> Optional[Dict[str, Any]]:
        """Get meeting by packet URL"""
        # Serialize packet_url if it's a list for DB lookup
        lookup_url = packet_url
        if isinstance(packet_url, list):
            lookup_url = json.dumps(packet_url)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT *
                FROM meetings
                WHERE packet_url = ?
            """, (lookup_url,))
            
            row = cursor.fetchone()
            if row:
                meeting = dict(row)
                meeting['packet_url'] = self._deserialize_packet_url(meeting.get('packet_url'))
                return meeting
            return None
    
    def get_processing_queue_stats(self) -> Dict[str, Any]:
        """Get statistics about processing queue"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Total unprocessed
            cursor.execute("SELECT COUNT(*) as count FROM meetings WHERE processed_summary IS NULL AND packet_url IS NOT NULL")
            unprocessed_count = cursor.fetchone()['count']
            
            # Recently added (last 24 hours)
            cursor.execute("SELECT COUNT(*) as count FROM meetings WHERE created_at > datetime('now', '-1 day')")
            recent_count = cursor.fetchone()['count']
            
            # Processing success rate
            cursor.execute("SELECT COUNT(*) as count FROM meetings WHERE processed_summary IS NOT NULL")
            processed_count = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM meetings WHERE packet_url IS NOT NULL")
            total_with_urls = cursor.fetchone()['count']
            
            success_rate = (processed_count / total_with_urls * 100) if total_with_urls > 0 else 0
            
            return {
                'unprocessed_count': unprocessed_count,
                'processed_count': processed_count,
                'recent_count': recent_count,
                'success_rate': success_rate,
                'total_meetings': total_with_urls
            }
    
    def delete_cached_summary(self, packet_url: str) -> bool:
        """Delete a cached summary for a specific packet URL"""
        logger.info(f"Deleting cached summary for: {packet_url}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if summary exists
            cursor.execute("SELECT id FROM meetings WHERE packet_url = ?", (packet_url,))
            if not cursor.fetchone():
                logger.warning(f"No cached summary found for packet: {packet_url}")
                return False
            
            # Delete the meeting record
            cursor.execute("DELETE FROM meetings WHERE packet_url = ?", (packet_url,))
            
            # Also delete from processing_cache if it exists
            cursor.execute("DELETE FROM processing_cache WHERE packet_url = ?", (packet_url,))
            
            conn.commit()
            logger.info(f"Successfully deleted cached summary for: {packet_url}")
            return True
    
    def cleanup_old_entries(self, days_old: int = 90) -> int:
        """Clean up old cache entries"""
        logger.info(f"Cleaning up cache entries older than {days_old} days")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM meetings 
                WHERE last_accessed < datetime('now', '-{} days')
            """.format(days_old))
            deleted_count = cursor.rowcount
            conn.commit()
            logger.info(f"Cleaned up {deleted_count} old cache entries")
            return deleted_count
    
    def get_meetings_stats(self) -> Dict[str, Any]:
        """Get meetings database statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Meetings count
            cursor.execute("SELECT COUNT(*) as count FROM meetings")
            meetings_count = cursor.fetchone()['count']
            
            # Processed meetings count
            cursor.execute("SELECT COUNT(*) as count FROM meetings WHERE processed_summary IS NOT NULL")
            processed_count = cursor.fetchone()['count']
            
            # Recent activity
            cursor.execute("SELECT COUNT(*) as count FROM meetings WHERE last_accessed > datetime('now', '-7 days')")
            recent_activity = cursor.fetchone()['count']
            
            return {
                'meetings_count': meetings_count,
                'processed_count': processed_count,
                'recent_activity': recent_activity
            }