"""
Admin API routes
"""

import time
import httpx
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends, Request

from config import config, get_logger
from server.models.requests import ProcessRequest

logger = get_logger(__name__)


router = APIRouter(prefix="/api/admin")


async def verify_admin_token(authorization: str = Header(None)):
    """Verify admin bearer token"""
    if not config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=500, detail="Admin authentication not configured"
        )

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    try:
        scheme, token = authorization.split(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")

        if token != config.ADMIN_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid admin token")

    except ValueError:
        raise HTTPException(
            status_code=401, detail="Invalid authorization header format"
        )

    return True


@router.get("/city-requests")
async def get_city_requests(is_admin: bool = Depends(verify_admin_token)):
    """Get top city requests for admin review"""
    # TODO(Phase 5): Implement analytics tracking for city requests
    # For now, check API logs for usage patterns
    return {
        "success": True,
        "message": "City request tracking not yet implemented. Check API logs for usage patterns.",
        "city_requests": [],
        "total_count": 0,
    }


@router.post("/sync-city/{banana}")
async def force_sync_city(banana: str, is_admin: bool = Depends(verify_admin_token)):
    """Force sync a specific city (admin endpoint)"""
    # This endpoint requires the background processor daemon to be running
    # Admin should use the daemon directly: python daemon.py --sync-city BANANA
    return {
        "success": False,
        "banana": banana,
        "message": "Background processing runs as separate service. Use daemon directly:",
        "command": f"python /root/engagic/app/daemon.py --sync-city {banana}",
        "alternative": "systemctl status engagic-daemon",
    }


@router.post("/process-meeting")
async def force_process_meeting(
    request: ProcessRequest, is_admin: bool = Depends(verify_admin_token)
):
    """Force process a specific meeting (admin endpoint)"""
    # This endpoint requires the background processor daemon to be running
    # Admin should use the daemon directly
    return {
        "success": False,
        "packet_url": request.packet_url,
        "message": "Background processing runs as separate service. Use daemon directly:",
        "command": f"python /root/engagic/app/daemon.py --process-meeting {request.packet_url}",
        "alternative": "systemctl status engagic-daemon",
    }


@router.get("/dead-letter-queue")
async def get_dead_letter_queue(
    request: Request,
    is_admin: bool = Depends(verify_admin_token)
):
    """Get jobs in dead letter queue (failed after 3 retries)

    Returns list of failed jobs with error messages for debugging.
    These jobs require manual intervention or code fixes.
    """
    from database.db import UnifiedDatabase

    db: UnifiedDatabase = request.app.state.db

    try:
        # Get dead letter jobs from queue
        async with db.pool.acquire() as conn:
            dead_jobs = await conn.fetch("""
                SELECT
                    id,
                    job_type,
                    meeting_id,
                    banana,
                    source_url,
                    error_message,
                    retry_count,
                    created_at,
                    started_at,
                    failed_at
                FROM queue
                WHERE status = 'dead_letter'
                ORDER BY failed_at DESC
                LIMIT 100
            """)

        jobs_list = []
        for job in dead_jobs:
            jobs_list.append({
                "queue_id": job["id"],
                "type": job["job_type"],
                "meeting_id": job["meeting_id"],
                "city": job["banana"],
                "source_url": job["source_url"],
                "error": job["error_message"],
                "retries": job["retry_count"],
                "created": str(job["created_at"]),
                "failed": str(job["failed_at"]) if job["failed_at"] else None,
            })

        # Alert if too many failures
        alert_threshold = 50
        needs_attention = len(jobs_list) > alert_threshold

        return {
            "success": True,
            "count": len(jobs_list),
            "alert": needs_attention,
            "alert_threshold": alert_threshold,
            "message": f"Found {len(jobs_list)} jobs in dead letter queue" +
                      (" - NEEDS ATTENTION!" if needs_attention else ""),
            "jobs": jobs_list,
        }

    except Exception as e:
        logger.error(f"Failed to fetch dead letter queue: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch dead letter queue: {str(e)}"
        )


@router.get("/prometheus-query")
async def prometheus_query(
    query: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    step: Optional[str] = None,
    is_admin: bool = Depends(verify_admin_token)
):
    """Proxy queries to Prometheus for dashboard metrics

    Args:
        query: PromQL query string
        start: Start timestamp (RFC3339 or Unix timestamp)
        end: End timestamp (RFC3339 or Unix timestamp)
        step: Query resolution step width

    Returns:
        Prometheus query result in JSON format
    """
    try:
        # Determine if this is a range query or instant query
        prometheus_url = "http://localhost:9090/api/v1"

        if start and end:
            # Range query
            url = f"{prometheus_url}/query_range"
            params = {"query": query, "start": start, "end": end}
            if step:
                params["step"] = step
        else:
            # Instant query
            url = f"{prometheus_url}/query"
            params = {"query": query}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=30.0)
            response.raise_for_status()
            return response.json()

    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Prometheus service unavailable. Ensure Prometheus is running on localhost:9090"
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Prometheus query timeout"
        )
    except Exception as e:
        logger.error(f"Prometheus query error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Prometheus query failed: {str(e)}"
        )


@router.get("/activity-feed")
async def get_activity_feed(
    limit: int = 100,
    is_admin: bool = Depends(verify_admin_token)
):
    """Get recent user activity from API logs

    Returns chronological feed of searches and page views
    """
    import subprocess
    import re

    try:
        result = subprocess.run(
            ['journalctl', '-u', 'engagic-api', '-n', '2000', '--no-pager'],
            capture_output=True,
            text=True,
            timeout=5
        )

        activities = []
        lines = result.stdout.split('\n')

        i = 0
        while i < len(lines):
            line = lines[i]

            # Parse timestamp
            ts_match = re.match(r'^(\w+ \d+ \d+:\d+:\d+)', line)
            if not ts_match:
                i += 1
                continue
            timestamp = ts_match.group(1)

            # Search events
            if 'Search request:' in line:
                query_match = re.search(r"Search request: '(.+?)'", line)
                # Check next line for city result
                if i + 1 < len(lines) and 'Found' in lines[i + 1]:
                    city_match = re.search(r'Found (\d+) cached meetings for (.+?)$', lines[i + 1])
                    if query_match and city_match:
                        activities.append({
                            'timestamp': timestamp,
                            'type': 'search',
                            'query': query_match.group(1),
                            'city': city_match.group(2),
                            'meeting_count': int(city_match.group(1))
                        })

            # Meeting views
            elif 'GET /api/meeting/' in line:
                meeting_match = re.search(r'GET /api/meeting/(\d+)', line)
                if meeting_match:
                    activities.append({
                        'timestamp': timestamp,
                        'type': 'meeting_view',
                        'meeting_id': meeting_match.group(1)
                    })

            # City matters page
            elif 'GET /api/city/' in line and '/matters' in line:
                city_match = re.search(r'GET /api/city/([^/]+)/matters', line)
                if city_match:
                    activities.append({
                        'timestamp': timestamp,
                        'type': 'city_matters',
                        'city_banana': city_match.group(1)
                    })

            i += 1

        # Return most recent activities (reversed for chronological order)
        recent = activities[-limit:] if len(activities) > limit else activities
        return {
            'success': True,
            'activities': list(reversed(recent)),
            'total': len(activities)
        }

    except Exception as e:
        logger.error(f"Error retrieving activity feed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve activity feed: {str(e)}")


@router.get("/live-metrics")
async def get_live_metrics(is_admin: bool = Depends(verify_admin_token)):
    """Get current metrics snapshot for admin dashboard

    Returns real-time metrics without requiring Prometheus queries.
    Useful for quick health checks and current state visibility.

    Returns:
        JSON with current metric values
    """
    from server.metrics import get_metrics_text
    from prometheus_client.parser import text_string_to_metric_families

    try:
        # Get raw Prometheus metrics
        metrics_text = get_metrics_text()

        # Parse metrics into structured format
        metrics_data = {}
        for family in text_string_to_metric_families(metrics_text):
            metrics_data[family.name] = {
                "type": family.type,
                "help": family.documentation,
                "samples": []
            }

            for sample in family.samples:
                metrics_data[family.name]["samples"].append({
                    "labels": sample.labels,
                    "value": sample.value
                })

        return {
            "success": True,
            "timestamp": time.time(),
            "metrics": metrics_data
        }

    except Exception as e:
        logger.error(f"Error retrieving live metrics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve metrics: {str(e)}"
        )
