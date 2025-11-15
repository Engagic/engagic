"""
Dashboard API routes - Comprehensive metrics and intelligence
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from database.db import UnifiedDatabase

logger = logging.getLogger("engagic")

router = APIRouter(prefix="/api/dashboard")


def get_db(request: Request) -> UnifiedDatabase:
    """Dependency to get shared database instance from app state"""
    return request.app.state.db


@router.get("/overview")
async def get_dashboard_overview(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: UnifiedDatabase = Depends(get_db),
):
    """
    Get comprehensive dashboard overview metrics

    Query params:
    - start_date: Optional ISO date (YYYY-MM-DD) for filtering
    - end_date: Optional ISO date (YYYY-MM-DD) for filtering

    Returns:
    - totals: City, meeting, item, matter counts
    - processing: Queue depth and success rates
    - growth: 7/30/90 day trends
    """
    try:
        overview = db.search.get_dashboard_overview(start_date, end_date)
        return overview
    except Exception as e:
        logger.error(f"Dashboard overview error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve dashboard overview")


@router.get("/geographic")
async def get_geographic_stats(db: UnifiedDatabase = Depends(get_db)):
    """
    Get state-level geographic statistics

    Returns:
    - states: Meeting counts per state
    - vendors: Vendor distribution
    - coverage: Civic tech coverage scores per state
    """
    try:
        stats = db.search.get_geographic_stats()
        return stats
    except Exception as e:
        logger.error(f"Geographic stats error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve geographic stats")


@router.get("/topics/trends")
async def get_topic_trends(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: UnifiedDatabase = Depends(get_db),
):
    """
    Get topic frequency and trend analysis

    Query params:
    - start_date: Optional ISO date for filtering
    - end_date: Optional ISO date for filtering

    Returns:
    - frequency: Topic counts across all meetings
    - trending: Topics with highest growth (last 30 vs prev 30 days)
    - cooccurrence: Topics that appear together
    """
    try:
        trends = db.search.get_topic_trends(start_date, end_date)
        return trends
    except Exception as e:
        logger.error(f"Topic trends error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve topic trends")


@router.get("/matters/trending")
async def get_matter_trends(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: UnifiedDatabase = Depends(get_db),
):
    """
    Get legislative matter tracking trends

    Query params:
    - start_date: Optional ISO date for filtering
    - end_date: Optional ISO date for filtering

    Returns:
    - top_matters: Most tracked legislative items
    - cross_state: Matters appearing in multiple states
    - recent_activity: Recently active matters
    - velocity: Matter progression speed (appearances per month)
    """
    try:
        trends = db.search.get_matter_trends(start_date, end_date)
        return trends
    except Exception as e:
        logger.error(f"Matter trends error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve matter trends")


@router.get("/funding")
async def get_funding_insights(db: UnifiedDatabase = Depends(get_db)):
    """
    Extract and analyze funding information from meeting summaries

    Returns:
    - total_funding_meetings: Count of meetings with budget/contract mentions
    - top_meetings: Recent meetings with funding discussions
    - by_city: Budget meeting counts per city
    - by_state: Budget meeting counts per state
    """
    try:
        funding = db.search.extract_funding_data()
        return funding
    except Exception as e:
        logger.error(f"Funding insights error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve funding insights")


@router.get("/processing")
async def get_processing_health(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: UnifiedDatabase = Depends(get_db),
):
    """
    Get processing system health metrics

    Query params:
    - start_date: Optional ISO date for filtering
    - end_date: Optional ISO date for filtering

    Returns:
    - queue_timeline: Processing queue depth over last 30 days
    - vendor_success: Success rates by vendor
    - processing_speed: Average/min/max processing times
    - cache: Cache hit statistics
    """
    try:
        health = db.search.get_processing_health(start_date, end_date)
        return health
    except Exception as e:
        logger.error(f"Processing health error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve processing health")
