"""
Keyword matching engine for userland alerts.

Uses engagic's database directly for efficient SQL-based matching.
Dual-track matching: string-based (granular) + matter-based (deduplicated)
"""

from datetime import datetime, timedelta
from typing import List, Dict
from uuid import uuid4

from config import get_logger
from database.db_postgres import Database
from userland.database.models import Alert, AlertMatch

logger = get_logger(__name__)


async def match_alert(
    alert: Alert,
    db: Database,
    since_days: int = 1
) -> List[AlertMatch]:
    """
    Match an alert against recent summaries (string-based matching).

    Args:
        alert: Alert configuration with keywords
        db: Database instance (for both engagic and userland queries)
        since_days: Only match items from last N days

    Returns:
        List of AlertMatch objects
    """
    if not alert.active:
        logger.debug("alert inactive, skipping", alert_name=alert.name)
        return []

    keywords = alert.criteria.get("keywords", [])
    if not keywords:
        logger.info("alert has no keywords, skipping", alert_name=alert.name)
        return []

    cutoff_date = (datetime.now() - timedelta(days=since_days)).isoformat()
    matches = []
    seen_items = set()

    logger.info(
        "matching alert",
        alert_name=alert.name,
        keyword_count=len(keywords),
        city_count=len(alert.cities)
    )

    async with db.pool.acquire() as conn:
        for keyword in keywords:
            logger.debug("searching for keyword", keyword=keyword)

            for city_banana in alert.cities:
                # Search items table for keyword matches
                query = """
                    SELECT i.id, i.meeting_id, i.title, i.summary,
                           m.title as meeting_title, m.date, m.banana,
                           c.name as city_name, c.state
                    FROM items i
                    JOIN meetings m ON i.meeting_id = m.id
                    JOIN cities c ON m.banana = c.banana
                    WHERE m.banana = $1
                      AND m.date >= $2
                      AND (m.status IS NULL OR m.status NOT IN ('cancelled', 'postponed'))
                      AND i.summary LIKE $3
                    ORDER BY m.date DESC
                """

                rows = await conn.fetch(query, city_banana, cutoff_date, f"%{keyword}%")

                for row in rows:
                    item_id = row['id']
                    meeting_id = row['meeting_id']

                    # Deduplicate by item_id
                    if item_id in seen_items:
                        continue
                    seen_items.add(item_id)

                    # Check if already notified
                    existing_matches = await db.userland.get_matches(
                        alert_id=alert.id,
                        limit=1000
                    )
                    if any(m.item_id == item_id for m in existing_matches):
                        logger.debug("already matched", item_id=item_id)
                        continue

                    # Extract clean summary (skip thinking section)
                    summary = row['summary'] or ""
                    if "## Summary" in summary:
                        summary = summary.split("## Summary", 1)[1].split("##", 1)[0].strip()

                    meeting_date = row['date']
                    meeting_slug = f"{meeting_date}-{meeting_id}"
                    url = f"https://engagic.org/{row['banana']}/{meeting_slug}?item=item-{item_id}"

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
                            "date": str(row['date']),
                            "meeting_title": row['meeting_title'],
                            "item_title": row['title'],
                            "context": summary[:300],
                            "url": url
                        }
                    )

                    matches.append(match)
                    logger.debug("match found", city_name=row['city_name'], title=row['title'][:50])

    logger.info("alert matching complete", alert_name=alert.name, match_count=len(matches))
    return matches


async def match_matters_for_alert(
    alert: Alert,
    db: Database,
    since_days: int = 1
) -> List[AlertMatch]:
    """
    Match alert against matters (deduplicated, matter-first).

    Benefits:
    - Deduplication: Same bill in 5 committees = 1 alert (not 5)
    - Timeline tracking: Show bill evolution across committees
    - Canonical summaries: High-quality deduplicated summaries

    Args:
        alert: Alert configuration with keywords
        db: Database instance
        since_days: Only match matters seen in last N days

    Returns:
        List of AlertMatch objects (one per matter, not per appearance)
    """
    if not alert.active:
        logger.debug("alert inactive, skipping matter match", alert_name=alert.name)
        return []

    keywords = alert.criteria.get("keywords", [])
    if not keywords:
        logger.info("alert has no keywords, skipping matter match", alert_name=alert.name)
        return []

    cutoff_date = (datetime.now() - timedelta(days=since_days)).isoformat()
    matches = []
    seen_matters = set()

    logger.info("matter matching for alert", alert_name=alert.name, keyword_count=len(keywords), city_count=len(alert.cities))

    async with db.pool.acquire() as conn:
        for keyword in keywords:
            logger.debug("searching matters for keyword", keyword=keyword)

            # Search city_matters for keyword matches
            cities_placeholder = ','.join(f'${i+1}' for i in range(len(alert.cities)))
            query = f"""
                SELECT cm.id, cm.banana, cm.matter_file, cm.matter_type,
                       cm.title, cm.canonical_summary, cm.sponsors,
                       cm.canonical_topics, cm.first_seen, cm.last_seen,
                       cm.appearance_count,
                       c.name as city_name, c.state
                FROM city_matters cm
                JOIN cities c ON cm.banana = c.banana
                WHERE cm.banana IN ({cities_placeholder})
                  AND cm.last_seen >= ${len(alert.cities) + 1}
                  AND cm.canonical_summary LIKE ${len(alert.cities) + 2}
                ORDER BY cm.last_seen DESC
            """

            params = list(alert.cities) + [cutoff_date, f"%{keyword}%"]
            rows = await conn.fetch(query, *params)

            for row in rows:
                matter_id = row['id']

                # Deduplicate by matter_id
                if matter_id in seen_matters:
                    continue
                seen_matters.add(matter_id)

                # Check if already notified using PostgreSQL JSON operator
                existing_check = await conn.fetchrow(
                    """
                    SELECT id FROM userland.alert_matches
                    WHERE alert_id = $1
                      AND matched_criteria->>'matter_id' = $2
                    """,
                    alert.id, matter_id
                )

                if existing_check:
                    logger.debug("already matched matter", matter_id=matter_id)
                    continue

                # Get matter appearances for timeline
                timeline_query = """
                    SELECT ma.appeared_at, ma.committee, ma.action,
                           ma.item_id, ma.meeting_id,
                           m.title as meeting_title
                    FROM matter_appearances ma
                    JOIN meetings m ON ma.meeting_id = m.id
                    WHERE ma.matter_id = $1
                      AND (m.status IS NULL OR m.status NOT IN ('cancelled', 'postponed'))
                    ORDER BY ma.appeared_at
                """
                appearances = await conn.fetch(timeline_query, matter_id)

                # Build timeline
                timeline = []
                for app in appearances:
                    timeline.append({
                        "date": str(app["appeared_at"]),
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
                    meeting_date = latest['appeared_at']
                    meeting_slug = f"{meeting_date}-{meeting_id}"
                    url = f"https://engagic.org/{row['banana']}/{meeting_slug}?item=item-{item_id}"

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
                        "first_seen": str(row['first_seen']),
                        "last_seen": str(row['last_seen']),
                        "appearance_count": row['appearance_count'],
                        "timeline": timeline,
                        "url": url
                    }
                )

                matches.append(match)
                logger.debug(
                    "matter match found",
                    city_name=row['city_name'],
                    matter_file=row['matter_file'],
                    appearance_count=row['appearance_count']
                )

    logger.info("matter matching complete", alert_name=alert.name, match_count=len(matches))
    return matches


async def match_all_alerts_dual_track(
    db: Database,
    since_days: int = 1
) -> Dict[str, Dict[str, List[AlertMatch]]]:
    """
    Match all active alerts using BOTH string and matter backends.

    Always runs both:
    - String matches: Granular item-level mentions
    - Matter matches: Deduplicated legislative tracking

    Args:
        db: Database instance (async PostgreSQL)
        since_days: Only match items/matters from last N days

    Returns:
        Dict with structure:
        {
            alert_id: {
                "string_matches": [AlertMatch, ...],
                "matter_matches": [AlertMatch, ...]
            }
        }
    """
    active_alerts = await db.userland.get_active_alerts()
    logger.info("processing active alerts dual-track", count=len(active_alerts))

    all_matches = {}

    for alert in active_alerts:
        # String backend (granular item-level)
        string_matches = await match_alert(alert, db=db, since_days=since_days)

        # Matter backend (deduplicated legislative)
        matter_matches = await match_matters_for_alert(alert, db=db, since_days=since_days)

        # Store all matches in database
        for match in string_matches + matter_matches:
            await db.userland.create_match(match)

        all_matches[alert.id] = {
            "string_matches": string_matches,
            "matter_matches": matter_matches
        }

    total_string = sum(len(m["string_matches"]) for m in all_matches.values())
    total_matter = sum(len(m["matter_matches"]) for m in all_matches.values())
    logger.info("dual-track matching complete", string_matches=total_string, matter_matches=total_matter)

    return all_matches
