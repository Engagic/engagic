"""
Admin API routes
"""

import asyncio
import secrets
import time
import httpx
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends

from config import config, get_logger
from server.models.requests import ProcessRequest
from server.dependencies import get_db
from database.db_postgres import Database

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

        if not secrets.compare_digest(token, config.ADMIN_TOKEN):
            raise HTTPException(status_code=403, detail="Invalid admin token")

    except ValueError:
        raise HTTPException(
            status_code=401, detail="Invalid authorization header format"
        )

    return True


@router.get("/city-requests")
async def get_city_requests(
    db: Database = Depends(get_db),
    is_admin: bool = Depends(verify_admin_token)
):
    """Get pending city requests ordered by demand

    Returns cities users have requested but aren't covered yet.
    Sorted by request_count descending - highest demand first.
    """
    try:
        requests = await db.userland.get_pending_city_requests()

        return {
            "success": True,
            "city_requests": requests,
            "total": len(requests),
        }

    except Exception:
        logger.exception("failed to fetch city requests")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch city requests"
        )


@router.post("/sync-city/{banana}")
async def force_sync_city(banana: str, is_admin: bool = Depends(verify_admin_token)):
    """INFO-ONLY: Returns CLI command to sync a city.

    This endpoint does NOT trigger processing. Processing runs via systemd daemon.
    Use the provided CLI command on the VPS to trigger manual sync.
    """
    return {
        "success": False,
        "banana": banana,
        "message": "Background processing runs as separate service. Use daemon directly:",
        "command": f"cd /opt/engagic && uv run python -m pipeline.conductor --sync-city {banana}",
        "alternative": "systemctl status engagic-daemon",
    }


@router.post("/process-meeting")
async def force_process_meeting(
    request: ProcessRequest, is_admin: bool = Depends(verify_admin_token)
):
    """INFO-ONLY: Returns CLI command to process a meeting.

    This endpoint does NOT trigger processing. Processing runs via systemd daemon.
    Use the provided CLI command on the VPS to trigger manual processing.
    """
    return {
        "success": False,
        "packet_url": request.packet_url,
        "message": "Background processing runs as separate service. Use daemon directly:",
        "command": f"cd /opt/engagic && uv run python -m pipeline.conductor --process-url {request.packet_url}",
        "alternative": "systemctl status engagic-daemon",
    }


@router.get("/dead-letter-queue")
async def get_dead_letter_queue(
    db: Database = Depends(get_db),
    is_admin: bool = Depends(verify_admin_token)
):
    """Get jobs in dead letter queue (failed after 3 retries)

    Returns list of failed jobs with error messages for debugging.
    These jobs require manual intervention or code fixes.
    """

    try:
        dead_jobs = await db.queue.get_dead_letter_jobs(limit=100)

        jobs_list = [
            {
                "queue_id": job["id"],
                "type": job["job_type"],
                "meeting_id": job["meeting_id"],
                "city": job["banana"],
                "source_url": job["source_url"],
                "error": job["error_message"],
                "retries": job["retry_count"],
                "created": job["created_at"],
                "failed": job["failed_at"],
            }
            for job in dead_jobs
        ]

        alert_threshold = 50
        needs_attention = len(jobs_list) > alert_threshold

        return {
            "success": True,
            "total": len(jobs_list),
            "alert": needs_attention,
            "alert_threshold": alert_threshold,
            "message": f"Found {len(jobs_list)} jobs in dead letter queue" +
                      (" - NEEDS ATTENTION!" if needs_attention else ""),
            "jobs": jobs_list,
        }

    except Exception:
        logger.exception("failed to fetch dead letter queue")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch dead letter queue"
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
        prometheus_url = "http://localhost:9090/api/v1"

        if start and end:
            url = f"{prometheus_url}/query_range"
            params = {"query": query, "start": start, "end": end}
            if step:
                params["step"] = step
        else:
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
    except Exception:
        logger.exception("prometheus query error")
        raise HTTPException(
            status_code=500,
            detail="Prometheus query failed"
        )


@router.get("/activity-feed")
async def get_activity_feed(
    limit: int = 100,
    is_admin: bool = Depends(verify_admin_token)
):
    """Get recent user activity from API logs

    Returns chronological feed of searches and page views
    """
    import re

    try:
        proc = await asyncio.create_subprocess_exec(
            'journalctl', '-u', 'engagic-api', '-n', '2000', '--no-pager',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        result_stdout = stdout.decode()

        activities = []
        lines = result_stdout.split('\n')

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

    except Exception:
        logger.exception("error retrieving activity feed")
        raise HTTPException(status_code=500, detail="Failed to retrieve activity feed")


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

    except Exception:
        logger.exception("error retrieving live metrics")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve metrics"
        )
