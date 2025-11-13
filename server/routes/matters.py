"""
Matter API routes

Handles matter tracking, timelines, and cross-meeting aggregation
"""

import json
import logging
import random
from fastapi import APIRouter, HTTPException, Depends, Request
from database.db import UnifiedDatabase

logger = logging.getLogger("engagic")

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
        matter = db.get_matter(matter_id)

        if not matter:
            raise HTTPException(status_code=404, detail="Matter not found")

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
    """
    try:
        # Verify city exists
        city = db.get_city(banana=banana)
        if not city:
            raise HTTPException(status_code=404, detail="City not found")

        matters = db.conn.execute(
            """
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

        matters_list = []
        for matter in matters:
            matter_dict = dict(matter)

            # Fetch timeline for this matter (simple FK join)
            timeline_items = db.conn.execute(
                """
                SELECT
                    i.id as item_id,
                    i.meeting_id,
                    i.agenda_number,
                    i.summary,
                    i.topics,
                    m.title as meeting_title,
                    m.date as meeting_date,
                    m.banana
                FROM items i
                JOIN meetings m ON i.meeting_id = m.id
                WHERE i.matter_id = ?
                ORDER BY m.date ASC, i.sequence ASC
                """,
                (matter_dict["id"],)
            ).fetchall()

            timeline = [
                {
                    "item_id": item["item_id"],
                    "meeting_id": item["meeting_id"],
                    "meeting_title": item["meeting_title"],
                    "meeting_date": item["meeting_date"],
                    "banana": item["banana"],
                    "agenda_number": item["agenda_number"],
                    "summary": item["summary"],
                    "topics": json.loads(item["topics"]) if item["topics"] else []
                }
                for item in timeline_items
            ]

            matters_list.append({
                "id": matter_dict["id"],
                "matter_file": matter_dict["matter_file"],
                "matter_id": matter_dict["matter_id"],
                "matter_type": matter_dict["matter_type"],
                "title": matter_dict["title"],
                "sponsors": json.loads(matter_dict["sponsors"]) if matter_dict["sponsors"] else [],
                "canonical_summary": matter_dict["canonical_summary"],
                "canonical_topics": json.loads(matter_dict["canonical_topics"]) if matter_dict["canonical_topics"] else [],
                "first_seen": matter_dict["first_seen"],
                "last_seen": matter_dict["last_seen"],
                "appearance_count": matter_dict["actual_appearance_count"],
                "status": matter_dict["status"],
                "timeline": timeline
            })

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
                import json
                try:
                    topics = json.loads(matter_dict["canonical_topics"])
                    for t in topics:
                        if t not in topic_aggregation:
                            topic_aggregation[t] = 0
                        topic_aggregation[t] += 1
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass

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
