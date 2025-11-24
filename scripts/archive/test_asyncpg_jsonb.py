#!/usr/bin/env python3
"""Test asyncpg's JSONB handling - does it expect dicts or JSON strings?"""

import asyncio
import asyncpg
from config import config

async def test_jsonb():
    # Connect to database
    dsn = config.get_postgres_dsn()
    conn = await asyncpg.connect(dsn)

    try:
        # Create test table
        await conn.execute("""
            DROP TABLE IF EXISTS test_jsonb;
            CREATE TABLE test_jsonb (
                id SERIAL PRIMARY KEY,
                data JSONB
            );
        """)

        # Test 1: Insert with native Python dict
        print("Test 1: Inserting native Python dict...")
        test_dict = {"foo": "bar", "num": 123}
        try:
            await conn.execute(
                "INSERT INTO test_jsonb (data) VALUES ($1)",
                test_dict
            )
            print("✓ Native dict works!")
        except Exception as e:
            print(f"✗ Native dict failed: {e}")

        # Test 2: Insert with JSON string
        print("\nTest 2: Inserting JSON string...")
        import json
        test_json_string = json.dumps({"foo": "bar", "num": 123})
        try:
            await conn.execute(
                "INSERT INTO test_jsonb (data) VALUES ($1)",
                test_json_string
            )
            print("✓ JSON string works!")
        except Exception as e:
            print(f"✗ JSON string failed: {e}")

        # Check what's in the table
        print("\nWhat's in the table:")
        rows = await conn.fetch("SELECT id, data, pg_typeof(data) FROM test_jsonb")
        for row in rows:
            print(f"  ID {row['id']}: {row['data']} (type: {row['pg_typeof']})")

        # Cleanup
        await conn.execute("DROP TABLE test_jsonb")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_jsonb())
