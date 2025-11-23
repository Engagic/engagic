#!/usr/bin/env python3
"""
PostgreSQL Migration Validation Script

Validates data integrity after SQLite → PostgreSQL migration.

Checks:
1. Foreign key integrity (orphaned records)
2. JSONB field validity (sampling)
3. Topic normalization accuracy
4. Cross-city matter collision detection
5. Row count verification

Usage:
    python scripts/validate_migration.py

Environment:
    ENGAGIC_USE_POSTGRES=true
    ENGAGIC_POSTGRES_HOST=localhost
    ENGAGIC_POSTGRES_DB=engagic
"""

import asyncio
import json
import sys
import os
from typing import Dict, List, Tuple
from dataclasses import dataclass, field

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_postgres import Database
from config import config, get_logger

logger = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of a validation check"""
    check_name: str
    passed: bool
    message: str
    details: Dict = field(default_factory=dict)

    def __str__(self) -> str:
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"{status} | {self.check_name}: {self.message}"


class MigrationValidator:
    """Validates PostgreSQL migration data integrity"""

    def __init__(self, db: Database):
        self.db = db
        self.results: List[ValidationResult] = []

    async def run_all_checks(self) -> bool:
        """Run all validation checks

        Returns:
            True if all checks pass, False otherwise
        """
        logger.info("starting migration validation")

        checks = [
            self.check_foreign_key_integrity(),
            self.check_jsonb_validity(),
            self.check_topic_normalization(),
            self.check_matter_cross_city_collisions(),
            self.check_row_counts(),
        ]

        for check in checks:
            result = await check
            self.results.append(result)
            print(result)

        passed = all(r.passed for r in self.results)
        logger.info(
            "validation complete",
            total_checks=len(self.results),
            passed=sum(1 for r in self.results if r.passed),
            failed=sum(1 for r in self.results if not r.passed),
        )

        return passed

    async def check_foreign_key_integrity(self) -> ValidationResult:
        """Check for orphaned records (foreign key violations)"""
        logger.info("checking foreign key integrity")

        try:
            async with self.db.pool.acquire() as conn:
                # Check orphaned items (meeting_id not in meetings)
                orphaned_items = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM agenda_items
                    WHERE meeting_id NOT IN (SELECT id FROM meetings)
                    """
                )

                # Check orphaned meetings (banana not in cities)
                orphaned_meetings = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM meetings
                    WHERE banana NOT IN (SELECT banana FROM cities)
                    """
                )

                # Check orphaned matter references (items.matter_id not in city_matters)
                orphaned_matter_refs = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM agenda_items
                    WHERE matter_id IS NOT NULL
                        AND matter_id NOT IN (SELECT id FROM city_matters)
                    """
                )

                # Check orphaned matter appearances (matter_id not in city_matters)
                orphaned_appearances = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM matter_appearances
                    WHERE matter_id NOT IN (SELECT id FROM city_matters)
                    """
                )

                total_orphans = (
                    orphaned_items +
                    orphaned_meetings +
                    orphaned_matter_refs +
                    orphaned_appearances
                )

                details = {
                    "orphaned_items": orphaned_items,
                    "orphaned_meetings": orphaned_meetings,
                    "orphaned_matter_refs": orphaned_matter_refs,
                    "orphaned_appearances": orphaned_appearances,
                }

                if total_orphans == 0:
                    return ValidationResult(
                        check_name="Foreign Key Integrity",
                        passed=True,
                        message="No orphaned records found",
                        details=details,
                    )
                else:
                    return ValidationResult(
                        check_name="Foreign Key Integrity",
                        passed=False,
                        message=f"Found {total_orphans} orphaned records",
                        details=details,
                    )

        except Exception as e:
            logger.error("foreign key check failed", error=str(e))
            return ValidationResult(
                check_name="Foreign Key Integrity",
                passed=False,
                message=f"Check failed with error: {e}",
            )

    async def check_jsonb_validity(self) -> ValidationResult:
        """Sample JSONB fields to verify they parse correctly"""
        logger.info("checking JSONB field validity")

        try:
            async with self.db.pool.acquire() as conn:
                # Sample 100 random meetings with participation
                meetings_sample = await conn.fetch(
                    """
                    SELECT id, participation
                    FROM meetings
                    WHERE participation IS NOT NULL
                    ORDER BY RANDOM()
                    LIMIT 100
                    """
                )

                # Sample 100 random items with attachments or sponsors
                items_sample = await conn.fetch(
                    """
                    SELECT id, attachments, sponsors
                    FROM agenda_items
                    WHERE attachments IS NOT NULL OR sponsors IS NOT NULL
                    ORDER BY RANDOM()
                    LIMIT 100
                    """
                )

                # Sample 50 random matters with attachments or sponsors
                matters_sample = await conn.fetch(
                    """
                    SELECT id, attachments, sponsors, metadata
                    FROM city_matters
                    WHERE attachments IS NOT NULL OR sponsors IS NOT NULL OR metadata IS NOT NULL
                    ORDER BY RANDOM()
                    LIMIT 50
                    """
                )

                errors = []

                # Validate meeting participation (already JSONB, just check structure)
                for row in meetings_sample:
                    if row["participation"]:
                        # asyncpg already parsed it - verify structure
                        if not isinstance(row["participation"], dict):
                            errors.append(f"Meeting {row['id']}: participation not a dict")

                # Validate item fields
                for row in items_sample:
                    if row["attachments"]:
                        if not isinstance(row["attachments"], list):
                            errors.append(f"Item {row['id']}: attachments not a list")
                    if row["sponsors"]:
                        if not isinstance(row["sponsors"], list):
                            errors.append(f"Item {row['id']}: sponsors not a list")

                # Validate matter fields
                for row in matters_sample:
                    if row["attachments"]:
                        if not isinstance(row["attachments"], list):
                            errors.append(f"Matter {row['id']}: attachments not a list")
                    if row["sponsors"]:
                        if not isinstance(row["sponsors"], list):
                            errors.append(f"Matter {row['id']}: sponsors not a list")
                    if row["metadata"]:
                        if not isinstance(row["metadata"], dict):
                            errors.append(f"Matter {row['id']}: metadata not a dict")

                total_sampled = len(meetings_sample) + len(items_sample) + len(matters_sample)

                if not errors:
                    return ValidationResult(
                        check_name="JSONB Validity",
                        passed=True,
                        message=f"All {total_sampled} sampled JSONB fields valid",
                        details={"sampled": total_sampled, "errors": 0},
                    )
                else:
                    return ValidationResult(
                        check_name="JSONB Validity",
                        passed=False,
                        message=f"Found {len(errors)} invalid JSONB fields",
                        details={"sampled": total_sampled, "errors": errors[:10]},  # First 10 errors
                    )

        except Exception as e:
            logger.error("JSONB validation failed", error=str(e))
            return ValidationResult(
                check_name="JSONB Validity",
                passed=False,
                message=f"Check failed with error: {e}",
            )

    async def check_topic_normalization(self) -> ValidationResult:
        """Verify topic normalization accuracy"""
        logger.info("checking topic normalization")

        try:
            async with self.db.pool.acquire() as conn:
                # Check meeting topics consistency
                meeting_topic_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM meeting_topics"
                )

                # Check item topics consistency
                item_topic_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM item_topics"
                )

                # Check matter topics consistency
                matter_topic_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM matter_topics"
                )

                # Verify no orphaned topic records
                orphaned_meeting_topics = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM meeting_topics
                    WHERE meeting_id NOT IN (SELECT id FROM meetings)
                    """
                )

                orphaned_item_topics = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM item_topics
                    WHERE item_id NOT IN (SELECT id FROM agenda_items)
                    """
                )

                orphaned_matter_topics = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM matter_topics
                    WHERE matter_id NOT IN (SELECT id FROM city_matters)
                    """
                )

                total_orphaned_topics = (
                    orphaned_meeting_topics +
                    orphaned_item_topics +
                    orphaned_matter_topics
                )

                details = {
                    "meeting_topics": meeting_topic_count,
                    "item_topics": item_topic_count,
                    "matter_topics": matter_topic_count,
                    "orphaned_meeting_topics": orphaned_meeting_topics,
                    "orphaned_item_topics": orphaned_item_topics,
                    "orphaned_matter_topics": orphaned_matter_topics,
                }

                if total_orphaned_topics == 0:
                    return ValidationResult(
                        check_name="Topic Normalization",
                        passed=True,
                        message=f"All topic tables consistent ({meeting_topic_count + item_topic_count + matter_topic_count} total topics)",
                        details=details,
                    )
                else:
                    return ValidationResult(
                        check_name="Topic Normalization",
                        passed=False,
                        message=f"Found {total_orphaned_topics} orphaned topic records",
                        details=details,
                    )

        except Exception as e:
            logger.error("topic normalization check failed", error=str(e))
            return ValidationResult(
                check_name="Topic Normalization",
                passed=False,
                message=f"Check failed with error: {e}",
            )

    async def check_matter_cross_city_collisions(self) -> ValidationResult:
        """Check for cross-city matter ID collisions"""
        logger.info("checking matter cross-city collisions")

        try:
            async with self.db.pool.acquire() as conn:
                # Check for matter_file duplicates across different cities
                duplicates = await conn.fetch(
                    """
                    SELECT matter_file, array_agg(DISTINCT banana) as cities, COUNT(DISTINCT banana) as city_count
                    FROM city_matters
                    WHERE matter_file IS NOT NULL
                    GROUP BY matter_file
                    HAVING COUNT(DISTINCT banana) > 1
                    LIMIT 10
                    """
                )

                if not duplicates:
                    return ValidationResult(
                        check_name="Matter Cross-City Collisions",
                        passed=True,
                        message="No cross-city matter_file collisions detected",
                        details={"duplicates_found": 0},
                    )
                else:
                    # This might be legitimate (same ordinance number in different cities)
                    # but worth flagging
                    collision_details = [
                        {"matter_file": row["matter_file"], "cities": row["cities"], "count": row["city_count"]}
                        for row in duplicates
                    ]
                    return ValidationResult(
                        check_name="Matter Cross-City Collisions",
                        passed=True,  # Warning, not failure
                        message=f"Found {len(duplicates)} matter_file values shared across cities (may be legitimate)",
                        details={"collisions": collision_details},
                    )

        except Exception as e:
            logger.error("cross-city collision check failed", error=str(e))
            return ValidationResult(
                check_name="Matter Cross-City Collisions",
                passed=False,
                message=f"Check failed with error: {e}",
            )

    async def check_row_counts(self) -> ValidationResult:
        """Verify row counts in main tables"""
        logger.info("checking row counts")

        try:
            async with self.db.pool.acquire() as conn:
                cities_count = await conn.fetchval("SELECT COUNT(*) FROM cities")
                meetings_count = await conn.fetchval("SELECT COUNT(*) FROM meetings")
                items_count = await conn.fetchval("SELECT COUNT(*) FROM agenda_items")
                matters_count = await conn.fetchval("SELECT COUNT(*) FROM city_matters")
                queue_count = await conn.fetchval("SELECT COUNT(*) FROM queue")

                details = {
                    "cities": cities_count,
                    "meetings": meetings_count,
                    "agenda_items": items_count,
                    "city_matters": matters_count,
                    "queue": queue_count,
                }

                # Basic sanity checks
                issues = []
                if cities_count == 0:
                    issues.append("No cities found")
                if meetings_count == 0:
                    issues.append("No meetings found")
                if items_count < meetings_count:
                    issues.append("Fewer items than meetings (suspicious)")

                if issues:
                    return ValidationResult(
                        check_name="Row Counts",
                        passed=False,
                        message=f"Row count issues: {', '.join(issues)}",
                        details=details,
                    )
                else:
                    return ValidationResult(
                        check_name="Row Counts",
                        passed=True,
                        message=f"Row counts reasonable ({cities_count} cities, {meetings_count} meetings, {items_count} items)",
                        details=details,
                    )

        except Exception as e:
            logger.error("row count check failed", error=str(e))
            return ValidationResult(
                check_name="Row Counts",
                passed=False,
                message=f"Check failed with error: {e}",
            )


async def main():
    """Main validation entry point"""
    print("\n" + "="*80)
    print("PostgreSQL Migration Validation")
    print("="*80 + "\n")

    # Verify PostgreSQL is enabled
    if not config.USE_POSTGRES:
        print("❌ ENGAGIC_USE_POSTGRES is not set to 'true'")
        print("Set environment variable: export ENGAGIC_USE_POSTGRES=true")
        sys.exit(1)

    # Initialize database
    db = await Database.create()

    try:
        validator = MigrationValidator(db)
        passed = await validator.run_all_checks()

        print("\n" + "="*80)
        if passed:
            print("✅ ALL VALIDATION CHECKS PASSED")
            print("="*80 + "\n")
            sys.exit(0)
        else:
            print("❌ SOME VALIDATION CHECKS FAILED")
            print("="*80 + "\n")
            print("Review failed checks above for details.")
            sys.exit(1)

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
