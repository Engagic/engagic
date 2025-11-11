"""
Monitoring and health check API routes
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response
from database.db import UnifiedDatabase
from server.services.ticker import generate_ticker_item
from server.metrics import metrics, get_metrics_text
from config import config

logger = logging.getLogger("engagic")

router = APIRouter()


def get_db(request: Request) -> UnifiedDatabase:
    """Dependency to get shared database instance from app state"""
    return request.app.state.db


def get_analyzer():
    """Dependency to get analyzer instance"""
    from pipeline.analyzer import Analyzer
    try:
        analyzer = Analyzer(api_key=config.get_api_key())
        return analyzer
    except ValueError:
        return None


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
            "random_best": "GET /api/random-best-meeting - Get a random high-quality meeting for showcasing",
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
async def health_check(db: UnifiedDatabase = Depends(get_db)):
    """Health check endpoint"""
    analyzer = get_analyzer()

    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "checks": {},
    }

    try:
        # Database health check
        stats = db.get_stats()
        health_status["checks"]["databases"] = {
            "status": "healthy",
            "cities": stats["active_cities"],
            "meetings": stats["total_meetings"],
        }

        # Add basic stats
        health_status["checks"]["data_summary"] = {
            "cities": stats["active_cities"],
            "meetings": stats["total_meetings"],
            "processed": stats["summarized_meetings"],
        }
    except Exception as e:
        health_status["checks"]["databases"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "degraded"

    # LLM analyzer check
    health_status["checks"]["llm_analyzer"] = {
        "status": "available" if analyzer else "disabled",
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
async def get_stats(db: UnifiedDatabase = Depends(get_db)):
    """Get system statistics"""
    try:
        stats = db.get_stats()

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
        logger.error(f"Error fetching stats: {str(e)}")
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )


@router.get("/api/queue-stats")
async def get_queue_stats(db: UnifiedDatabase = Depends(get_db)):
    """Get processing queue statistics (Phase 4)"""
    try:
        queue_stats = db.get_queue_stats()

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
        logger.error(f"Error fetching queue stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching queue statistics")


@router.get("/api/metrics")
async def get_metrics(db: UnifiedDatabase = Depends(get_db)):
    """Basic metrics endpoint for monitoring"""
    try:
        stats = db.get_stats()

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
        logger.error(f"Metrics endpoint failed: {e}")
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )


@router.get("/metrics")
async def prometheus_metrics(db: UnifiedDatabase = Depends(get_db)):
    """Prometheus metrics endpoint

    Returns metrics in Prometheus text format for scraping.
    Updated with real-time queue statistics.
    """
    try:
        # Update queue size gauges with current stats
        queue_stats = db.get_queue_stats()
        metrics.update_queue_sizes(queue_stats)

        # Return Prometheus text format
        return Response(content=get_metrics_text(), media_type="text/plain")
    except Exception as e:
        logger.error(f"Prometheus metrics endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate metrics")


@router.get("/api/analytics")
async def get_analytics(db: UnifiedDatabase = Depends(get_db)):
    """Get comprehensive analytics for public dashboard"""
    try:
        # Get stats directly from unified database
        if db.conn is None:
            raise HTTPException(
                status_code=500, detail="Database connection not established"
            )
        cursor = db.conn.cursor()

        # City stats
        cursor.execute("SELECT COUNT(*) as total_cities FROM cities")
        total_cities = dict(cursor.fetchone())

        # Meeting stats
        cursor.execute("SELECT COUNT(*) as meetings_count FROM meetings")
        meetings_stats = dict(cursor.fetchone())

        cursor.execute(
            "SELECT COUNT(*) as packets_count FROM meetings WHERE packet_url IS NOT NULL AND packet_url != ''"
        )
        packets_stats = dict(cursor.fetchone())

        cursor.execute(
            "SELECT COUNT(*) as summaries_count FROM meetings WHERE summary IS NOT NULL AND summary != ''"
        )
        summaries_stats = dict(cursor.fetchone())

        cursor.execute("SELECT COUNT(DISTINCT banana) as active_cities FROM meetings")
        active_cities_stats = dict(cursor.fetchone())

        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "real_metrics": {
                "cities_covered": total_cities["total_cities"],
                "meetings_tracked": meetings_stats["meetings_count"],
                "meetings_with_packet": packets_stats["packets_count"],
                "agendas_summarized": summaries_stats["summaries_count"],
                "active_cities": active_cities_stats["active_cities"],
            },
        }

    except Exception as e:
        logger.error(f"Analytics endpoint failed: {e}")
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )


@router.get("/api/ticker")
async def get_ticker_items(db: UnifiedDatabase = Depends(get_db)):
    """Get pre-generated ticker items for homepage news ticker"""
    try:
        ticker_items = []

        # Fetch 15 random meetings with items
        for i in range(15):
            meeting = db.get_random_meeting_with_items()

            if meeting:
                ticker_item = generate_ticker_item(meeting, db)
                if ticker_item:
                    ticker_items.append(ticker_item)

        return {
            "success": True,
            "items": ticker_items,
            "count": len(ticker_items)
        }

    except Exception as e:
        logger.error(f"Ticker endpoint failed: {e}")
        raise HTTPException(
            status_code=500, detail="We humbly thank you for your patience"
        )
