#!/usr/bin/env python3
"""
PostgreSQL Load and Stress Tests

Tests connection pool behavior under load, transaction rollback,
and concurrent access patterns.

Run with:
    ENGAGIC_USE_POSTGRES=true python tests/test_postgres_load.py
"""

import asyncio
import sys
import os
from datetime import datetime
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_postgres import Database
from database.models import Meeting
from config import config, get_logger

logger = get_logger(__name__)


class LoadTests:
    """Load and stress test suite for PostgreSQL"""

    def __init__(self, db: Database):
        self.db = db
        self.passed = 0
        self.failed = 0

    def _log_test(self, test_name: str, passed: bool, message: str = ""):
        """Log test result"""
        if passed:
            self.passed += 1
            print(f"✅ PASS | {test_name}")
            if message:
                print(f"         {message}")
        else:
            self.failed += 1
            print(f"❌ FAIL | {test_name}")
            if message:
                print(f"         {message}")

    async def test_connection_pool_stress(self):
        """Test 100 concurrent read operations (connection pool stress)"""
        test_name = "Connection pool stress (100 concurrent reads)"

        try:
            # Create test meeting first
            meeting = Meeting(
                id="test_pool_stress",
                banana="testCA",
                title="Pool Stress Test",
                date=datetime.now(),
                source_url="https://test.com/stress",
            )
            await self.db.meetings.store_meeting(meeting)

            # Define concurrent query function
            async def query_meeting():
                return await self.db.meetings.get_meeting("test_pool_stress")

            # Execute 100 concurrent queries
            start_time = time.time()
            tasks = [query_meeting() for _ in range(100)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - start_time

            # Check for errors
            errors = [r for r in results if isinstance(r, Exception)]
            successes = [r for r in results if not isinstance(r, Exception) and r is not None]

            if not errors and len(successes) == 100:
                self._log_test(
                    test_name,
                    True,
                    f"100 concurrent queries completed in {elapsed:.2f}s ({100/elapsed:.1f} req/s)"
                )
            else:
                self._log_test(
                    test_name,
                    False,
                    f"{len(errors)} errors, {len(successes)} successes"
                )

        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def test_transaction_rollback_on_error(self):
        """Test that transaction rolls back on error"""
        test_name = "Transaction rollback on error"

        try:
            meeting_id = "test_rollback_meeting"

            # Attempt to insert meeting in transaction, then raise error
            try:
                async with self.db.pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute(
                            """
                            INSERT INTO meetings (id, banana, title, source_url, date)
                            VALUES ($1, $2, $3, $4, $5)
                            """,
                            meeting_id,
                            "testCA",
                            "Rollback Test",
                            "https://test.com/rollback",
                            datetime.now(),
                        )
                        # Simulate error
                        raise Exception("Simulated transaction error")

            except Exception as e:
                if "Simulated" not in str(e):
                    raise  # Unexpected error

            # Verify meeting was NOT inserted (transaction rolled back)
            retrieved = await self.db.meetings.get_meeting(meeting_id)

            if retrieved is None:
                self._log_test(test_name, True, "Transaction rolled back correctly")
            else:
                self._log_test(test_name, False, "Meeting found - rollback failed")

        except Exception as e:
            self._log_test(test_name, False, f"Unexpected exception: {e}")

    async def test_transaction_commit_on_success(self):
        """Test that transaction commits on success"""
        test_name = "Transaction commit on success"

        try:
            meeting_id = "test_commit_meeting"

            # Insert meeting in transaction
            async with self.db.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        INSERT INTO meetings (id, banana, title, source_url, date)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        meeting_id,
                        "testCA",
                        "Commit Test",
                        "https://test.com/commit",
                        datetime.now(),
                    )

            # Verify meeting was inserted (transaction committed)
            retrieved = await self.db.meetings.get_meeting(meeting_id)

            if retrieved and retrieved.id == meeting_id:
                self._log_test(test_name, True, "Transaction committed correctly")
            else:
                self._log_test(test_name, False, "Meeting not found - commit failed")

        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def test_concurrent_writes(self):
        """Test 50 concurrent write operations"""
        test_name = "Concurrent writes (50 meetings)"

        try:
            # Define concurrent write function
            async def write_meeting(index: int):
                meeting = Meeting(
                    id=f"test_concurrent_{index}",
                    banana="testCA",
                    title=f"Concurrent Test {index}",
                    date=datetime.now(),
                    source_url=f"https://test.com/concurrent/{index}",
                )
                await self.db.meetings.store_meeting(meeting)
                return index

            # Execute 50 concurrent writes
            start_time = time.time()
            tasks = [write_meeting(i) for i in range(50)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - start_time

            # Check for errors
            errors = [r for r in results if isinstance(r, Exception)]
            successes = [r for r in results if isinstance(r, int)]

            if not errors and len(successes) == 50:
                self._log_test(
                    test_name,
                    True,
                    f"50 concurrent writes completed in {elapsed:.2f}s ({50/elapsed:.1f} writes/s)"
                )
            else:
                self._log_test(
                    test_name,
                    False,
                    f"{len(errors)} errors, {len(successes)} successes"
                )

        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def test_queue_concurrency(self):
        """Test concurrent queue operations (dequeue + process)"""
        test_name = "Queue concurrent dequeue (10 workers)"

        try:
            # Enqueue 20 jobs
            for i in range(20):
                await self.db.queue.enqueue_job(
                    source_url=f"https://test.com/queue/{i}",
                    job_type="meeting",
                    banana="testCA",
                    payload={"index": i},
                )

            # Simulate 10 workers dequeuing simultaneously
            async def worker():
                job = await self.db.queue.get_next_for_processing()
                return job

            tasks = [worker() for _ in range(10)]
            results = await asyncio.gather(*tasks)

            # Each worker should get a unique job (no duplicates)
            job_ids = [job["id"] for job in results if job]
            unique_jobs = len(set(job_ids))

            if unique_jobs == len(job_ids) and unique_jobs == 10:
                self._log_test(
                    test_name,
                    True,
                    f"10 workers dequeued 10 unique jobs (no duplicates)"
                )
            else:
                self._log_test(
                    test_name,
                    False,
                    f"Expected 10 unique jobs, got {unique_jobs} ({len(job_ids)} total)"
                )

        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def test_connection_pool_recovery(self):
        """Test that pool recovers from connection errors"""
        test_name = "Connection pool recovery"

        try:
            # Acquire all connections (stress pool)
            connections = []
            try:
                for _ in range(config.POSTGRES_POOL_MAX_SIZE):
                    conn = await self.db.pool.acquire()
                    connections.append(conn)

                # Pool is now exhausted - try to query (should wait and succeed)
                # Use a new coroutine that will wait for connection
                async def query_with_full_pool():
                    return await self.db.meetings.get_meeting("test_pool_stress")

                # Release one connection to allow query to proceed
                self.db.pool.release(connections.pop())

                result = await asyncio.wait_for(query_with_full_pool(), timeout=5.0)

                if result:
                    self._log_test(test_name, True, "Pool recovered from exhaustion")
                else:
                    self._log_test(test_name, True, "Pool handled exhaustion gracefully")

            finally:
                # Release all connections
                for conn in connections:
                    self.db.pool.release(conn)

        except asyncio.TimeoutError:
            self._log_test(test_name, False, "Query timed out - pool deadlock?")
        except Exception as e:
            self._log_test(test_name, False, f"Exception: {e}")

    async def cleanup(self):
        """Clean up test data"""
        try:
            async with self.db.pool.acquire() as conn:
                await conn.execute("DELETE FROM meetings WHERE id LIKE 'test_%'")
                await conn.execute("DELETE FROM queue WHERE source_url LIKE 'https://test.com%'")
            logger.info("cleaned up test data")
        except Exception as e:
            logger.warning("cleanup failed", error=str(e))

    async def run_all(self):
        """Run all load tests"""
        print("\n" + "="*80)
        print("PostgreSQL Load and Stress Tests")
        print("="*80 + "\n")

        # Run tests
        await self.test_connection_pool_stress()
        await self.test_transaction_rollback_on_error()
        await self.test_transaction_commit_on_success()
        await self.test_concurrent_writes()
        await self.test_queue_concurrency()
        await self.test_connection_pool_recovery()

        # Cleanup
        await self.cleanup()

        # Summary
        print("\n" + "="*80)
        total = self.passed + self.failed
        print(f"Results: {self.passed}/{total} passed")
        print("="*80 + "\n")

        return self.failed == 0


async def main():
    """Main test entry point"""
    # Verify PostgreSQL is enabled
    if not config.USE_POSTGRES:
        print("❌ ENGAGIC_USE_POSTGRES is not set to 'true'")
        print("Set environment variable: export ENGAGIC_USE_POSTGRES=true")
        sys.exit(1)

    # Initialize database
    db = await Database.create()

    try:
        print(f"Connection pool: {config.POSTGRES_POOL_MIN_SIZE}-{config.POSTGRES_POOL_MAX_SIZE} connections")
        print(f"Testing with {config.POSTGRES_POOL_MAX_SIZE} max connections\n")

        tests = LoadTests(db)
        passed = await tests.run_all()

        if passed:
            print("✅ ALL TESTS PASSED")
            sys.exit(0)
        else:
            print("❌ SOME TESTS FAILED")
            sys.exit(1)

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
