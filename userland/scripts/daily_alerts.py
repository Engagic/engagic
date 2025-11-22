#!/usr/bin/env python3
"""
Daily Alerts Script

Run daily to:
1. Match all active alerts against recent meetings
2. Send email digests for new matches

Usage:
    python3 scripts/daily_alerts.py [--dry-run] [--since-days N]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from userland.matching.matcher import match_all_alerts_dual_track
from userland.email.emailer import send_daily_digests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("engagic")


def main():
    parser = argparse.ArgumentParser(description="Process daily civic alerts")
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Match alerts but don't send emails"
    )
    parser.add_argument(
        '--since-days',
        type=int,
        default=1,
        help="Only match items from last N days (default: 1)"
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Daily Alerts Processing")
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    logger.info(f"Time window: Last {args.since_days} day(s)")
    logger.info("=" * 60)

    # Step 1: Match all alerts
    logger.info("\nStep 1: Matching alerts against recent meetings...")
    try:
        matches = match_all_alerts_dual_track(since_days=args.since_days)

        total_string = sum(len(m["string_matches"]) for m in matches.values())
        total_matter = sum(len(m["matter_matches"]) for m in matches.values())

        logger.info("✓ Matching complete:")
        logger.info(f"  - String matches: {total_string}")
        logger.info(f"  - Matter matches: {total_matter}")
        logger.info(f"  - Total alerts processed: {len(matches)}")

    except Exception as e:
        logger.error(f"✗ Matching failed: {e}")
        return 1

    # Step 2: Send email digests (unless dry-run)
    if args.dry_run:
        logger.info("\nStep 2: SKIPPED (dry-run mode)")
        logger.info("Would have sent email digests for new matches")
    else:
        logger.info("\nStep 2: Sending email digests...")
        try:
            stats = send_daily_digests()

            logger.info("✓ Email delivery complete:")
            logger.info(f"  - Emails sent: {stats['emails_sent']}")
            logger.info(f"  - Items notified: {stats['items_notified']}")
            logger.info(f"  - Failed: {stats['failed']}")
            logger.info(f"  - Skipped: {stats['skipped']}")

        except Exception as e:
            logger.error(f"✗ Email delivery failed: {e}")
            return 1

    logger.info("\n" + "=" * 60)
    logger.info("Daily alerts processing complete!")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
