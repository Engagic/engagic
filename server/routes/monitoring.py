"""
Monitoring and health check API routes
"""

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response

from config import config, get_logger
from database.db_postgres import Database
from server.dependencies import get_db
from server.metrics import metrics, get_metrics_text

logger = get_logger(__name__)


router = APIRouter()


@router.get("/")
async def root():
    """API status and info"""
    return {
        "service": "engagic API",
        "status": "running",
        "version": "2.0.0",
        "description": "Civic engagement made simple - Search and access local government meetings",
        "documentation": "https://github.com/Engagic/engagic#api-documentation",
        "endpoints": {
            "search": "POST /api/search - Search for meetings by zipcode or city name",
            "process": "POST /api/process-agenda - Get cached meeting agenda summary",
            "random_meeting": "GET /api/random-meeting-with-items - Get a random meeting with item summaries",
            "topics": "GET /api/topics - Get all available topics for filtering",
            "topics_popular": "GET /api/topics/popular - Get most common topics across all meetings",
            "search_by_topic": "POST /api/search/by-topic - Search meetings by topic",
            "stats": "GET /api/stats - System statistics and metrics",
            "queue_stats": "GET /api/queue-stats - Processing queue statistics",
            "health": "GET /api/health - Health check with detailed status",
            "metrics": "GET /api/metrics - Detailed system metrics",
            "admin": {
                "city_requests": "GET /api/admin/city-requests - View requested cities",
                "sync_city": "POST /api/admin/sync-city/{city_slug} - Force sync specific city",
                "process_meeting": "POST /api/admin/process-meeting - Force process specific meeting",
            },
        },
        "usage_examples": {
            "search_by_zipcode": {
                "method": "POST",
                "url": "/api/search",
                "body": {"query": "94301"},
                "description": "Search meetings by ZIP code",
            },
            "search_by_city": {
                "method": "POST",
                "url": "/api/search",
                "body": {"query": "Palo Alto, CA"},
                "description": "Search meetings by city and state",
            },
            "search_ambiguous": {
                "method": "POST",
                "url": "/api/search",
                "body": {"query": "Springfield"},
                "description": "Search by city name only (may return multiple options)",
            },
            "get_summary": {
                "method": "POST",
                "url": "/api/process-agenda",
                "body": {
                    "packet_url": "https://example.com/agenda.pdf",
                    "banana": "paloaltoCA",
                    "meeting_name": "City Council Meeting",
                },
                "description": "Get cached AI summary of meeting agenda",
            },
        },
        "rate_limiting": f"{config.RATE_LIMIT_REQUESTS} requests per {config.RATE_LIMIT_WINDOW} seconds per IP",
        "features": [
            "ZIP code and city name search",
            "AI-powered meeting summaries",
            "Ambiguous city name handling",
            "Real-time meeting data caching",
            "Multiple city system adapters",
            "Background data processing",
            "Comprehensive error handling",
            "Request demand tracking",
        ],
        "data_sources": [
            "PrimeGov (city council management)",
            "CivicClerk (municipal systems)",
            "Direct city websites",
        ],
    }


@router.get("/api/health")
async def health_check(db: Database = Depends(get_db)):
    """Health check endpoint"""
    health_status: Dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "checks": {},
    }

    try:
        # Database health check (async PostgreSQL)
        async with db.pool.acquire() as conn:
            await conn.fetchrow("SELECT 1")

        stats = await db.get_stats()
        health_status["checks"]["databases"] = {
            "status": "healthy",
            "cities": stats["active_cities"],
            "meetings": stats["total_meetings"],
        }

        # Queue health check (detect backlog)
        queue_stats = await db.get_queue_stats()
        pending_count = queue_stats.get("pending_count", 0)
        dead_letter_count = queue_stats.get("dead_letter_count", 0)

        queue_status = "healthy"
        if pending_count > 10000:
            queue_status = "backlogged"
            health_status["status"] = "degraded"
        elif dead_letter_count > 50:
            queue_status = "degraded"
            health_status["status"] = "degraded"

        health_status["checks"]["queue"] = {
            "status": queue_status,
            "pending": pending_count,
            "dead_letter": dead_letter_count,
        }

        # Add basic stats
        health_status["checks"]["data_summary"] = {
            "cities": stats["active_cities"],
            "meetings": stats["total_meetings"],
            "processed": stats["summarized_meetings"],
        }
    except Exception as e:
        health_status["checks"]["databases"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "unhealthy"

    # LLM analyzer check
    health_status["checks"]["llm_analyzer"] = {
        "status": "available" if config.get_api_key() else "disabled",
        "has_api_key": bool(config.get_api_key()),
    }

    # Configuration check
    health_status["checks"]["configuration"] = {
        "status": "healthy",
        "is_development": config.is_development(),
        "rate_limiting": f"{config.RATE_LIMIT_REQUESTS} req/{config.RATE_LIMIT_WINDOW}s",
        "background_processing": config.BACKGROUND_PROCESSING,
    }

    # Background processor check (separate service)
    health_status["checks"]["background_processor"] = {
        "status": "separate_service",
        "note": "Background processing runs as independent daemon",
        "check_command": "systemctl status engagic-daemon",
    }

    # Set overall status based on critical services
    if health_status["checks"]["databases"].get("overall_status") == "error":
        health_status["status"] = "unhealthy"

    return health_status


@router.get("/api/stats")
async def get_stats(db: Database = Depends(get_db)):
    """Get system statistics"""
    try:
        stats = await db.get_stats()

        return {
            "status": "healthy",
            "active_cities": stats.get("active_cities", 0),
            "total_meetings": stats.get("total_meetings", 0),
            "summarized_meetings": stats.get("summarized_meetings", 0),
            "pending_meetings": stats.get("pending_meetings", 0),
            "summary_rate": stats.get("summary_rate", "0%"),
            "background_processing": {
                "service_status": "separate_daemon",
                "note": "Check daemon status: systemctl status engagic-daemon",
            },
        }
    except Exception as e:
        logger.error("error fetching stats", error=str(e))
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )


@router.get("/api/platform-metrics")
async def get_platform_metrics(db: Database = Depends(get_db)):
    """Get comprehensive platform metrics for impact/about page."""
    try:
        metrics = await db.get_platform_metrics()
        return {
            "status": "ok",
            "content": {
                "total_cities": metrics["total_cities"],
                "active_cities": metrics["active_cities"],
                "meetings": metrics["meetings"],
                "agenda_items": metrics["agenda_items"],
                "matters": metrics["matters"],
                "matter_appearances": metrics["matter_appearances"],
            },
            "civic_infrastructure": {
                "committees": metrics["committees"],
                "council_members": metrics["council_members"],
                "committee_assignments": metrics["committee_assignments"],
            },
            "accountability": {
                "votes": metrics["votes"],
                "sponsorships": metrics["sponsorships"],
                "cities_with_votes": metrics["cities_with_votes"],
                "votes_by_city": metrics["votes_by_city"],
            },
            "processing": {
                "summarized_meetings": metrics["summarized_meetings"],
                "summarized_items": metrics["summarized_items"],
                "meeting_summary_rate": metrics["meeting_summary_rate"],
                "item_summary_rate": metrics["item_summary_rate"],
            },
        }
    except Exception as e:
        logger.error("error fetching platform metrics", error=str(e))
        raise HTTPException(status_code=500, detail="Error fetching metrics")


@router.get("/api/queue-stats")
async def get_queue_stats(db: Database = Depends(get_db)):
    """Get processing queue statistics (Phase 4)"""
    try:
        queue_stats = await db.get_queue_stats()

        return {
            "status": "healthy",
            "queue": {
                "pending": queue_stats.get("pending_count", 0),
                "processing": queue_stats.get("processing_count", 0),
                "completed": queue_stats.get("completed_count", 0),
                "failed": queue_stats.get("failed_count", 0),
                "dead_letter": queue_stats.get("dead_letter_count", 0),
                "avg_processing_seconds": round(
                    queue_stats.get("avg_processing_seconds", 0), 2
                ),
            },
            "note": "Queue is processed continuously by background daemon. Failed jobs retry 3 times before moving to dead_letter.",
        }
    except Exception as e:
        logger.error("error fetching queue stats", error=str(e))
        raise HTTPException(status_code=500, detail="Error fetching queue statistics")


@router.get("/api/metrics")
async def get_metrics(db: Database = Depends(get_db)):
    """Basic metrics endpoint for monitoring"""
    try:
        stats = await db.get_stats()

        return {
            "timestamp": datetime.now().isoformat(),
            "database": {
                "active_cities": stats.get("active_cities", 0),
                "total_meetings": stats.get("total_meetings", 0),
                "summarized_meetings": stats.get("summarized_meetings", 0),
                "pending_meetings": stats.get("pending_meetings", 0),
            },
            "configuration": {
                "rate_limit_window": config.RATE_LIMIT_WINDOW,
                "rate_limit_requests": config.RATE_LIMIT_REQUESTS,
                "background_processing": config.BACKGROUND_PROCESSING,
            },
        }
    except Exception as e:
        logger.error("metrics endpoint failed", error=str(e))
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )


@router.get("/metrics")
async def prometheus_metrics(db: Database = Depends(get_db)):
    """Prometheus metrics endpoint

    Returns metrics in Prometheus text format for scraping.
    Updated with real-time queue statistics.
    """
    try:
        # Update queue size gauges with current stats
        queue_stats = await db.get_queue_stats()
        metrics.update_queue_sizes(queue_stats)

        # Return Prometheus text format
        return Response(content=get_metrics_text(), media_type="text/plain")
    except Exception as e:
        logger.error("prometheus metrics endpoint failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate metrics")


@router.get("/api/analytics")
async def get_analytics(db: Database = Depends(get_db)):
    """Get comprehensive analytics for public dashboard"""
    try:
        # Get stats using async PostgreSQL
        async with db.pool.acquire() as conn:
            # City stats
            total_cities = await conn.fetchrow("SELECT COUNT(*) as total_cities FROM cities")
            active_cities_stats = await conn.fetchrow("SELECT COUNT(DISTINCT banana) as active_cities FROM meetings")

            # Meeting stats
            meetings_stats = await conn.fetchrow("SELECT COUNT(*) as meetings_count FROM meetings")
            meetings_with_items_stats = await conn.fetchrow(
                "SELECT COUNT(*) as meetings_with_items FROM meetings WHERE id IN (SELECT DISTINCT meeting_id FROM items)"
            )
            packets_stats = await conn.fetchrow(
                "SELECT COUNT(*) as packets_count FROM meetings WHERE packet_url IS NOT NULL AND packet_url != ''"
            )
            summaries_stats = await conn.fetchrow(
                "SELECT COUNT(*) as summaries_count FROM meetings WHERE summary IS NOT NULL AND summary != ''"
            )

            # Item-level stats (matters-first architecture)
            items_stats = await conn.fetchrow("SELECT COUNT(*) as items_count FROM items")
            matters_stats = await conn.fetchrow("SELECT COUNT(*) as matters_count FROM city_matters")

            # Unique summaries = deduplicated matters + standalone items with summaries
            matters_summarized = await conn.fetchrow(
                "SELECT COUNT(*) as matters_with_summary FROM city_matters WHERE canonical_summary IS NOT NULL AND canonical_summary != ''"
            )
            standalone_items = await conn.fetchrow(
                "SELECT COUNT(*) as standalone_items FROM items WHERE matter_id IS NULL AND summary IS NOT NULL AND summary != ''"
            )

            unique_summaries = matters_summarized["matters_with_summary"] + standalone_items["standalone_items"]

            # Frequently updated cities (cities with at least 7 meetings with summaries)
            frequently_updated_stats = await conn.fetchrow("""
                SELECT COUNT(*) as frequently_updated
                FROM (
                    SELECT m.banana, COUNT(DISTINCT m.id) as meeting_count
                    FROM meetings m
                    WHERE (m.summary IS NOT NULL AND m.summary != '')
                       OR m.id IN (SELECT DISTINCT meeting_id FROM items WHERE summary IS NOT NULL AND summary != '')
                    GROUP BY m.banana
                    HAVING COUNT(DISTINCT m.id) >= 7
                ) AS subquery
            """)

            # Population metrics by coverage tier
            # Total population: all cities with geometry
            total_population = await conn.fetchrow("""
                SELECT COALESCE(SUM(population), 0) as total_pop
                FROM cities WHERE geom IS NOT NULL
            """)

            # Population with any meeting data
            population_with_data = await conn.fetchrow("""
                SELECT COALESCE(SUM(c.population), 0) as pop_with_data
                FROM cities c
                WHERE c.banana IN (SELECT DISTINCT banana FROM meetings)
            """)

            # Population with summarized content
            population_with_summaries = await conn.fetchrow("""
                SELECT COALESCE(SUM(c.population), 0) as pop_with_summaries
                FROM cities c
                WHERE c.banana IN (
                    SELECT DISTINCT m.banana
                    FROM meetings m
                    WHERE (m.summary IS NOT NULL AND m.summary != '')
                       OR m.id IN (SELECT DISTINCT meeting_id FROM items WHERE summary IS NOT NULL AND summary != '')
                )
            """)

        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "real_metrics": {
                "cities_covered": total_cities["total_cities"],
                "active_cities": active_cities_stats["active_cities"],
                "frequently_updated_cities": frequently_updated_stats["frequently_updated"],
                "meetings_tracked": meetings_stats["meetings_count"],
                "meetings_with_items": meetings_with_items_stats["meetings_with_items"],
                "meetings_with_packet": packets_stats["packets_count"],
                "agendas_summarized": summaries_stats["summaries_count"],
                "agenda_items_processed": items_stats["items_count"],
                "matters_tracked": matters_stats["matters_count"],
                "unique_item_summaries": unique_summaries,
                "population_total": total_population["total_pop"],
                "population_with_data": population_with_data["pop_with_data"],
                "population_with_summaries": population_with_summaries["pop_with_summaries"],
            },
        }

    except Exception as e:
        logger.error("analytics endpoint failed", error=str(e))
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )
