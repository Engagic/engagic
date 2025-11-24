#!/usr/bin/env python3
"""
Create User Script

Manually create a user account (admin utility).

Usage:
    python3 -m userland.scripts.create_user --email user@example.com --name "John Doe"
"""

import argparse
import asyncio
import logging
import secrets
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database.db_postgres import Database
from userland.database.models import User, Alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("engagic")


async def main():
    parser = argparse.ArgumentParser(description="Create a new user account")
    parser.add_argument('--email', required=True, help="User email address")
    parser.add_argument('--name', required=True, help="User name")
    parser.add_argument('--cities', nargs='+', help="Optional: Cities to track (e.g., paloaltoCA nashvilleTN)")
    parser.add_argument('--keywords', nargs='+', help="Optional: Keywords to track (e.g., housing zoning)")
    args = parser.parse_args()

    logger.info("Creating new user account...")
    logger.info(f"  Email: {args.email}")
    logger.info(f"  Name: {args.name}")

    db = await Database.create()
    try:
        # Check if user already exists
        existing = await db.userland.get_user_by_email(args.email)
        if existing:
            logger.error(f"User with email {args.email} already exists!")
            return 1

        # Create user
        user_id = secrets.token_urlsafe(16)
        user = User(
            id=user_id,
            name=args.name,
            email=args.email
        )

        try:
            await db.userland.create_user(user)
            logger.info(f"User created: {user.id}")

            # Create alert if cities and keywords provided
            if args.cities and args.keywords:
                alert = Alert(
                    id=secrets.token_urlsafe(16),
                    user_id=user_id,
                    name=f"{args.name}'s Alert",
                    cities=args.cities,
                    criteria={"keywords": args.keywords},
                    frequency="weekly",
                    active=True
                )
                await db.userland.create_alert(alert)
                logger.info(f"Alert created: {alert.id}")
                logger.info(f"  Cities: {', '.join(args.cities)}")
                logger.info(f"  Keywords: {', '.join(args.keywords)}")

            logger.info("\nUser account created successfully!")
            logger.info("User can log in at: https://engagic.org/login")

        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            return 1

        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
