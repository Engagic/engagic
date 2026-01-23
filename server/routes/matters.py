"""Matter API routes - handles matter tracking, timelines, and cross-meeting aggregation."""

import random
from fastapi import APIRouter, HTTPException, Depends
from server.metrics import metrics
from server.dependencies import get_db
from server.utils.text import extract_context
from database.db_postgres import Database

from config import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix="/api")


@router.get("/matters/{matter_id}/timeline")
async def get_matter_timeline(matter_id: str, db: Database = Depends(get_db)):
    """Get timeline of a matter across multiple meetings

    Returns all appearances of this matter with meeting context
    """
    try:
        # Get the canonical matter record
        matter = await db.get_matter(matter_id)

        if not matter:
            raise HTTPException(status_code=404, detail="Matter not found")

        # Track matter engagement
        metrics.page_views.labels(page_type='matter').inc()
        metrics.matter_engagement.labels(action='timeline').inc()

        # Get all items for this matter across meetings with committee context (async PostgreSQL)
        async with db.pool.acquire() as conn:
            items = await conn.fetch(
                """
                SELECT
                    i.*,
                    m.title as meeting_title,
                    m.date as meeting_date,
                    m.banana,
                    c.name as city_name,
                    c.state,
                    ma.committee,
                    ma.committee_id,
                    ma.vote_outcome,
                    ma.vote_tally,
                    cm.name as committee_name
                FROM items i
                JOIN meetings m ON i.meeting_id = m.id
                JOIN cities c ON m.banana = c.banana
                LEFT JOIN matter_appearances ma ON ma.item_id = i.id AND ma.matter_id = i.matter_id
                LEFT JOIN committees cm ON ma.committee_id = cm.id
                WHERE i.matter_id = $1
                ORDER BY m.date ASC, i.sequence ASC
                """,
                matter.id
            )

        if not items:
            raise HTTPException(status_code=404, detail="No items found for this matter")

        # Transform into timeline structure
        timeline = []
        for item in items:
            timeline.append({
                "item_id": item["id"],
                "meeting_id": item["meeting_id"],
                "meeting_title": item["meeting_title"],
                "meeting_date": item["meeting_date"],
                "city_name": item["city_name"],
                "state": item["state"],
                "banana": item["banana"],
                "agenda_number": item["agenda_number"],
                "summary": item["summary"],
                "topics": item["topics"] or [],
                "committee": item["committee_name"] or item["committee"],
                "committee_id": item["committee_id"],
                "vote_outcome": item["vote_outcome"],
                "vote_tally": item["vote_tally"]
            })

        return {
            "success": True,
            "matter": matter.to_dict(),
            "timeline": timeline,
            "appearance_count": len(timeline)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error fetching matter timeline", matter_id=matter_id, error=str(e))
        raise HTTPException(status_code=500, detail="Error retrieving matter timeline")


@router.get("/matters/{matter_id}/sponsors")
async def get_matter_sponsors(matter_id: str, db: Database = Depends(get_db)):
    """Get sponsors for a specific matter.

    Returns enriched council member data (IDs, names, stats) for just this matter's sponsors.
    Much more efficient than fetching all council members for a city.
    """
    try:
        # Verify matter exists
        matter = await db.get_matter(matter_id)
        if not matter:
            raise HTTPException(status_code=404, detail="Matter not found")

        # Get sponsors using existing repository method
        sponsors = await db.council_members.get_sponsors_for_matter(matter_id)

        return {
            "success": True,
            "matter_id": matter_id,
            "sponsors": [s.to_dict() for s in sponsors],
            "total": len(sponsors)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error fetching matter sponsors", matter_id=matter_id, error=str(e))
        raise HTTPException(status_code=500, detail="Error retrieving matter sponsors")


@router.get("/city/{banana}/matters")
async def get_city_matters(
    banana: str,
    limit: int = 50,
    offset: int = 0,
    db: Database = Depends(get_db)
):
    """Get all matters for a city with appearance counts

    Returns matters sorted by most recent activity

    Optimized to eliminate N+1 queries by fetching all data in a single query
    """
    try:
        # Verify city exists
        city = await db.get_city(banana=banana)
        if not city:
            raise HTTPException(status_code=404, detail="City not found")

        # Track city page view
        metrics.page_views.labels(page_type='city').inc()

        # Single optimized query: fetch matters with their timelines (async PostgreSQL)
        async with db.pool.acquire() as conn:
            all_data = await conn.fetch(
                """
                WITH matter_summary AS (
                    SELECT
                        m.*,
                        COUNT(i.id) as actual_appearance_count,
                        MAX(mt.date) as last_seen_date
                    FROM city_matters m
                    LEFT JOIN items i ON i.matter_id = m.id
                    LEFT JOIN meetings mt ON i.meeting_id = mt.id
                    WHERE m.banana = $1
                    GROUP BY m.id
                    HAVING COUNT(i.id) >= 1
                    ORDER BY last_seen_date DESC, m.created_at DESC
                    LIMIT $2 OFFSET $3
                )
                SELECT
                    ms.*,
                    i.id as item_id,
                    i.meeting_id,
                    i.agenda_number,
                    i.summary as item_summary,
                    i.topics as item_topics,
                    m.title as meeting_title,
                    m.date as meeting_date,
                    m.banana as meeting_banana
                FROM matter_summary ms
                LEFT JOIN items i ON i.matter_id = ms.id
                LEFT JOIN meetings m ON i.meeting_id = m.id
                ORDER BY ms.last_seen_date DESC, ms.created_at DESC, m.date ASC, i.sequence ASC
                """,
                banana, limit, offset
            )

            # Count all matters with at least one appearance
            total_count_row = await conn.fetchrow(
                """
                SELECT COUNT(*) as count FROM (
                    SELECT m.id
                    FROM city_matters m
                    LEFT JOIN items i ON i.matter_id = m.id
                    WHERE m.banana = $1
                    GROUP BY m.id
                    HAVING COUNT(i.id) >= 1
                ) AS subquery
                """,
                banana
            )
            total_count = total_count_row['count']

        # Group timeline data by matter (single pass through results)
        matters_dict = {}
        for row in all_data:
            matter_id = row["id"]

            # Initialize matter if not seen yet
            if matter_id not in matters_dict:
                matters_dict[matter_id] = {
                    "id": matter_id,
                    "matter_file": row["matter_file"],
                    "matter_id": row["matter_id"],
                    "matter_type": row["matter_type"],
                    "title": row["title"],
                    "sponsors": row["sponsors"] or [],
                    "canonical_summary": row["canonical_summary"],
                    "canonical_topics": row["canonical_topics"] or [],
                    "first_seen": row["first_seen"],
                    "last_seen": row["last_seen"],
                    "appearance_count": row["actual_appearance_count"],
                    "status": row["status"],
                    "timeline": []
                }

            # Add timeline item if it exists (LEFT JOIN may have NULL item_id)
            if row["item_id"] is not None:
                matters_dict[matter_id]["timeline"].append({
                    "item_id": row["item_id"],
                    "meeting_id": row["meeting_id"],
                    "meeting_title": row["meeting_title"],
                    "meeting_date": row["meeting_date"],
                    "banana": row["meeting_banana"],
                    "agenda_number": row["agenda_number"],
                    "summary": row["item_summary"],
                    "topics": row["item_topics"] or []
                })

        # Convert dict to list (preserves ORDER BY from query)
        matters_list = list(matters_dict.values())

        return {
            "success": True,
            "city_name": city.name,
            "state": city.state,
            "banana": banana,
            "matters": matters_list,
            "total_count": total_count,
            "limit": limit,
            "offset": offset
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error fetching matters for city", banana=banana, error=str(e))
        raise HTTPException(status_code=500, detail="Error retrieving city matters")


@router.get("/city/{banana}/search/matters")
async def search_city_matters(
    banana: str,
    q: str,
    limit: int = 50,
    db: Database = Depends(get_db)
):
    """Full-text search matters within a city using PostgreSQL FTS.

    Returns matter results with context snippets for highlighting.
    Searches title, canonical_summary, and matter_file.
    """
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    city = await db.get_city(banana=banana)
    if not city:
        raise HTTPException(status_code=404, detail="City not found")

    logger.debug("city matter search", banana=banana, query=query)

    try:
        matters = await db.matters.search_matters_fulltext(query, banana=banana, limit=limit)
    except Exception as e:
        logger.error("city matter search error", error=str(e), banana=banana)
        raise HTTPException(status_code=500, detail="Search failed")

    # Transform to rich results with context snippets
    results = []
    for m in matters:
        matter_dict = m.to_dict()
        # Add context snippet from canonical_summary or title
        context_source = m.canonical_summary or m.title or ""
        matter_dict["context"] = extract_context(context_source, query)
        matter_dict["type"] = "matter"
        results.append(matter_dict)

    metrics.search_queries.labels(query_type='city_matters').inc()

    return {
        "success": True,
        "query": query,
        "banana": banana,
        "results": results,
        "total": len(results)
    }


@router.get("/state/{state_code}/matters")
async def get_state_matters(
    state_code: str,
    topic: str | None = None,
    limit: int = 100,
    db: Database = Depends(get_db)
):
    """Get matters across all cities in a state

    Optionally filter by topic. Shows cross-city matter trends.
    """
    try:
        # Validate state code (2 letters)
        if len(state_code) != 2:
            raise HTTPException(status_code=400, detail="Invalid state code")

        state_code = state_code.upper()

        # Track state page view
        metrics.page_views.labels(page_type='state').inc()

        # Query matters with async PostgreSQL
        async with db.pool.acquire() as conn:
            # Build query with optional topic filter
            if topic:
                # PostgreSQL uses JSONB @> operator or jsonb_array_elements for topic filtering
                matters = await conn.fetch(
                    """
                    SELECT
                        m.*,
                        c.name as city_name,
                        c.banana,
                        COUNT(i.id) as appearance_count
                    FROM city_matters m
                    JOIN cities c ON m.banana = c.banana
                    LEFT JOIN items i ON i.matter_id = m.id
                    WHERE c.state = $1
                    AND m.canonical_topics::text LIKE $2
                    GROUP BY m.id, c.name, c.banana
                    HAVING COUNT(i.id) >= 2
                    ORDER BY m.last_seen DESC
                    LIMIT $3
                    """,
                    state_code, f'%"{topic}"%', limit
                )
            else:
                matters = await conn.fetch(
                    """
                    SELECT
                        m.*,
                        c.name as city_name,
                        c.banana,
                        COUNT(i.id) as appearance_count
                    FROM city_matters m
                    JOIN cities c ON m.banana = c.banana
                    LEFT JOIN items i ON i.matter_id = m.id
                    WHERE c.state = $1
                    GROUP BY m.id, c.name, c.banana
                    HAVING COUNT(i.id) >= 2
                    ORDER BY m.last_seen DESC
                    LIMIT $2
                    """,
                    state_code, limit
                )

            # Get cities in this state
            cities = await conn.fetch(
                """
                SELECT banana, name, vendor
                FROM cities
                WHERE state = $1
                ORDER BY name ASC
                """,
                state_code
            )

            # Get meeting statistics for this state
            meeting_stats = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) as total_meetings,
                    SUM(CASE WHEN agenda_url IS NOT NULL OR packet_url IS NOT NULL THEN 1 ELSE 0 END) as with_agendas,
                    SUM(CASE WHEN summary IS NOT NULL THEN 1 ELSE 0 END) as with_summaries
                FROM meetings m
                JOIN cities c ON m.banana = c.banana
                WHERE c.state = $1
                """,
                state_code
            )

        # Group by topic for aggregation
        topic_aggregation = {}
        matters_list = []

        for matter in matters:
            matters_list.append({
                "id": matter["id"],
                "matter_file": matter["matter_file"],
                "matter_type": matter["matter_type"],
                "title": matter["title"],
                "city_name": matter["city_name"],
                "banana": matter["banana"],
                "canonical_topics": matter["canonical_topics"],
                "last_seen": matter["last_seen"],
                "appearance_count": matter["appearance_count"]
            })

            # Aggregate by topics
            if matter.get("canonical_topics"):
                try:
                    topics = matter["canonical_topics"]
                    for t in topics:
                        if t not in topic_aggregation:
                            topic_aggregation[t] = 0
                        topic_aggregation[t] += 1
                except (TypeError, KeyError) as e:
                    logger.debug("invalid topics", error=str(e))

        cities_list = [
            {
                "banana": city["banana"],
                "name": city["name"],
                "vendor": city["vendor"]
            }
            for city in cities
        ]

        return {
            "success": True,
            "state": state_code,
            "cities_count": len(cities_list),
            "cities": cities_list,
            "matters": matters_list,
            "total_matters": len(matters_list),
            "topic_distribution": topic_aggregation,
            "filtered_by_topic": topic,
            "meeting_stats": {
                "total_meetings": meeting_stats["total_meetings"],
                "with_agendas": meeting_stats["with_agendas"],
                "with_summaries": meeting_stats["with_summaries"]
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error fetching state matters", state_code=state_code, error=str(e))
        raise HTTPException(status_code=500, detail="Error retrieving state matters")


@router.get("/state/{state_code}/meetings")
async def get_state_meetings(
    state_code: str,
    limit: int = 50,
    include_past: bool = False,
    db: Database = Depends(get_db)
):
    """Get upcoming meetings across all cities in a state.

    Returns meetings sorted by date ascending (soonest first).
    Includes city name and banana for display/navigation.
    """
    try:
        # Validate state code (2 letters)
        if len(state_code) != 2:
            raise HTTPException(status_code=400, detail="Invalid state code")

        state_code = state_code.upper()

        # Track state meetings page view
        metrics.page_views.labels(page_type='state_meetings').inc()

        async with db.pool.acquire() as conn:
            # Build query based on include_past flag
            if include_past:
                meetings = await conn.fetch(
                    """
                    SELECT
                        m.*,
                        c.name as city_name,
                        c.banana as city_banana
                    FROM meetings m
                    JOIN cities c ON m.banana = c.banana
                    WHERE c.state = $1
                    ORDER BY m.date DESC
                    LIMIT $2
                    """,
                    state_code, limit
                )
            else:
                # Filter to upcoming meetings (date >= now - 6 hours for buffer)
                meetings = await conn.fetch(
                    """
                    SELECT
                        m.*,
                        c.name as city_name,
                        c.banana as city_banana
                    FROM meetings m
                    JOIN cities c ON m.banana = c.banana
                    WHERE c.state = $1
                    AND m.date >= NOW() - INTERVAL '6 hours'
                    ORDER BY m.date ASC
                    LIMIT $2
                    """,
                    state_code, limit
                )

            # Get total count for upcoming meetings
            total_row = await conn.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM meetings m
                JOIN cities c ON m.banana = c.banana
                WHERE c.state = $1
                AND m.date >= NOW() - INTERVAL '6 hours'
                """,
                state_code
            )

        meetings_list = []
        for meeting in meetings:
            meetings_list.append({
                "id": meeting["id"],
                "banana": meeting["banana"],
                "title": meeting["title"],
                "date": meeting["date"].isoformat() if meeting["date"] else None,
                "agenda_url": meeting["agenda_url"],
                "packet_url": meeting["packet_url"],
                "summary": meeting["summary"],
                "meeting_status": meeting["meeting_status"],
                "topics": meeting["topics"],
                "has_items": meeting["has_items"],
                "city_name": meeting["city_name"],
                "city_banana": meeting["city_banana"]
            })

        return {
            "success": True,
            "state": state_code,
            "meetings": meetings_list,
            "total": total_row["count"] if total_row else 0
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error fetching state meetings", state_code=state_code, error=str(e))
        raise HTTPException(status_code=500, detail="Error retrieving state meetings")


@router.get("/random-matter")
async def get_random_matter(db: Database = Depends(get_db)):
    """Get a random high-quality matter (2+ appearances)

    Returns a random matter with its timeline for showcasing legislative tracking
    """
    try:
        # Get all matters with 2+ appearances AND summaries (async PostgreSQL)
        async with db.pool.acquire() as conn:
            matters = await conn.fetch(
                """
                SELECT
                    m.id,
                    m.matter_file,
                    m.matter_id,
                    m.matter_type,
                    m.title,
                    m.banana,
                    m.canonical_summary,
                    m.canonical_topics,
                    c.name as city_name,
                    c.state,
                    COUNT(i.id) as appearance_count
                FROM city_matters m
                JOIN cities c ON m.banana = c.banana
                LEFT JOIN items i ON i.matter_id = m.id
                WHERE m.canonical_summary IS NOT NULL AND m.canonical_summary != ''
                GROUP BY m.id, c.name, c.state
                HAVING COUNT(i.id) >= 2
                """
            )

            if not matters:
                raise HTTPException(status_code=404, detail="No high-quality matters found")

            # Pick a random matter
            matter = random.choice(matters)

            # Get timeline for this matter
            timeline_items = await conn.fetch(
                """
                SELECT
                    i.*,
                    m.title as meeting_title,
                    m.date as meeting_date
                FROM items i
                JOIN meetings m ON i.meeting_id = m.id
                WHERE i.matter_id = $1
                ORDER BY m.date ASC, i.sequence ASC
                """,
                matter["id"]
            )

        timeline = []
        for item in timeline_items:
            timeline.append({
                "item_id": item["id"],
                "meeting_id": item["meeting_id"],
                "meeting_title": item["meeting_title"],
                "meeting_date": item["meeting_date"],
                "agenda_number": item["agenda_number"],
                "summary": item["summary"],
                "topics": item["topics"]
            })

        return {
            "success": True,
            "matter": {
                "id": matter["id"],
                "matter_file": matter["matter_file"],
                "matter_type": matter["matter_type"],
                "title": matter["title"],
                "city_name": matter["city_name"],
                "state": matter["state"],
                "banana": matter["banana"],
                "canonical_summary": matter["canonical_summary"],
                "canonical_topics": matter["canonical_topics"],
                "appearance_count": matter["appearance_count"]
            },
            "timeline": timeline
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("error fetching random matter", error=str(e))
        raise HTTPException(status_code=500, detail="Error retrieving random matter")
