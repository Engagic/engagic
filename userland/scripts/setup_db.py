#!/usr/bin/env python3
"""
Setup userland schema in PostgreSQL database.

Applies schema_userland.sql to create the userland schema and tables.
Safe to run multiple times (uses IF NOT EXISTS).
"""

import asyncio
import asyncpg
from pathlib import Path

from config import settings


async def setup_userland_schema():
    """Apply userland schema to PostgreSQL database"""

    # Read schema file
    schema_path = Path(__file__).parent.parent.parent / "database" / "schema_userland.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    schema_sql = schema_path.read_text()

    # Get database connection string
    database_url = settings.get_postgres_dsn()

    print("Connecting to PostgreSQL database...")
    print(f"Database: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}")

    # Connect to database
    conn = await asyncpg.connect(database_url)

    try:
        print(f"\nApplying userland schema from {schema_path}...")

        # Execute schema SQL
        await conn.execute(schema_sql)

        print("\nSchema applied successfully!")

        # Verify tables exist
        print("\nVerifying tables...")
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'userland'
            ORDER BY table_name
        """)

        print("\nUserland tables created:")
        for table in tables:
            print(f"  - userland.{table['table_name']}")

        # Count existing records
        user_count = await conn.fetchval("SELECT COUNT(*) FROM userland.users")
        alert_count = await conn.fetchval("SELECT COUNT(*) FROM userland.alerts")

        print("\nCurrent data:")
        print(f"  - Users: {user_count}")
        print(f"  - Alerts: {alert_count}")

    finally:
        await conn.close()
        print("\nDatabase connection closed.")


if __name__ == "__main__":
    asyncio.run(setup_userland_schema())
