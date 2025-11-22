"""
Keyword matching engine for userland alerts.

Uses engagic's database directly for efficient SQL-based matching.
Dual-track matching: string-based (granular) + matter-based (deduplicated)
"""

import logging
import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from uuid import uuid4

from userland.database.models import Alert, AlertMatch
from userland.database.db import UserlandDB

logger = logging.getLogger("engagic")


def get_engagic_connection() -> sqlite3.Connection:
    """Get read-only connection to engagic database"""
    engagic_db_path = os.getenv('ENGAGIC_UNIFIED_DB', '/root/engagic/data/engagic.db')
    conn = sqlite3.connect(f"file:{engagic_db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def match_alert(
    alert: Alert,
    since_days: int = 1,
    db: Optional[UserlandDB] = None
) -> List[AlertMatch]:
    """
    Match an alert against recent summaries (string-based matching).

    Args:
        alert: Alert configuration with keywords
        since_days: Only match items from last N days
        db: UserlandDB instance (optional, for deduplication)

    Returns:
        List of AlertMatch objects
    """
    if not alert.active:
        logger.debug(f"Alert {alert.name} is inactive, skipping")
        return []

    keywords = alert.criteria.get("keywords", [])
    if not keywords:
        logger.info(f"Alert {alert.name} has no keywords, skipping")
        return []

    cutoff_date = (datetime.now() - timedelta(days=since_days)).isoformat()
    matches = []
    seen_items = set()

    logger.info(
        f"Matching alert '{alert.name}': "
        f"{len(keywords)} keywords, {len(alert.cities)} cities"
    )

    conn = get_engagic_connection()

    for keyword in keywords:
        logger.debug(f"Searching for keyword: '{keyword}'")

        for city_banana in alert.cities:
            # Search items table for keyword matches
            query = """
                SELECT i.id, i.meeting_id, i.title, i.summary,
                       m.title as meeting_title, m.date, m.banana,
                       c.name as city_name, c.state
                FROM items i
                JOIN meetings m ON i.meeting_id = m.id
                JOIN cities c ON m.banana = c.banana
                WHERE m.banana = ?
                  AND m.date >= ?
                  AND i.summary LIKE ?
                ORDER BY m.date DESC
            """

            rows = conn.execute(query, (city_banana, cutoff_date, f"%{keyword}%")).fetchall()

            for row in rows:
                item_id = row['id']
                meeting_id = row['meeting_id']

                # Deduplicate by item_id
                if item_id in seen_items:
                    continue
                seen_items.add(item_id)

                # Check if already notified (if db provided)
                if db:
                    existing = db.conn.execute(
                        "SELECT id FROM alert_matches WHERE alert_id = ? AND item_id = ?",
                        (alert.id, item_id)
                    ).fetchone()

                    if existing:
                        logger.debug(f"Already matched: {item_id}")
                        continue

                # Extract clean summary (skip thinking section)
                summary = row['summary'] or ""
                if "## Summary" in summary:
                    summary = summary.split("## Summary", 1)[1].split("##", 1)[0].strip()

                # Build URL
                url = f"https://engagic.org/{row['banana']}/{meeting_id}#item-{item_id}"

                # Create match
                match = AlertMatch(
                    id=str(uuid4()),
                    alert_id=alert.id,
                    meeting_id=meeting_id,
                    item_id=item_id,
                    match_type="keyword",
                    confidence=1.0,
                    matched_criteria={
                        "keyword": keyword,
                        "city": f"{row['city_name']}, {row['state']}",
                        "date": row['date'],
                        "meeting_title": row['meeting_title'],
                        "item_title": row['title'],
                        "context": summary[:300],
                        "url": url
                    }
                )

                matches.append(match)
                logger.debug(f"Match: {row['city_name']} - {row['title'][:50]}")

    conn.close()
    logger.info(f"Alert '{alert.name}': {len(matches)} new matches")
    return matches


def match_matters_for_alert(
    alert: Alert,
    since_days: int = 1,
    db: Optional[UserlandDB] = None
) -> List[AlertMatch]:
    """
    Match alert against matters (deduplicated, matter-first).

    Benefits:
    - Deduplication: Same bill in 5 committees = 1 alert (not 5)
    - Timeline tracking: Show bill evolution across committees
    - Canonical summaries: High-quality deduplicated summaries

    Args:
        alert: Alert configuration with keywords
        since_days: Only match matters seen in last N days
        db: UserlandDB instance (optional, for deduplication)

    Returns:
        List of AlertMatch objects (one per matter, not per appearance)
    """
    if not alert.active:
        logger.debug(f"Alert {alert.name} is inactive, skipping")
        return []

    keywords = alert.criteria.get("keywords", [])
    if not keywords:
        logger.info(f"Alert {alert.name} has no keywords, skipping")
        return []

    cutoff_date = (datetime.now() - timedelta(days=since_days)).isoformat()
    matches = []
    seen_matters = set()

    logger.info(f"Matter matching for '{alert.name}': {len(keywords)} keywords, {len(alert.cities)} cities")

    conn = get_engagic_connection()

    for keyword in keywords:
        logger.debug(f"Searching matters for keyword: '{keyword}'")

        # Search city_matters for keyword matches
        cities_placeholder = ','.join('?' * len(alert.cities))
        query = f"""
            SELECT cm.id, cm.banana, cm.matter_file, cm.matter_type,
                   cm.title, cm.canonical_summary, cm.sponsors,
                   cm.canonical_topics, cm.first_seen, cm.last_seen,
                   cm.appearance_count,
                   c.name as city_name, c.state
            FROM city_matters cm
            JOIN cities c ON cm.banana = c.banana
            WHERE cm.banana IN ({cities_placeholder})
              AND cm.last_seen >= ?
              AND cm.canonical_summary LIKE ?
            ORDER BY cm.last_seen DESC
        """

        params = list(alert.cities) + [cutoff_date, f"%{keyword}%"]
        rows = conn.execute(query, params).fetchall()

        for row in rows:
            matter_id = row['id']

            # Deduplicate by matter_id
            if matter_id in seen_matters:
                continue
            seen_matters.add(matter_id)

            # Check if already notified (if db provided)
            if db:
                # Use SQLite JSON functions for reliable JSON querying
                existing = db.conn.execute(
                    """
                    SELECT id FROM alert_matches
                    WHERE alert_id = ?
                      AND json_extract(matched_criteria, '$.matter_id') = ?
                    """,
                    (alert.id, matter_id)
                ).fetchone()

                if existing:
                    logger.debug(f"Already matched matter: {matter_id}")
                    continue

            # Get matter appearances for timeline
            timeline_query = """
                SELECT ma.appeared_at, ma.committee, ma.action,
                       ma.item_id, ma.meeting_id,
                       m.title as meeting_title
                FROM matter_appearances ma
                JOIN meetings m ON ma.meeting_id = m.id
                WHERE ma.matter_id = ?
                ORDER BY ma.appeared_at
            """
            appearances = conn.execute(timeline_query, (matter_id,)).fetchall()

            # Build timeline
            timeline = []
            for app in appearances:
                timeline.append({
                    "date": app["appeared_at"],
                    "committee": app["committee"],
                    "action": app["action"],
                    "meeting_title": app["meeting_title"]
                })

            # Use most recent appearance for URL
            latest = appearances[-1] if appearances else None
            url = None
            item_id = None
            meeting_id = None

            if latest:
                item_id = latest['item_id']
                meeting_id = latest['meeting_id']
                url = f"https://engagic.org/{row['banana']}/{meeting_id}#item-{item_id}"

            # Create match
            match = AlertMatch(
                id=str(uuid4()),
                alert_id=alert.id,
                meeting_id=meeting_id or "",
                item_id=item_id,
                match_type="matter",
                confidence=1.0,
                matched_criteria={
                    "keyword": keyword,
                    "matter_id": matter_id,
                    "matter_file": row['matter_file'],
                    "matter_type": row['matter_type'],
                    "title": row['title'],
                    "city": f"{row['city_name']}, {row['state']}",
                    "canonical_summary": row['canonical_summary'],
                    "sponsors": row['sponsors'],
                    "topics": row['canonical_topics'],
                    "first_seen": row['first_seen'],
                    "last_seen": row['last_seen'],
                    "appearance_count": row['appearance_count'],
                    "timeline": timeline,
                    "url": url
                }
            )

            matches.append(match)
            logger.debug(
                f"Matter match: {row['city_name']} - "
                f"{row['matter_file']} ({row['appearance_count']} appearances)"
            )

    conn.close()
    logger.info(f"Alert '{alert.name}': {len(matches)} new matter matches")
    return matches


def match_all_alerts_dual_track(
    since_days: int = 1,
    db_path: Optional[str] = None
) -> Dict[str, Dict[str, List[AlertMatch]]]:
    """
    Match all active alerts using BOTH string and matter backends.

    Always runs both:
    - String matches: Granular item-level mentions
    - Matter matches: Deduplicated legislative tracking

    Args:
        since_days: Only match items/matters from last N days
        db_path: Path to userland database

    Returns:
        Dict with structure:
        {
            alert_id: {
                "string_matches": [AlertMatch, ...],
                "matter_matches": [AlertMatch, ...]
            }
        }
    """
    db = UserlandDB(db_path) if db_path else UserlandDB(
        os.getenv('USERLAND_DB', '/root/engagic/data/userland.db')
    )

    active_alerts = db.get_active_alerts()
    logger.info(f"Processing {len(active_alerts)} active alerts (dual-track: string + matter)")

    all_matches = {}

    for alert in active_alerts:
        # String backend (granular item-level)
        string_matches = match_alert(alert, since_days=since_days, db=db)

        # Matter backend (deduplicated legislative)
        matter_matches = match_matters_for_alert(alert, since_days=since_days, db=db)

        # Store all matches in database
        for match in string_matches + matter_matches:
            db.create_match(match)

        all_matches[alert.id] = {
            "string_matches": string_matches,
            "matter_matches": matter_matches
        }

    total_string = sum(len(m["string_matches"]) for m in all_matches.values())
    total_matter = sum(len(m["matter_matches"]) for m in all_matches.values())
    logger.info(f"Dual-track complete: {total_string} string matches, {total_matter} matter matches")

    db.close()
    return all_matches
