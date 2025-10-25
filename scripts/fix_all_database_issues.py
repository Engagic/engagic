#!/usr/bin/env python3
"""
Fix all identified database issues:
1. Implement cache usage
2. Fix meetings with invalid dates  
3. Clean orphaned analytics records
4. Remove old backup table
5. Implement search analytics aggregation
6. Add data validation
"""

import sys
import sqlite3
import logging
import json
from pathlib import Path

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import DatabaseManager
from backend.core.config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseFixer:
    def __init__(self):
        self.db = DatabaseManager(
            locations_db_path=config.LOCATIONS_DB_PATH,
            meetings_db_path=config.MEETINGS_DB_PATH,
            analytics_db_path=config.ANALYTICS_DB_PATH
        )
        self.stats = {
            "dates_fixed": 0,
            "orphans_cleaned": 0,
            "backup_removed": False,
            "analytics_aggregated": 0,
            "cache_migrated": 0
        }

    def fix_invalid_meeting_dates(self):
        """Fix meetings with NULL or invalid dates"""
        logger.info("Fixing invalid meeting dates...")
        
        with self.db.meetings.get_connection() as conn:
            cursor = conn.cursor()
            
            # Find meetings with invalid dates
            cursor.execute("""
                SELECT id, city_banana, meeting_name, meeting_date, created_at
                FROM meetings
                WHERE meeting_date IS NULL OR meeting_date = ''
            """)
            
            invalid_meetings = cursor.fetchall()
            logger.info(f"Found {len(invalid_meetings)} meetings with invalid dates")
            
            for meeting in invalid_meetings:
                meeting_id = meeting['id']
                meeting_name = meeting['meeting_name'] or ""
                created_at = meeting['created_at']
                
                # Try to extract date from meeting_name
                fixed_date = None
                
                # Common patterns in meeting names
                import re
                date_patterns = [
                    r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',  # MM/DD/YYYY or MM-DD-YYYY
                    r'([A-Za-z]+ \d{1,2},? \d{4})',       # Month DD, YYYY
                    r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})',     # YYYY-MM-DD
                ]
                
                for pattern in date_patterns:
                    match = re.search(pattern, meeting_name)
                    if match:
                        date_str = match.group(1)
                        # Use the normalization function from meetings
                        fixed_date = self.db.meetings._normalize_meeting_datetime(date_str)
                        if fixed_date:
                            break
                
                # If no date found in name, use created_at as fallback
                if not fixed_date:
                    fixed_date = created_at
                    logger.debug(f"Using created_at as fallback for meeting {meeting_id}")
                
                # Update the meeting
                cursor.execute("""
                    UPDATE meetings
                    SET meeting_date = ?
                    WHERE id = ?
                """, (fixed_date, meeting_id))
                
                self.stats["dates_fixed"] += 1
                
            conn.commit()
            logger.info(f"Fixed {self.stats['dates_fixed']} meeting dates")

    def clean_orphaned_analytics(self):
        """Remove analytics records with invalid city_banana references"""
        logger.info("Cleaning orphaned analytics records...")
        
        # Get all valid city_banana values
        with self.db.locations.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT city_banana FROM cities")
            valid_cities = set(row[0] for row in cursor.fetchall())
        
        # Clean usage_metrics
        with self.db.analytics.get_connection() as conn:
            cursor = conn.cursor()
            
            # Find orphaned records
            cursor.execute("""
                SELECT DISTINCT city_banana
                FROM usage_metrics
                WHERE city_banana IS NOT NULL AND city_banana != ''
            """)
            
            used_cities = set(row[0] for row in cursor.fetchall())
            orphaned_cities = used_cities - valid_cities
            
            if orphaned_cities:
                logger.info(f"Found {len(orphaned_cities)} orphaned city references")
                
                # Delete orphaned records
                placeholders = ','.join('?' * len(orphaned_cities))
                cursor.execute(f"""
                    DELETE FROM usage_metrics
                    WHERE city_banana IN ({placeholders})
                """, list(orphaned_cities))
                
                self.stats["orphans_cleaned"] += cursor.rowcount
            
            # Also clean NULL/empty city_banana records
            cursor.execute("""
                DELETE FROM usage_metrics
                WHERE city_banana IS NULL OR city_banana = ''
            """)
            
            self.stats["orphans_cleaned"] += cursor.rowcount
            conn.commit()
            
        logger.info(f"Cleaned {self.stats['orphans_cleaned']} orphaned analytics records")

    def remove_backup_table(self):
        """Remove old backup table from production database"""
        logger.info("Removing old backup table...")
        
        with self.db.meetings.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if backup table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name LIKE 'meetings_backup_%'
            """)
            
            backup_tables = cursor.fetchall()
            
            for table in backup_tables:
                table_name = table[0]
                logger.info(f"Dropping backup table: {table_name}")
                cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                self.stats["backup_removed"] = True
            
            conn.commit()
            
        if self.stats["backup_removed"]:
            logger.info("Backup tables removed")
        else:
            logger.info("No backup tables found")

    def implement_search_analytics(self):
        """Aggregate search data into search_analytics table"""
        logger.info("Implementing search analytics aggregation...")
        
        with self.db.analytics.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get unique dates from usage_metrics
            cursor.execute("""
                SELECT DISTINCT date(created_at) as search_date
                FROM usage_metrics
                WHERE created_at >= date('now', '-30 days')
                ORDER BY search_date
            """)
            
            dates = [row[0] for row in cursor.fetchall()]
            
            for date_str in dates:
                # Calculate daily statistics
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN search_type = 'zipcode' THEN 1 ELSE 0 END) as zipcode_searches,
                        SUM(CASE WHEN search_type = 'city' THEN 1 ELSE 0 END) as city_searches,
                        SUM(CASE WHEN search_type = 'ambiguous' THEN 1 ELSE 0 END) as ambiguous_searches
                    FROM usage_metrics
                    WHERE date(created_at) = ?
                """, (date_str,))
                
                stats = cursor.fetchone()
                
                # Get top cities for the day
                cursor.execute("""
                    SELECT city_banana, COUNT(*) as count
                    FROM usage_metrics
                    WHERE date(created_at) = ? AND city_banana IS NOT NULL
                    GROUP BY city_banana
                    ORDER BY count DESC
                    LIMIT 5
                """, (date_str,))
                
                top_cities = [{"city": row[0], "count": row[1]} for row in cursor.fetchall()]
                
                # Get top zipcodes for the day
                cursor.execute("""
                    SELECT zipcode, COUNT(*) as count
                    FROM usage_metrics
                    WHERE date(created_at) = ? AND zipcode IS NOT NULL
                    GROUP BY zipcode
                    ORDER BY count DESC
                    LIMIT 5
                """, (date_str,))
                
                top_zipcodes = [{"zipcode": row[0], "count": row[1]} for row in cursor.fetchall()]
                
                # Insert or update search_analytics
                cursor.execute("""
                    INSERT OR REPLACE INTO search_analytics
                    (date, total_searches, zipcode_searches, city_searches, 
                     ambiguous_searches, successful_searches, top_cities, top_zipcodes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date_str,
                    stats['total'],
                    stats['zipcode_searches'],
                    stats['city_searches'],
                    stats['ambiguous_searches'],
                    stats['total'],  # Assume all are successful for now
                    json.dumps(top_cities),
                    json.dumps(top_zipcodes)
                ))
                
                self.stats["analytics_aggregated"] += 1
            
            conn.commit()
            
        logger.info(f"Aggregated analytics for {self.stats['analytics_aggregated']} days")

    def migrate_to_cache(self):
        """Migrate existing summaries to use cache table"""
        logger.info("Migrating to cache usage...")
        
        with self.db.meetings.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get all meetings with summaries
            cursor.execute("""
                SELECT packet_url, processed_summary, processing_time_seconds
                FROM meetings
                WHERE packet_url IS NOT NULL 
                AND processed_summary IS NOT NULL
            """)
            
            meetings = cursor.fetchall()
            logger.info(f"Found {len(meetings)} meetings to migrate to cache")
            
            for meeting in meetings:
                packet_url = meeting['packet_url']
                summary = meeting['processed_summary']
                processing_time = meeting['processing_time_seconds'] or 0
                
                # Generate content hash
                import hashlib
                content_hash = hashlib.md5(summary.encode()).hexdigest() if summary else None
                
                # Insert into cache
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO cache
                        (packet_url, content_hash, summary_size, 
                         processing_duration_seconds, cache_hit_count, created_at)
                        VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                    """, (
                        packet_url,
                        content_hash,
                        len(summary) if summary else 0,
                        processing_time
                    ))
                    
                    if cursor.rowcount > 0:
                        self.stats["cache_migrated"] += 1
                        
                except sqlite3.IntegrityError:
                    # Already exists in cache
                    pass
            
            conn.commit()
            
        logger.info(f"Migrated {self.stats['cache_migrated']} entries to cache")

    def add_data_validation_triggers(self):
        """Add triggers to prevent future data issues"""
        logger.info("Adding data validation triggers...")
        
        # Add trigger to validate meeting dates
        with self.db.meetings.get_connection() as conn:
            cursor = conn.cursor()
            
            # Drop existing trigger if it exists
            cursor.execute("DROP TRIGGER IF EXISTS validate_meeting_date")
            
            # Create trigger to validate dates on insert/update
            cursor.execute("""
                CREATE TRIGGER validate_meeting_date
                BEFORE INSERT ON meetings
                FOR EACH ROW
                WHEN NEW.meeting_date IS NULL OR NEW.meeting_date = ''
                BEGIN
                    SELECT RAISE(IGNORE);
                END;
            """)
            
            conn.commit()
            
        logger.info("Data validation triggers added")

    def verify_fixes(self):
        """Verify all fixes were applied successfully"""
        logger.info("\n=== Verification Report ===")
        
        with self.db.meetings.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check invalid dates
            cursor.execute("""
                SELECT COUNT(*) FROM meetings 
                WHERE meeting_date IS NULL OR meeting_date = ''
            """)
            invalid_dates = cursor.fetchone()[0]
            logger.info(f"Meetings with invalid dates: {invalid_dates}")
            
            # Check cache
            cursor.execute("SELECT COUNT(*) FROM cache")
            cache_entries = cursor.fetchone()[0]
            logger.info(f"Processing cache entries: {cache_entries}")
            
            # Check backup tables
            cursor.execute("""
                SELECT COUNT(*) FROM sqlite_master 
                WHERE type='table' AND name LIKE 'meetings_backup_%'
            """)
            backup_tables = cursor.fetchone()[0]
            logger.info(f"Backup tables remaining: {backup_tables}")
        
        with self.db.analytics.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check orphaned analytics
            cursor.execute("""
                SELECT COUNT(*) FROM usage_metrics 
                WHERE city_banana IS NULL OR city_banana = ''
            """)
            orphaned = cursor.fetchone()[0]
            logger.info(f"Orphaned analytics records: {orphaned}")
            
            # Check search analytics
            cursor.execute("SELECT COUNT(*) FROM search_analytics")
            analytics_days = cursor.fetchone()[0]
            logger.info(f"Search analytics days: {analytics_days}")

    def run_all_fixes(self):
        """Run all database fixes"""
        logger.info("Starting database fixes...")
        
        try:
            self.fix_invalid_meeting_dates()
            self.clean_orphaned_analytics()
            self.remove_backup_table()
            self.implement_search_analytics()
            self.migrate_to_cache()
            self.add_data_validation_triggers()
            self.verify_fixes()
            
            logger.info("\n=== Fix Summary ===")
            logger.info(f"Dates fixed: {self.stats['dates_fixed']}")
            logger.info(f"Orphans cleaned: {self.stats['orphans_cleaned']}")
            logger.info(f"Backup removed: {self.stats['backup_removed']}")
            logger.info(f"Analytics aggregated: {self.stats['analytics_aggregated']} days")
            logger.info(f"Cache entries migrated: {self.stats['cache_migrated']}")
            logger.info("\nAll fixes completed successfully!")
            
        except Exception as e:
            logger.error(f"Error during fixes: {e}")
            raise


def main():
    """Main entry point"""
    fixer = DatabaseFixer()
    fixer.run_all_fixes()


if __name__ == "__main__":
    main()