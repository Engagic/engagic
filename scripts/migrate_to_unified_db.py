"""
Migration script: 3-database architecture -> Unified database

Migrates data from:
- locations.db (cities, zipcodes)
- meetings.db (meetings, processing_cache)
- analytics.db (not migrated - can be dropped)

To:
- unified.db (single database with all tables)

Usage:
    python scripts/migrate_to_unified_db.py --source-dir /path/to/data --output unified.db

Safety features:
- Creates backup of source databases before migration
- Validates data integrity after migration
- Logs all operations
- Can run in dry-run mode
"""

import argparse
import logging
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.database.unified_db import UnifiedDatabase, Meeting

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseMigrator:
    """Handles migration from 3-DB to unified DB"""

    def __init__(self, source_dir: str, output_path: str, dry_run: bool = False):
        self.source_dir = Path(source_dir)
        self.output_path = Path(output_path)
        self.dry_run = dry_run

        self.locations_db = self.source_dir / "locations.db"
        self.meetings_db = self.source_dir / "meetings.db"
        self.analytics_db = self.source_dir / "analytics.db"

        # Verify source databases exist
        if not self.locations_db.exists():
            raise FileNotFoundError(f"locations.db not found at {self.locations_db}")
        if not self.meetings_db.exists():
            raise FileNotFoundError(f"meetings.db not found at {self.meetings_db}")

        logger.info(f"Source directory: {self.source_dir}")
        logger.info(f"Output database: {self.output_path}")
        logger.info(f"Dry run: {self.dry_run}")

    def create_backup(self):
        """Create backup of source databases"""
        backup_dir = self.source_dir / "backup" / datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Creating backup at {backup_dir}")

        if self.locations_db.exists():
            shutil.copy2(self.locations_db, backup_dir / "locations.db")
            logger.info("  Backed up locations.db")

        if self.meetings_db.exists():
            shutil.copy2(self.meetings_db, backup_dir / "meetings.db")
            logger.info("  Backed up meetings.db")

        if self.analytics_db.exists():
            shutil.copy2(self.analytics_db, backup_dir / "analytics.db")
            logger.info("  Backed up analytics.db")

        logger.info(f"Backup complete at {backup_dir}")
        return backup_dir

    def migrate_cities(self, unified_db: UnifiedDatabase):
        """Migrate cities from locations.db"""
        logger.info("Migrating cities from locations.db...")

        # Connect to old locations.db
        locations_conn = sqlite3.connect(self.locations_db)
        locations_conn.row_factory = sqlite3.Row

        # Get all cities
        cursor = locations_conn.cursor()
        cursor.execute("SELECT * FROM cities")
        cities = cursor.fetchall()

        logger.info(f"Found {len(cities)} cities to migrate")

        migrated = 0
        errors = 0

        for city_row in cities:
            try:
                # Convert Row to dict for easier access
                city = dict(city_row)

                city_banana = city['city_banana']
                name = city['city_name']
                state = city['state']
                vendor = city.get('vendor') or 'unknown'
                vendor_slug = city.get('city_slug') or ''
                county = city.get('county')

                # Get zipcodes for this city
                cursor.execute("""
                    SELECT zipcode FROM zipcodes
                    WHERE city_id = ?
                    ORDER BY is_primary DESC
                """, (city['id'],))
                zipcodes = [row['zipcode'] for row in cursor.fetchall()]

                if not self.dry_run:
                    unified_db.add_city(
                        banana=city_banana,
                        name=name,
                        state=state,
                        vendor=vendor,
                        vendor_slug=vendor_slug,
                        county=county,
                        zipcodes=zipcodes
                    )

                migrated += 1
                if migrated % 50 == 0:
                    logger.info(f"  Migrated {migrated}/{len(cities)} cities...")

            except Exception as e:
                city_name = dict(city_row).get('city_name', 'Unknown')
                logger.error(f"  Error migrating city {city_name}: {e}")
                errors += 1

        locations_conn.close()

        logger.info(f"Cities migration complete: {migrated} migrated, {errors} errors")
        return migrated, errors

    def migrate_meetings(self, unified_db: UnifiedDatabase):
        """Migrate meetings from meetings.db"""
        logger.info("Migrating meetings from meetings.db...")

        # Connect to old meetings.db
        meetings_conn = sqlite3.connect(self.meetings_db)
        meetings_conn.row_factory = sqlite3.Row

        # Get all meetings
        cursor = meetings_conn.cursor()
        cursor.execute("SELECT * FROM meetings")
        meetings = cursor.fetchall()

        logger.info(f"Found {len(meetings)} meetings to migrate")

        migrated = 0
        errors = 0

        for meeting_row in meetings:
            try:
                # Convert Row to dict for easier access
                meeting_dict = dict(meeting_row)

                # Generate meeting ID if missing
                meeting_id = meeting_dict.get('meeting_id')
                if not meeting_id:
                    # Generate from hash
                    import hashlib
                    hash_input = f"{meeting_dict['city_banana']}_{meeting_dict.get('meeting_name', '')}_{meeting_dict.get('meeting_date', '')}"
                    meeting_id = "auto_" + hashlib.md5(hash_input.encode()).hexdigest()[:12]

                # Parse date
                date_str = meeting_dict.get('meeting_date')
                meeting_date = None
                if date_str:
                    try:
                        meeting_date = datetime.fromisoformat(date_str)
                    except:
                        logger.warning(f"  Could not parse date: {date_str}")

                # Determine processing status
                if meeting_dict.get('processed_summary'):
                    status = "completed"
                elif meeting_dict.get('packet_url'):
                    status = "pending"
                else:
                    status = "no_packet"

                meeting = Meeting(
                    id=meeting_id,
                    city_banana=meeting_dict['city_banana'],
                    title=meeting_dict.get('meeting_name', 'Untitled Meeting'),
                    date=meeting_date,
                    packet_url=meeting_dict.get('packet_url'),
                    summary=meeting_dict.get('processed_summary'),
                    processing_status=status,
                    processing_method=None,  # Not tracked in old schema
                    processing_time=meeting_dict.get('processing_time_seconds')
                )

                if not self.dry_run:
                    unified_db.store_meeting(meeting)

                migrated += 1
                if migrated % 100 == 0:
                    logger.info(f"  Migrated {migrated}/{len(meetings)} meetings...")

            except Exception as e:
                meeting_name = dict(meeting_row).get('meeting_name', 'Unknown')
                logger.error(f"  Error migrating meeting {meeting_name}: {e}")
                errors += 1

        meetings_conn.close()

        logger.info(f"Meetings migration complete: {migrated} migrated, {errors} errors")
        return migrated, errors

    def validate_migration(self, unified_db: UnifiedDatabase):
        """Validate migration completed successfully"""
        logger.info("Validating migration...")

        errors = []

        # Check cities count
        locations_conn = sqlite3.connect(self.locations_db)
        cursor = locations_conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM cities")
        old_city_count = cursor.fetchone()[0]
        locations_conn.close()

        new_city_count = len(unified_db.get_cities(status="active"))

        if old_city_count != new_city_count:
            errors.append(f"City count mismatch: old={old_city_count}, new={new_city_count}")
        else:
            logger.info(f"  City count matches: {new_city_count}")

        # Check meetings count
        meetings_conn = sqlite3.connect(self.meetings_db)
        cursor = meetings_conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM meetings")
        old_meeting_count = cursor.fetchone()[0]
        meetings_conn.close()

        cursor = unified_db.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM meetings")
        new_meeting_count = cursor.fetchone()[0]

        if old_meeting_count != new_meeting_count:
            errors.append(f"Meeting count mismatch: old={old_meeting_count}, new={new_meeting_count}")
        else:
            logger.info(f"  Meeting count matches: {new_meeting_count}")

        # Check sample cities
        locations_conn = sqlite3.connect(self.locations_db)
        locations_conn.row_factory = sqlite3.Row
        cursor = locations_conn.cursor()
        cursor.execute("SELECT * FROM cities LIMIT 5")
        sample_cities = cursor.fetchall()

        for city_row in sample_cities:
            city = unified_db.get_city(banana=city_row['city_banana'])
            if not city:
                errors.append(f"City not found in unified DB: {city_row['city_banana']}")
            else:
                logger.info(f"  Verified city: {city.name}, {city.state}")

        locations_conn.close()

        if errors:
            logger.error("Validation FAILED:")
            for error in errors:
                logger.error(f"  - {error}")
            return False
        else:
            logger.info("Validation PASSED")
            return True

    def run(self):
        """Execute full migration"""
        logger.info("=" * 60)
        logger.info("Starting database migration")
        logger.info("=" * 60)

        if self.dry_run:
            logger.info("DRY RUN MODE - No changes will be made")

        # Create backup
        if not self.dry_run:
            backup_dir = self.create_backup()
            logger.info(f"Backup created at: {backup_dir}")

        # Initialize unified database
        if not self.dry_run:
            if self.output_path.exists():
                logger.warning(f"Output database already exists: {self.output_path}")
                response = input("Overwrite? (yes/no): ")
                if response.lower() != 'yes':
                    logger.info("Migration aborted")
                    return False
                self.output_path.unlink()

        unified_db = UnifiedDatabase(str(self.output_path))

        # Migrate cities
        cities_migrated, cities_errors = self.migrate_cities(unified_db)

        # Migrate meetings
        meetings_migrated, meetings_errors = self.migrate_meetings(unified_db)

        # Validate
        if not self.dry_run:
            validation_passed = self.validate_migration(unified_db)
        else:
            validation_passed = True
            logger.info("Skipping validation (dry run)")

        # Summary
        logger.info("=" * 60)
        logger.info("Migration Summary")
        logger.info("=" * 60)
        logger.info(f"Cities migrated: {cities_migrated} (errors: {cities_errors})")
        logger.info(f"Meetings migrated: {meetings_migrated} (errors: {meetings_errors})")
        logger.info(f"Validation: {'PASSED' if validation_passed else 'FAILED'}")

        if not self.dry_run:
            logger.info(f"Unified database created at: {self.output_path}")
            logger.info(f"Backup available at: {backup_dir}")

        unified_db.close()

        return validation_passed


def main():
    parser = argparse.ArgumentParser(description="Migrate Engagic to unified database")
    parser.add_argument(
        "--source-dir",
        required=True,
        help="Directory containing locations.db and meetings.db"
    )
    parser.add_argument(
        "--output",
        default="unified.db",
        help="Output path for unified database (default: unified.db)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run migration without making changes"
    )

    args = parser.parse_args()

    migrator = DatabaseMigrator(
        source_dir=args.source_dir,
        output_path=args.output,
        dry_run=args.dry_run
    )

    success = migrator.run()

    if success:
        logger.info("Migration completed successfully")
        return 0
    else:
        logger.error("Migration completed with errors")
        return 1


if __name__ == "__main__":
    sys.exit(main())
