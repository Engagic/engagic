"""
Admin API routes
"""

import logging
import httpx
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Depends
from server.models.requests import ProcessRequest
from config import config

logger = logging.getLogger("engagic")

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
            "timestamp": __import__("time").time(),
            "metrics": metrics_data
        }

    except Exception as e:
        logger.error(f"Error retrieving live metrics: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve metrics: {str(e)}"
        )
