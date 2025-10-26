#!/usr/bin/env python3
"""
Migration script: Old schema → New simplified schema

Key changes:
- city_banana → banana (column names)
- vendor_slug → slug
- city_zipcodes → zipcodes (table name)
- processing_cache → cache
- processing_queue → queue
- agenda_items → items
- meeting_status → status (in meetings table)

Run from project root:
    python scripts/migrate_to_new_schema.py
    python scripts/migrate_to_new_schema.py --dry-run  # Test without committing
"""

import sqlite3
import sys
import shutil
from pathlib import Path
from datetime import datetime


def backup_database(db_path: str) -> str:
    """Create timestamped backup of database"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    shutil.copy2(db_path, backup_path)
    print(f"Created backup: {backup_path}")
    return backup_path


def migrate_database(db_path: str, dry_run: bool = False):
    """Migrate database from old schema to new simplified schema"""

    if not Path(db_path).exists():
        print(f"ERROR: Database not found at {db_path}")
        sys.exit(1)

    # Create backup before migration
    if not dry_run:
        backup_path = backup_database(db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check if migration is needed
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cities'")
    if not cursor.fetchone():
        print("No cities table found - database may be empty or already migrated")
        conn.close()
        return

    # Check if already migrated (new schema has 'banana' column, old has 'city_banana')
    cursor.execute("PRAGMA table_info(cities)")
    columns = {row['name'] for row in cursor.fetchall()}

    if 'banana' in columns:
        print("Database already uses new schema (has 'banana' column)")
        print("Migration not needed.")
        conn.close()
        return

    if 'city_banana' not in columns:
        print("ERROR: Unexpected schema - neither 'banana' nor 'city_banana' found")
        conn.close()
        sys.exit(1)

    print("Starting migration from old schema to new schema...")
    print(f"Database: {db_path}")
    print()

    try:
        # Disable foreign keys during migration
        cursor.execute("PRAGMA foreign_keys=OFF")

        # Clean up any leftover temp tables from previous failed runs
        temp_tables = ['cities_new', 'zipcodes_new', 'meetings_new', 'items_new',
                      'cache_new', 'queue_new', 'tenant_coverage_new', 'tracked_items_new']
        for temp_table in temp_tables:
            cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")

        # ========== MIGRATE CITIES TABLE ==========
        print("1. Migrating cities table (city_banana → banana, vendor_slug → slug)...")

        cursor.execute("""
            CREATE TABLE cities_new (
                banana TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                state TEXT NOT NULL,
                vendor TEXT NOT NULL,
                slug TEXT NOT NULL,
                county TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(name, state)
            )
        """)

        cursor.execute("""
            INSERT INTO cities_new
            (banana, name, state, vendor, slug, county, status, created_at, updated_at)
            SELECT city_banana, name, state, vendor, vendor_slug, county, status, created_at, updated_at
            FROM cities
        """)

        cursor.execute("DROP TABLE cities")
        cursor.execute("ALTER TABLE cities_new RENAME TO cities")

        row_count = cursor.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
        print(f"   Migrated {row_count} cities")

        # ========== MIGRATE CITY_ZIPCODES TABLE ==========
        print("\n2. Migrating city_zipcodes → zipcodes (city_banana → banana)...")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='city_zipcodes'")
        if cursor.fetchone():
            cursor.execute("""
                CREATE TABLE zipcodes_new (
                    banana TEXT NOT NULL,
                    zipcode TEXT NOT NULL,
                    is_primary BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
                    PRIMARY KEY (banana, zipcode)
                )
            """)

            cursor.execute("""
                INSERT INTO zipcodes_new (banana, zipcode, is_primary)
                SELECT city_banana, zipcode, is_primary
                FROM city_zipcodes
            """)

            cursor.execute("DROP TABLE city_zipcodes")
            cursor.execute("ALTER TABLE zipcodes_new RENAME TO zipcodes")

            row_count = cursor.execute("SELECT COUNT(*) FROM zipcodes").fetchone()[0]
            print(f"   Migrated {row_count} zipcode mappings")
        else:
            print("   Table city_zipcodes not found, creating empty zipcodes table")
            cursor.execute("""
                CREATE TABLE zipcodes (
                    banana TEXT NOT NULL,
                    zipcode TEXT NOT NULL,
                    is_primary BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
                    PRIMARY KEY (banana, zipcode)
                )
            """)

        # ========== MIGRATE MEETINGS TABLE ==========
        print("\n3. Migrating meetings table (city_banana → banana, meeting_status → status)...")

        cursor.execute("""
            CREATE TABLE meetings_new (
                id TEXT PRIMARY KEY,
                banana TEXT NOT NULL,
                title TEXT NOT NULL,
                date TIMESTAMP,
                packet_url TEXT,
                summary TEXT,
                status TEXT,
                processing_status TEXT DEFAULT 'pending',
                processing_method TEXT,
                processing_time REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            INSERT INTO meetings_new
            (id, banana, title, date, packet_url, summary, status,
             processing_status, processing_method, processing_time, created_at, updated_at)
            SELECT id, city_banana, title, date, packet_url, summary, meeting_status,
                   processing_status, processing_method, processing_time, created_at, updated_at
            FROM meetings
        """)

        cursor.execute("DROP TABLE meetings")
        cursor.execute("ALTER TABLE meetings_new RENAME TO meetings")

        row_count = cursor.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
        print(f"   Migrated {row_count} meetings")

        # ========== MIGRATE AGENDA_ITEMS TABLE ==========
        print("\n4. Migrating agenda_items → items...")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agenda_items'")
        if cursor.fetchone():
            cursor.execute("""
                CREATE TABLE items_new (
                    id TEXT PRIMARY KEY,
                    meeting_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    attachments TEXT,
                    summary TEXT,
                    topics TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                INSERT INTO items_new
                (id, meeting_id, title, sequence, attachments, summary, topics, created_at)
                SELECT id, meeting_id, title, sequence, attachments, summary, topics, created_at
                FROM agenda_items
            """)

            cursor.execute("DROP TABLE agenda_items")
            cursor.execute("ALTER TABLE items_new RENAME TO items")

            row_count = cursor.execute("SELECT COUNT(*) FROM items").fetchone()[0]
            print(f"   Migrated {row_count} agenda items")
        else:
            print("   Table agenda_items not found, creating empty items table")
            cursor.execute("""
                CREATE TABLE items (
                    id TEXT PRIMARY KEY,
                    meeting_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    attachments TEXT,
                    summary TEXT,
                    topics TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
                )
            """)

        # ========== MIGRATE PROCESSING_CACHE TABLE ==========
        print("\n5. Migrating processing_cache → cache...")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='processing_cache'")
        if cursor.fetchone():
            cursor.execute("""
                CREATE TABLE cache_new (
                    packet_url TEXT PRIMARY KEY,
                    content_hash TEXT,
                    processing_method TEXT,
                    processing_time REAL,
                    cache_hit_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                INSERT INTO cache_new
                (packet_url, content_hash, processing_method, processing_time,
                 cache_hit_count, created_at, last_accessed)
                SELECT packet_url, content_hash, processing_method, processing_time,
                       cache_hit_count, created_at, last_accessed
                FROM processing_cache
            """)

            cursor.execute("DROP TABLE processing_cache")
            cursor.execute("ALTER TABLE cache_new RENAME TO cache")

            row_count = cursor.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            print(f"   Migrated {row_count} cache entries")
        else:
            print("   Table processing_cache not found, creating empty cache table")
            cursor.execute("""
                CREATE TABLE cache (
                    packet_url TEXT PRIMARY KEY,
                    content_hash TEXT,
                    processing_method TEXT,
                    processing_time REAL,
                    cache_hit_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        # ========== MIGRATE PROCESSING_QUEUE TABLE ==========
        print("\n6. Migrating processing_queue → queue (city_banana → banana)...")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='processing_queue'")
        if cursor.fetchone():
            cursor.execute("""
                CREATE TABLE queue_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    packet_url TEXT NOT NULL UNIQUE,
                    meeting_id TEXT,
                    banana TEXT,
                    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
                    priority INTEGER DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT,
                    processing_metadata TEXT,
                    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
                    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                INSERT INTO queue_new
                (id, packet_url, meeting_id, banana, status, priority, retry_count,
                 created_at, started_at, completed_at, error_message, processing_metadata)
                SELECT id, packet_url, meeting_id, city_banana, status, priority, retry_count,
                       created_at, started_at, completed_at, error_message, processing_metadata
                FROM processing_queue
            """)

            cursor.execute("DROP TABLE processing_queue")
            cursor.execute("ALTER TABLE queue_new RENAME TO queue")

            row_count = cursor.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
            print(f"   Migrated {row_count} queue entries")
        else:
            print("   Table processing_queue not found, creating empty queue table")
            cursor.execute("""
                CREATE TABLE queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    packet_url TEXT NOT NULL UNIQUE,
                    meeting_id TEXT,
                    banana TEXT,
                    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
                    priority INTEGER DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT,
                    processing_metadata TEXT,
                    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
                    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
                )
            """)

        # ========== MIGRATE TENANT TABLES (if they exist) ==========
        print("\n7. Migrating tenant tables (city_banana → banana)...")

        # Tenants table doesn't need migration (no city_banana columns)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tenants'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    api_key TEXT UNIQUE NOT NULL,
                    webhook_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

        # Tenant keywords doesn't need migration (no city_banana columns)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tenant_keywords'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tenant_keywords (
                    tenant_id TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
                    PRIMARY KEY (tenant_id, keyword)
                )
            """)

        # Migrate tenant_coverage
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tenant_coverage'")
        if cursor.fetchone():
            # Check if it has the old column name
            cursor.execute("PRAGMA table_info(tenant_coverage)")
            coverage_cols = {row['name'] for row in cursor.fetchall()}

            if 'city_banana' in coverage_cols:
                cursor.execute("""
                    CREATE TABLE tenant_coverage_new (
                        tenant_id TEXT NOT NULL,
                        banana TEXT NOT NULL,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
                        FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
                        PRIMARY KEY (tenant_id, banana)
                    )
                """)

                cursor.execute("""
                    INSERT INTO tenant_coverage_new (tenant_id, banana, added_at)
                    SELECT tenant_id, city_banana, added_at
                    FROM tenant_coverage
                """)

                cursor.execute("DROP TABLE tenant_coverage")
                cursor.execute("ALTER TABLE tenant_coverage_new RENAME TO tenant_coverage")
                print("   Migrated tenant_coverage")
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tenant_coverage (
                    tenant_id TEXT NOT NULL,
                    banana TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
                    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE,
                    PRIMARY KEY (tenant_id, banana)
                )
            """)

        # Migrate tracked_items
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tracked_items'")
        if cursor.fetchone():
            # Check if it has the old column name
            cursor.execute("PRAGMA table_info(tracked_items)")
            tracked_cols = {row['name'] for row in cursor.fetchall()}

            if 'city_banana' in tracked_cols:
                cursor.execute("""
                    CREATE TABLE tracked_items_new (
                        id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL,
                        item_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT,
                        banana TEXT NOT NULL,
                        first_mentioned_meeting_id TEXT,
                        first_seen TIMESTAMP,
                        last_seen TIMESTAMP,
                        status TEXT DEFAULT 'active',
                        metadata TEXT,
                        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
                        FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
                    )
                """)

                cursor.execute("""
                    INSERT INTO tracked_items_new
                    (id, tenant_id, item_type, title, description, banana,
                     first_mentioned_meeting_id, first_seen, last_seen, status, metadata)
                    SELECT id, tenant_id, item_type, title, description, city_banana,
                           first_mentioned_meeting_id, first_seen, last_seen, status, metadata
                    FROM tracked_items
                """)

                cursor.execute("DROP TABLE tracked_items")
                cursor.execute("ALTER TABLE tracked_items_new RENAME TO tracked_items")
                print("   Migrated tracked_items")
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tracked_items (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    banana TEXT NOT NULL,
                    first_mentioned_meeting_id TEXT,
                    first_seen TIMESTAMP,
                    last_seen TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    metadata TEXT,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
                    FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
                )
            """)

        # Tracked item meetings doesn't need migration (no city_banana columns)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tracked_item_meetings'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tracked_item_meetings (
                    tracked_item_id TEXT NOT NULL,
                    meeting_id TEXT NOT NULL,
                    mentioned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    excerpt TEXT,
                    FOREIGN KEY (tracked_item_id) REFERENCES tracked_items(id) ON DELETE CASCADE,
                    FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE,
                    PRIMARY KEY (tracked_item_id, meeting_id)
                )
            """)

        # ========== CREATE INDICES ==========
        print("\n8. Creating performance indices...")

        indices = [
            "CREATE INDEX IF NOT EXISTS idx_cities_vendor ON cities(vendor)",
            "CREATE INDEX IF NOT EXISTS idx_cities_state ON cities(state)",
            "CREATE INDEX IF NOT EXISTS idx_cities_status ON cities(status)",
            "CREATE INDEX IF NOT EXISTS idx_zipcodes_zipcode ON zipcodes(zipcode)",
            "CREATE INDEX IF NOT EXISTS idx_meetings_banana ON meetings(banana)",
            "CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(date)",
            "CREATE INDEX IF NOT EXISTS idx_meetings_status ON meetings(processing_status)",
            "CREATE INDEX IF NOT EXISTS idx_cache_hash ON cache(content_hash)",
            "CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status)",
            "CREATE INDEX IF NOT EXISTS idx_queue_priority ON queue(priority DESC)",
            "CREATE INDEX IF NOT EXISTS idx_queue_city ON queue(banana)",
            "CREATE INDEX IF NOT EXISTS idx_tenant_coverage_city ON tenant_coverage(banana)",
            "CREATE INDEX IF NOT EXISTS idx_tracked_items_tenant ON tracked_items(tenant_id)",
            "CREATE INDEX IF NOT EXISTS idx_tracked_items_city ON tracked_items(banana)",
            "CREATE INDEX IF NOT EXISTS idx_tracked_items_status ON tracked_items(status)",
        ]

        for idx_sql in indices:
            try:
                cursor.execute(idx_sql)
            except sqlite3.OperationalError:
                # Table might not exist (tenant tables)
                pass

        print("   Created indices")

        # Re-enable foreign keys
        cursor.execute("PRAGMA foreign_keys=ON")

        # Commit changes
        if not dry_run:
            conn.commit()
            print("\n" + "="*70)
            print("MIGRATION COMPLETED SUCCESSFULLY")
            print("="*70)
            print(f"Backup saved at: {backup_path}")
        else:
            print("\n" + "="*70)
            print("DRY RUN COMPLETED - NO CHANGES MADE")
            print("="*70)

        # Verify migration
        print("\nVerification:")
        cursor.execute("SELECT COUNT(*) FROM cities")
        print(f"  Cities: {cursor.fetchone()[0]}")
        cursor.execute("SELECT COUNT(*) FROM meetings")
        print(f"  Meetings: {cursor.fetchone()[0]}")
        cursor.execute("SELECT COUNT(*) FROM items")
        print(f"  Items: {cursor.fetchone()[0]}")

    except Exception as e:
        print(f"\nERROR during migration: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        if not dry_run:
            print(f"\nDatabase rolled back. Backup available at: {backup_path}")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate Engagic database to new simplified schema")
    parser.add_argument(
        "--db-path",
        default="data/engagic.db",
        help="Path to database file (default: data/engagic.db)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run migration without committing changes"
    )

    args = parser.parse_args()

    print("="*70)
    print("Engagic Database Migration: Old Schema → New Simplified Schema")
    print("="*70)
    print()

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made\n")

    migrate_database(args.db_path, dry_run=args.dry_run)
