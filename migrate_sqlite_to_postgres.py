"""
SQLite to PostgreSQL Migration Script
Migrates all data from engagic.db (SQLite) to PostgreSQL

Usage:
    uv run migrate_sqlite_to_postgres.py [--dry-run] [--batch-size 100]
"""

import asyncio
import json
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from database.db_postgres import Database
from database.models import City, Meeting, AgendaItem, Matter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


class MigrationStats:
    """Track migration statistics"""
    def __init__(self):
        self.cities = 0
        self.meetings = 0
        self.items = 0
        self.city_matters = 0
        self.matter_appearances = 0
        self.matter_topics = 0
        self.queue_jobs = 0
        self.cache_entries = 0
        self.zipcodes = 0
        self.meeting_topics = 0
        self.item_topics = 0
        self.errors = []

    def report(self):
        """Print migration summary"""
        logger.info("=" * 60)
        logger.info("Migration Summary")
        logger.info("=" * 60)
        logger.info(f"Cities:             {self.cities:,}")
        logger.info(f"Zipcodes:           {self.zipcodes:,}")
        logger.info(f"Meetings:           {self.meetings:,}")
        logger.info(f"Meeting Topics:     {self.meeting_topics:,}")
        logger.info(f"City Matters:       {self.city_matters:,}")
        logger.info(f"Matter Topics:      {self.matter_topics:,}")
        logger.info(f"Matter Appearances: {self.matter_appearances:,}")
        logger.info(f"Items:              {self.items:,}")
        logger.info(f"Item Topics:        {self.item_topics:,}")
        logger.info(f"Queue Jobs:         {self.queue_jobs:,}")
        logger.info(f"Cache Entries:      {self.cache_entries:,}")
        logger.info(f"Errors:             {len(self.errors)}")
        if self.errors:
            logger.error("\nErrors encountered:")
            for err in self.errors[:10]:  # Show first 10 errors
                logger.error(f"  - {err}")
            if len(self.errors) > 10:
                logger.error(f"  ... and {len(self.errors) - 10} more")


class SQLitePostgresMigrator:
    """Migrate data from SQLite to PostgreSQL"""

    def __init__(self, sqlite_path: str, dry_run: bool = False, batch_size: int = 100):
        self.sqlite_path = sqlite_path
        self.dry_run = dry_run
        self.batch_size = batch_size
        self.stats = MigrationStats()
        self.sqlite_conn = None
        self.pg_db = None

    async def connect(self):
        """Connect to both databases"""
        logger.info(f"Connecting to SQLite: {self.sqlite_path}")
        self.sqlite_conn = sqlite3.connect(self.sqlite_path)
        self.sqlite_conn.row_factory = sqlite3.Row

        logger.info("Connecting to PostgreSQL...")
        self.pg_db = await Database.create()
        logger.info("Connected to both databases")

    async def close(self):
        """Close connections"""
        if self.sqlite_conn:
            self.sqlite_conn.close()
        if self.pg_db:
            await self.pg_db.close()

    def get_sqlite_data(self, table: str) -> List[Dict[str, Any]]:
        """Fetch all rows from SQLite table"""
        cursor = self.sqlite_conn.cursor()
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse timestamp string from SQLite into datetime object

        Handles ISO format timestamps with or without timezone info.
        Returns None if timestamp_str is None or empty.
        """
        if not timestamp_str:
            return None

        try:
            # Handle ISO format with Z (UTC) suffix
            if timestamp_str.endswith("Z"):
                return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            # Handle ISO format
            return datetime.fromisoformat(timestamp_str)
        except (ValueError, AttributeError):
            logger.warning(f"Failed to parse timestamp: {timestamp_str}")
            return None

    async def migrate_cities(self):
        """Migrate cities and zipcodes"""
        logger.info("\n--- Migrating Cities ---")
        cities = self.get_sqlite_data("cities")
        logger.info(f"Found {len(cities):,} cities in SQLite")

        # Fetch all zipcodes and group by banana
        all_zipcodes = self.get_sqlite_data("zipcodes")
        zipcodes_by_city = {}
        for zc in all_zipcodes:
            banana = zc["banana"]
            if banana not in zipcodes_by_city:
                zipcodes_by_city[banana] = []
            zipcodes_by_city[banana].append(zc["zipcode"])

        logger.info(f"Found {len(all_zipcodes):,} zipcodes in SQLite")

        for i, city in enumerate(cities, 1):
            if i % 100 == 0:
                logger.info(f"Progress: {i}/{len(cities)} cities")

            try:
                # Get zipcodes for this city from the separate table
                zipcodes = zipcodes_by_city.get(city["banana"], [])

                # Create City model object
                city_obj = City(
                    banana=city["banana"],
                    name=city["name"],
                    state=city["state"],
                    vendor=city["vendor"],
                    slug=city["slug"],
                    county=city.get("county"),
                    zipcodes=zipcodes if zipcodes else None,
                    status=city.get("status", "active")
                )

                if not self.dry_run:
                    await self.pg_db.cities.add_city(city_obj)

                self.stats.cities += 1
                self.stats.zipcodes += len(zipcodes)

            except Exception as e:
                error_msg = f"City {city.get('banana')}: {str(e)}"
                self.stats.errors.append(error_msg)
                logger.error(error_msg)

        logger.info(f"✅ Migrated {self.stats.cities:,} cities with {self.stats.zipcodes:,} zipcodes")

    async def migrate_meetings(self):
        """Migrate meetings and meeting_topics"""
        logger.info("\n--- Migrating Meetings ---")
        meetings = self.get_sqlite_data("meetings")
        logger.info(f"Found {len(meetings):,} meetings in SQLite")

        for i, meeting in enumerate(meetings, 1):
            if i % 100 == 0:
                logger.info(f"Progress: {i}/{len(meetings)} meetings")

            try:
                # Parse JSON fields
                topics = []
                if meeting.get("topics"):
                    if isinstance(meeting["topics"], str):
                        topics = json.loads(meeting["topics"])
                    else:
                        topics = meeting["topics"]

                participation = None
                if meeting.get("participation"):
                    if isinstance(meeting["participation"], str):
                        participation = json.loads(meeting["participation"])
                    else:
                        participation = meeting["participation"]

                # Convert date string to datetime
                date = None
                if meeting.get("date"):
                    try:
                        date = datetime.fromisoformat(meeting["date"].replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass

                # Create Meeting model object
                meeting_obj = Meeting(
                    id=meeting["id"],
                    banana=meeting["banana"],
                    title=meeting["title"],
                    date=date,
                    agenda_url=meeting.get("agenda_url"),
                    packet_url=meeting.get("packet_url"),
                    summary=meeting.get("summary"),
                    topics=topics if topics else None,
                    participation=participation,
                    status=meeting.get("status"),
                    processing_status=meeting.get("processing_status", "pending"),
                    processing_method=meeting.get("processing_method"),
                    processing_time=meeting.get("processing_time")
                )

                if not self.dry_run:
                    await self.pg_db.meetings.store_meeting(meeting_obj)

                self.stats.meetings += 1
                self.stats.meeting_topics += len(topics)

            except Exception as e:
                error_msg = f"Meeting {meeting.get('id')}: {str(e)}"
                self.stats.errors.append(error_msg)
                logger.error(error_msg)

        logger.info(f"✅ Migrated {self.stats.meetings:,} meetings with {self.stats.meeting_topics:,} topics")

    async def migrate_city_matters(self):
        """Migrate city_matters (legislative items tracked across meetings)"""
        logger.info("\n--- Migrating City Matters ---")
        matters = self.get_sqlite_data("city_matters")
        logger.info(f"Found {len(matters):,} city matters in SQLite")

        processed = 0
        for matter in matters:
            try:
                # Parse JSON fields
                sponsors = []
                if matter.get("sponsors"):
                    if isinstance(matter["sponsors"], str):
                        sponsors = json.loads(matter["sponsors"])
                    else:
                        sponsors = matter["sponsors"]

                canonical_topics = []
                if matter.get("canonical_topics"):
                    if isinstance(matter["canonical_topics"], str):
                        canonical_topics = json.loads(matter["canonical_topics"])
                    else:
                        canonical_topics = matter["canonical_topics"]

                attachments = []
                if matter.get("attachments"):
                    if isinstance(matter["attachments"], str):
                        attachments = json.loads(matter["attachments"])
                    else:
                        attachments = matter["attachments"]

                metadata = {}
                if matter.get("metadata"):
                    if isinstance(matter["metadata"], str):
                        metadata = json.loads(matter["metadata"])
                    else:
                        metadata = matter["metadata"]

                # Create Matter model object
                matter_obj = Matter(
                    id=matter["id"],
                    banana=matter["banana"],
                    matter_id=matter.get("matter_id"),
                    matter_file=matter.get("matter_file"),
                    matter_type=matter.get("matter_type"),
                    title=matter["title"],
                    sponsors=sponsors if sponsors else None,
                    canonical_summary=matter.get("canonical_summary"),
                    canonical_topics=canonical_topics if canonical_topics else None,
                    first_seen=self.parse_timestamp(matter.get("first_seen")),
                    last_seen=self.parse_timestamp(matter.get("last_seen")),
                    appearance_count=matter.get("appearance_count", 1),
                    status=matter.get("status", "active"),
                    attachments=attachments if attachments else None,
                    metadata=metadata if metadata else None
                )

                if not self.dry_run:
                    await self.pg_db.matters.store_matter(matter_obj)

                self.stats.city_matters += 1
                if canonical_topics:
                    self.stats.matter_topics += len(canonical_topics)

                processed += 1
                if processed % 500 == 0:
                    logger.info(f"Progress: {processed}/{len(matters)} matters")

            except Exception as e:
                error_msg = f"Matter {matter.get('id')}: {str(e)}"
                self.stats.errors.append(error_msg)
                logger.error(error_msg)

        logger.info(f"✅ Migrated {self.stats.city_matters:,} city matters with {self.stats.matter_topics:,} topics")

    async def migrate_items(self):
        """Migrate agenda items and item_topics"""
        logger.info("\n--- Migrating Agenda Items ---")
        items = self.get_sqlite_data("items")
        logger.info(f"Found {len(items):,} items in SQLite")

        # Batch items by meeting_id for efficiency
        items_by_meeting: Dict[str, List[Dict]] = {}
        for item in items:
            meeting_id = item["meeting_id"]
            if meeting_id not in items_by_meeting:
                items_by_meeting[meeting_id] = []
            items_by_meeting[meeting_id].append(item)

        logger.info(f"Grouped into {len(items_by_meeting):,} meetings")

        processed = 0
        for meeting_id, meeting_items in items_by_meeting.items():
            try:
                # Convert items to AgendaItem objects
                items_to_store = []
                for item in meeting_items:
                    # Parse JSON fields
                    topics = []
                    if item.get("topics"):
                        if isinstance(item["topics"], str):
                            topics = json.loads(item["topics"])
                        else:
                            topics = item["topics"]

                    attachments = []
                    if item.get("attachments"):
                        if isinstance(item["attachments"], str):
                            attachments = json.loads(item["attachments"])
                        else:
                            attachments = item["attachments"]

                    sponsors = []
                    if item.get("sponsors"):
                        if isinstance(item["sponsors"], str):
                            sponsors = json.loads(item["sponsors"])
                        else:
                            sponsors = item["sponsors"]

                    # Create AgendaItem model object
                    agenda_item = AgendaItem(
                        id=item["id"],
                        meeting_id=item["meeting_id"],
                        title=item["title"],
                        sequence=item["sequence"],
                        attachments=attachments,
                        summary=item.get("summary"),
                        topics=topics if topics else None,
                        matter_id=item.get("matter_id"),
                        matter_file=item.get("matter_file"),
                        matter_type=item.get("matter_type"),
                        agenda_number=item.get("agenda_number"),
                        sponsors=sponsors if sponsors else None
                    )
                    items_to_store.append(agenda_item)
                    self.stats.item_topics += len(topics)

                if not self.dry_run:
                    await self.pg_db.items.store_agenda_items(meeting_id, items_to_store)

                self.stats.items += len(items_to_store)
                processed += 1

                if processed % 100 == 0:
                    logger.info(f"Progress: {processed}/{len(items_by_meeting)} meetings ({self.stats.items:,} items)")

            except Exception as e:
                error_msg = f"Items for meeting {meeting_id}: {str(e)}"
                self.stats.errors.append(error_msg)
                logger.error(error_msg)

        logger.info(f"✅ Migrated {self.stats.items:,} items with {self.stats.item_topics:,} topics")

    async def migrate_matter_appearances(self):
        """Migrate matter_appearances (matter tracking across meetings)"""
        logger.info("\n--- Migrating Matter Appearances ---")
        appearances = self.get_sqlite_data("matter_appearances")
        logger.info(f"Found {len(appearances):,} matter appearances in SQLite")

        processed = 0
        for appearance in appearances:
            try:
                # Parse vote_tally JSON if present
                vote_tally = None
                if appearance.get("vote_tally"):
                    if isinstance(appearance["vote_tally"], str):
                        try:
                            vote_tally = json.loads(appearance["vote_tally"])
                        except json.JSONDecodeError:
                            vote_tally = None
                    else:
                        vote_tally = appearance["vote_tally"]

                if not self.dry_run:
                    # Store matter appearance directly via SQL
                    # Note: PostgreSQL uses auto-increment for id, so we don't pass it
                    await self.pg_db.pool.execute(
                        """
                        INSERT INTO matter_appearances (
                            matter_id, meeting_id, item_id, appeared_at,
                            committee, action, vote_tally, sequence
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT (matter_id, meeting_id, item_id) DO NOTHING
                        """,
                        appearance["matter_id"],
                        appearance["meeting_id"],
                        appearance["item_id"],
                        self.parse_timestamp(appearance["appeared_at"]),
                        appearance.get("committee"),
                        appearance.get("action"),
                        json.dumps(vote_tally) if vote_tally else None,
                        appearance.get("sequence")
                    )

                self.stats.matter_appearances += 1
                processed += 1
                if processed % 500 == 0:
                    logger.info(f"Progress: {processed}/{len(appearances)} appearances")

            except Exception as e:
                error_msg = f"Appearance {appearance.get('id')}: {str(e)}"
                self.stats.errors.append(error_msg)
                logger.error(error_msg)

        logger.info(f"✅ Migrated {self.stats.matter_appearances:,} matter appearances")

    async def migrate_queue(self):
        """Migrate processing queue"""
        logger.info("\n--- Migrating Queue Jobs ---")
        jobs = self.get_sqlite_data("queue")
        logger.info(f"Found {len(jobs):,} queue jobs in SQLite")

        for i, job in enumerate(jobs, 1):
            if i % 100 == 0:
                logger.info(f"Progress: {i}/{len(jobs)} jobs")

            try:
                # Note: Intentionally NOT migrating processing_metadata, started_at, completed_at
                # These represent processing state which we discard during migration
                # All jobs are re-queued fresh in 'pending' status

                if not self.dry_run:
                    # Parse payload if JSON string
                    payload = {}
                    if job.get("payload"):
                        if isinstance(job["payload"], str):
                            try:
                                payload = json.loads(job["payload"])
                            except json.JSONDecodeError:
                                payload = {}
                        else:
                            payload = job["payload"]

                    await self.pg_db.queue.enqueue_job(
                        source_url=job["source_url"],
                        job_type=job.get("job_type", "meeting"),  # Default to meeting
                        payload=payload,
                        meeting_id=job.get("meeting_id"),
                        banana=job.get("banana"),
                        priority=job.get("priority", 0)
                    )

                self.stats.queue_jobs += 1

            except Exception as e:
                error_msg = f"Queue job {job.get('id')}: {str(e)}"
                self.stats.errors.append(error_msg)
                # Don't log every queue error, they're expected for duplicates

        logger.info(f"✅ Migrated {self.stats.queue_jobs:,} queue jobs")

    async def migrate_cache(self):
        """Migrate processing cache"""
        logger.info("\n--- Migrating Cache ---")
        cache_entries = self.get_sqlite_data("cache")
        logger.info(f"Found {len(cache_entries):,} cache entries in SQLite")

        for i, entry in enumerate(cache_entries, 1):
            if i % 50 == 0:
                logger.info(f"Progress: {i}/{len(cache_entries)} cache entries")

            try:
                if not self.dry_run:
                    # Insert cache entry directly via SQL (no dedicated method)
                    await self.pg_db.pool.execute(
                        """
                        INSERT INTO cache (
                            packet_url, content_hash, processing_method, processing_time,
                            cache_hit_count, created_at, last_accessed
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (packet_url) DO NOTHING
                        """,
                        entry["packet_url"],
                        entry.get("content_hash"),
                        entry.get("processing_method"),
                        entry.get("processing_time"),
                        entry.get("cache_hit_count", 0),
                        datetime.now(),
                        datetime.now()
                    )

                self.stats.cache_entries += 1

            except Exception as e:
                error_msg = f"Cache {entry.get('packet_url')}: {str(e)}"
                self.stats.errors.append(error_msg)
                logger.error(error_msg)

        logger.info(f"✅ Migrated {self.stats.cache_entries:,} cache entries")

    async def verify_counts(self):
        """Verify row counts match"""
        logger.info("\n--- Verifying Migration ---")

        # Get SQLite counts
        sqlite_counts = {}
        for table in ["cities", "meetings", "items", "queue", "cache"]:
            cursor = self.sqlite_conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            sqlite_counts[table] = cursor.fetchone()[0]

        # Get PostgreSQL counts
        pg_counts = {}
        for table in ["cities", "meetings", "items", "queue", "cache"]:
            count = await self.pg_db.pool.fetchval(f"SELECT COUNT(*) FROM {table}")
            pg_counts[table] = count

        # Compare
        logger.info("\nRow Count Verification:")
        logger.info(f"{'Table':<15} {'SQLite':>10} {'PostgreSQL':>12} {'Match':>8}")
        logger.info("-" * 50)

        all_match = True
        for table in ["cities", "meetings", "items", "queue", "cache"]:
            sqlite_count = sqlite_counts.get(table, 0)
            pg_count = pg_counts.get(table, 0)
            match = "✅" if sqlite_count == pg_count else "❌"
            if sqlite_count != pg_count:
                all_match = False

            logger.info(f"{table:<15} {sqlite_count:>10,} {pg_count:>12,} {match:>8}")

        return all_match

    async def run(self):
        """Run full migration"""
        try:
            await self.connect()

            if self.dry_run:
                logger.info("🔍 DRY RUN MODE - No data will be written")

            logger.info(f"\nBatch size: {self.batch_size}")
            logger.info("=" * 60)

            # Migrate in order (respecting foreign keys)
            await self.migrate_cities()
            await self.migrate_meetings()
            await self.migrate_city_matters()
            await self.migrate_items()
            await self.migrate_matter_appearances()
            await self.migrate_queue()
            await self.migrate_cache()

            # Report stats
            self.stats.report()

            # Verify if not dry run
            if not self.dry_run:
                all_match = await self.verify_counts()
                if all_match:
                    logger.info("\n✅ Migration completed successfully!")
                else:
                    logger.warning("\n⚠️  Migration completed with count mismatches")
                    return 1
            else:
                logger.info("\n✅ Dry run completed successfully!")

            return 0

        except Exception as e:
            logger.error(f"\n❌ Migration failed: {e}")
            import traceback
            traceback.print_exc()
            return 1

        finally:
            await self.close()


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Migrate SQLite to PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Simulate migration without writing")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for migrations")
    parser.add_argument("--sqlite-path", type=str, default="/root/engagic/data/engagic.db", help="Path to SQLite database")

    args = parser.parse_args()

    # Verify SQLite database exists
    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        logger.error(f"SQLite database not found: {sqlite_path}")
        return 1

    # Run migration
    migrator = SQLitePostgresMigrator(
        sqlite_path=str(sqlite_path),
        dry_run=args.dry_run,
        batch_size=args.batch_size
    )

    return await migrator.run()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
