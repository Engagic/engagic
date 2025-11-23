"""
Matter API routes

Handles matter tracking, timelines, and cross-meeting aggregation
"""

import json
import random
from fastapi import APIRouter, HTTPException, Depends, Request
from server.metrics import metrics
from database.db import UnifiedDatabase

from config import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix="/api")


def get_db(request: Request) -> UnifiedDatabase:
    """Dependency to get shared database instance from app state"""
    return request.app.state.db


@router.get("/matters/{matter_id}/timeline")
async def get_matter_timeline(matter_id: str, db: UnifiedDatabase = Depends(get_db)):
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

        # Get all items for this matter across meetings (simple FK join)
        items = db.conn.execute(
            """
            SELECT
                i.*,
                m.title as meeting_title,
                m.date as meeting_date,
                m.banana,
                c.name as city_name,
                c.state
            FROM items i
            JOIN meetings m ON i.meeting_id = m.id
            JOIN cities c ON m.banana = c.banana
            WHERE i.matter_id = ?
            ORDER BY m.date ASC, i.sequence ASC
            """,
            (matter.id,)
        ).fetchall()

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
                "topics": json.loads(item["topics"]) if item["topics"] else []
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
        logger.error(f"Error fetching matter timeline {matter_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving matter timeline")


@router.get("/city/{banana}/matters")
async def get_city_matters(
    banana: str,
    limit: int = 50,
    offset: int = 0,
    db: UnifiedDatabase = Depends(get_db)
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

        # Single optimized query: fetch matters with their timelines (eliminates N+1 problem)
        # Uses CTE for matter filtering, then joins timeline data in one query
        all_data = db.conn.execute(
            """
            WITH matter_summary AS (
                SELECT
                    m.*,
                    COUNT(i.id) as actual_appearance_count,
                    MAX(mt.date) as last_seen_date
                FROM city_matters m
                LEFT JOIN items i ON i.matter_id = m.id
                LEFT JOIN meetings mt ON i.meeting_id = mt.id
                WHERE m.banana = ?
                GROUP BY m.id
                HAVING COUNT(i.id) >= 1
                ORDER BY last_seen_date DESC, m.created_at DESC
                LIMIT ? OFFSET ?
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
            (banana, limit, offset)
        ).fetchall()

        # Count all matters with at least one appearance
        total_count = db.conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT m.id
                FROM city_matters m
                LEFT JOIN items i ON i.matter_id = m.id
                WHERE m.banana = ?
                GROUP BY m.id
                HAVING COUNT(i.id) >= 1
            )
            """,
            (banana,)
        ).fetchone()[0]

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
                    "sponsors": json.loads(row["sponsors"]) if row["sponsors"] else [],
                    "canonical_summary": row["canonical_summary"],
                    "canonical_topics": json.loads(row["canonical_topics"]) if row["canonical_topics"] else [],
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
                    "topics": json.loads(row["item_topics"]) if row["item_topics"] else []
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
        logger.error(f"Error fetching matters for city {banana}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving city matters")


@router.get("/state/{state_code}/matters")
async def get_state_matters(
    state_code: str,
    topic: str | None = None,
    limit: int = 100,
    db: UnifiedDatabase = Depends(get_db)
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

        # Build query with optional topic filter
        query = """
            SELECT
                m.*,
                c.name as city_name,
                c.banana,
                COUNT(i.id) as appearance_count
            FROM city_matters m
            JOIN cities c ON m.banana = c.banana
            LEFT JOIN items i ON i.matter_id = m.id
            WHERE c.state = ?
        """

        params: list[str | int] = [state_code]

        if topic:
            query += " AND json_extract(m.canonical_topics, '$') LIKE ?"
            params.append(f'%"{topic}"%')

        query += """
            GROUP BY m.id
            HAVING COUNT(i.id) >= 2
            ORDER BY m.last_seen DESC
            LIMIT ?
        """
        params.append(limit)

        matters = db.conn.execute(query, tuple(params)).fetchall()

        # Group by topic for aggregation
        topic_aggregation = {}
        matters_list = []

        for matter in matters:
            matter_dict = dict(matter)
            matters_list.append({
                "id": matter_dict["id"],
                "matter_file": matter_dict["matter_file"],
                "matter_type": matter_dict["matter_type"],
                "title": matter_dict["title"],
                "city_name": matter_dict["city_name"],
                "banana": matter_dict["banana"],
                "canonical_topics": matter_dict["canonical_topics"],
                "last_seen": matter_dict["last_seen"],
                "appearance_count": matter_dict["appearance_count"]
            })

            # Aggregate by topics
            if matter_dict.get("canonical_topics"):
                try:
                    topics = json.loads(matter_dict["canonical_topics"])
                    for t in topics:
                        if t not in topic_aggregation:
                            topic_aggregation[t] = 0
                        topic_aggregation[t] += 1
                except (json.JSONDecodeError, TypeError, KeyError) as e:
                    logger.debug(f"Invalid topics JSON: {e}")

        # Get cities in this state
        cities = db.conn.execute(
            """
            SELECT banana, name, vendor
            FROM cities
            WHERE state = ?
            ORDER BY name ASC
            """,
            (state_code,)
        ).fetchall()

        cities_list = [
            {
                "banana": city["banana"],
                "name": city["name"],
                "vendor": city["vendor"]
            }
            for city in cities
        ]

        # Get meeting statistics for this state
        meeting_stats = db.conn.execute(
            """
            SELECT
                COUNT(*) as total_meetings,
                SUM(CASE WHEN agenda_url IS NOT NULL OR packet_url IS NOT NULL THEN 1 ELSE 0 END) as with_agendas,
                SUM(CASE WHEN summary IS NOT NULL THEN 1 ELSE 0 END) as with_summaries
            FROM meetings m
            JOIN cities c ON m.banana = c.banana
            WHERE c.state = ?
            """,
            (state_code,)
        ).fetchone()

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
        logger.error(f"Error fetching state matters for {state_code}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving state matters")


@router.get("/random-matter")
async def get_random_matter(db: UnifiedDatabase = Depends(get_db)):
    """Get a random high-quality matter (2+ appearances)

    Returns a random matter with its timeline for showcasing legislative tracking
    """
    try:
        # Get all matters with 2+ appearances AND summaries
        matters = db.conn.execute(
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
            GROUP BY m.id
            HAVING COUNT(i.id) >= 2
            """,
        ).fetchall()

        if not matters:
            raise HTTPException(status_code=404, detail="No high-quality matters found")

        # Pick a random matter
        matter = random.choice(matters)
        matter_dict = dict(matter)

        # Get timeline for this matter (simple FK join)
        timeline_items = db.conn.execute(
            """
            SELECT
                i.*,
                m.title as meeting_title,
                m.date as meeting_date
            FROM items i
            JOIN meetings m ON i.meeting_id = m.id
            WHERE i.matter_id = ?
            ORDER BY m.date ASC, i.sequence ASC
            """,
            (matter_dict["id"],)
        ).fetchall()

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
                "id": matter_dict["id"],
                "matter_file": matter_dict["matter_file"],
                "matter_type": matter_dict["matter_type"],
                "title": matter_dict["title"],
                "city_name": matter_dict["city_name"],
                "state": matter_dict["state"],
                "banana": matter_dict["banana"],
                "canonical_summary": matter_dict["canonical_summary"],
                "canonical_topics": matter_dict["canonical_topics"],
                "appearance_count": matter_dict["appearance_count"]
            },
            "timeline": timeline
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching random matter: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving random matter")
