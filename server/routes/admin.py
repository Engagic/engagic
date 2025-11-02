"""
Admin API routes
"""

import logging
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
