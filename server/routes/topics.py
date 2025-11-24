"""
Topic search API routes
"""

from fastapi import APIRouter, HTTPException, Depends
from server.models.requests import TopicSearchRequest
from server.dependencies import get_db
from database.db_postgres import Database

from config import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix="/api")


@router.get("/topics")
async def get_all_topics():
    """Get all available canonical topics for browsing/filtering"""
    try:
        from analysis.topics.normalizer import get_normalizer

        normalizer = get_normalizer()
        all_topics = normalizer.get_all_canonical_topics()

        # Build response with display names
        topics_with_display = [
            {
                "canonical": topic,
                "display_name": normalizer.get_display_name(topic)
            }
            for topic in all_topics
        ]

        return {
            "success": True,
            "topics": topics_with_display,
            "count": len(topics_with_display)
        }
    except Exception as e:
        logger.error("error fetching topics", error=str(e))
        raise HTTPException(status_code=500, detail="Error fetching topics")


@router.post("/search/by-topic")
async def search_by_topic(request: TopicSearchRequest, db: Database = Depends(get_db)):
    """Search meetings by topic (Phase 1 - Topic Extraction)"""
    try:
        from analysis.topics.normalizer import get_normalizer

        # Normalize the search topic
        normalizer = get_normalizer()
        normalized_topic = normalizer.normalize_single(request.topic)

        logger.info("topic search", query=request.topic, normalized=normalized_topic, city=request.banana)

        # Search meetings by topic using db method
        meetings = await db.search_meetings_by_topic(
            topic=normalized_topic,
            city_banana=request.banana,
            limit=request.limit
        )

        # For each meeting, get the items that match this topic
        results = []
        for meeting in meetings:
            # Get items with this topic using db method
            matching_items = await db.get_items_by_topic(meeting.id, normalized_topic)

            results.append({
                "meeting": meeting.to_dict(),
                "matching_items": [
                    {
                        "id": item.id,
                        "title": item.title,
                        "sequence": item.sequence,
                        "summary": item.summary,
                        "topics": item.topics
                    }
                    for item in matching_items
                ]
            })

        return {
            "success": True,
            "query": request.topic,
            "normalized_topic": normalized_topic,
            "display_name": normalizer.get_display_name(normalized_topic),
            "results": results,
            "count": len(results)
        }

    except Exception as e:
        logger.error("error searching by topic", topic=request.topic, error=str(e))
        raise HTTPException(status_code=500, detail="Error searching by topic")


@router.get("/topics/popular")
async def get_popular_topics(db: Database = Depends(get_db)):
    """Get most common topics across all meetings (for UI suggestions)"""
    try:
        # Get popular topics using db method
        topic_counts = await db.get_popular_topics(limit=20)

        from analysis.topics.normalizer import get_normalizer
        normalizer = get_normalizer()

        popular_topics = [
            {
                "topic": item["topic"],
                "display_name": normalizer.get_display_name(item["topic"]),
                "count": item["count"]
            }
            for item in topic_counts
        ]

        return {
            "success": True,
            "topics": popular_topics,
            "count": len(popular_topics)
        }

    except Exception as e:
        logger.error("error fetching popular topics", error=str(e))
        raise HTTPException(status_code=500, detail="Error fetching popular topics")
