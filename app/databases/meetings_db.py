import sqlite3
import logging
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
            
            # Insert meeting
            cursor.execute("""
                INSERT OR REPLACE INTO meetings 
                (city_slug, meeting_id, meeting_name, meeting_date, packet_url, last_accessed)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                city_slug,
                meeting_data.get('meeting_id'),
                meeting_data.get('meeting_name'),
                meeting_data.get('meeting_date'),
                meeting_data.get('packet_url')
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def store_meeting_summary(self, meeting_data: Dict[str, Any], summary: str, 
                            processing_time: float) -> int:
        """Store processed meeting summary"""
        city_slug = meeting_data.get('city_slug')
        logger.info(f"Storing meeting summary for {city_slug}: {len(summary)} chars, {processing_time:.2f}s")
        
        if not city_slug:
            raise ValueError("city_slug required in meeting_data")
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
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
                meeting_data.get('packet_url'),
                summary,
                processing_time
            ))
            
            conn.commit()
            return cursor.lastrowid
    
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
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_cached_summary(self, packet_url: str) -> Optional[Dict[str, Any]]:
        """Get cached meeting summary by packet URL"""
        logger.debug(f"Checking cache for packet: {packet_url}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT *
                FROM meetings
                WHERE packet_url = ? AND processed_summary IS NOT NULL
            """, (packet_url,))
            
            row = cursor.fetchone()
            if row:
                # Update last accessed
                cursor.execute("""
                    UPDATE meetings SET last_accessed = CURRENT_TIMESTAMP 
                    WHERE packet_url = ?
                """, (packet_url,))
                conn.commit()
                logger.debug(f"Cache hit for packet: {packet_url}")
                return dict(row)
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
            
            return [dict(row) for row in cursor.fetchall()]
    
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
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_meeting_by_packet_url(self, packet_url: str) -> Optional[Dict[str, Any]]:
        """Get meeting by packet URL"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT *
                FROM meetings
                WHERE packet_url = ?
            """, (packet_url,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
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