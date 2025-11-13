"""
Fix city_matters schema: Make first_seen/last_seen nullable

The code tries to INSERT without first_seen/last_seen, then UPDATE them.
But the schema has NOT NULL constraints. Need to remove those.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import config


def main():
    db_path = config.UNIFIED_DB_PATH
    print(f"Database: {db_path}\n")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        print("=" * 60)
        print("Fixing city_matters schema")
        print("=" * 60)

        conn.execute("BEGIN TRANSACTION")

        # Create new table without NOT NULL on first_seen/last_seen
        print("Creating temporary table...")
        conn.execute("""
            CREATE TABLE city_matters_new (
                id TEXT PRIMARY KEY,
                banana TEXT NOT NULL,
                matter_id TEXT,
                matter_file TEXT,
                matter_type TEXT,
                title TEXT NOT NULL,
                sponsors TEXT,
                canonical_summary TEXT,
                canonical_topics TEXT,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                appearance_count INTEGER DEFAULT 1,
                status TEXT DEFAULT 'active',
                attachments TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (banana) REFERENCES cities(banana) ON DELETE CASCADE
            )
        """)

        # Copy all data
        print("Copying data...")
        conn.execute("""
            INSERT INTO city_matters_new
            SELECT * FROM city_matters
        """)

        # Get count
        count = conn.execute("SELECT COUNT(*) FROM city_matters_new").fetchone()[0]
        print(f"Copied {count} records")

        # Drop old table
        print("Dropping old table...")
        conn.execute("DROP TABLE city_matters")

        # Rename new table
        print("Renaming new table...")
        conn.execute("ALTER TABLE city_matters_new RENAME TO city_matters")

        # Recreate indexes
        print("Recreating indexes...")
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_city_matters_banana
            ON city_matters(banana)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_city_matters_matter_file
            ON city_matters(matter_file)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_city_matters_matter_id
            ON city_matters(matter_id)
        """)

        conn.commit()

        print("\n" + "=" * 60)
        print("Schema fix complete!")
        print("=" * 60)
        print("  first_seen: NOT NULL -> nullable")
        print("  last_seen: NOT NULL -> nullable")
        print(f"  {count} records preserved")

    except Exception as e:
        print(f"\nERROR: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
