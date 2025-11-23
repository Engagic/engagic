"""
Dashboard API

Real-time dashboard data for authenticated users.
Simplified UX: Watch 1 city, track 1-3 keywords, get weekly digest.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from config import get_logger
from server.routes.auth import get_current_user
from userland.database.db import UserlandDB
from userland.database.models import User
from userland.server.models import AlertUpdateRequest

logger = get_logger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def get_userland_db(request: Request) -> UserlandDB:
    """Dependency to get shared userland database instance from app state"""
    return request.app.state.userland_db


@router.get("")
async def get_dashboard(
    user: User = Depends(get_current_user), db: UserlandDB = Depends(get_userland_db)
):
    """
    Get consolidated dashboard data for authenticated user.

    Returns stats, alerts configuration, and recent matches in one call.
    Optimized for simplified UX: 1 city, 1-3 keywords, weekly digest.
    """
    # Get all alerts for this user
    alerts = db.get_alerts(user_id=user.id)
    active_alerts = [a for a in alerts if a.active]

    # Stats calculation
    all_cities = set()
    total_keywords = 0
    for alert in active_alerts:
        all_cities.update(alert.cities)
        criteria = alert.criteria
        if "keywords" in criteria:
            total_keywords += len(criteria["keywords"])

    matches_this_week = db.get_match_count(user_id=user.id, since_days=7)
    total_matches = db.get_match_count(user_id=user.id)

    stats = {
        "active_digests": len(active_alerts),
        "total_matches": total_matches,
        "matches_this_week": matches_this_week,
        "cities_tracked": len(all_cities),
    }

    # Alert config (simplified for 1 city, 1-3 keywords)
    alert_configs = []
    for alert in active_alerts:
        criteria = alert.criteria
        keywords = criteria.get("keywords", [])

        alert_configs.append(
            {
                "id": alert.id,
                "name": alert.name,
                "cities": alert.cities,
                "keywords": keywords,
                "frequency": alert.frequency,
                "active": alert.active,
                "created_at": alert.created_at.isoformat(),
            }
        )

    # Recent matches (last 10)
    matches = db.get_matches(user_id=user.id, limit=10)
    alert_map = {a.id: a.name for a in alerts}

    recent_matches = []
    for match in matches:
        match_dict = match.to_dict()
        match_dict["alert_name"] = alert_map.get(match.alert_id, "Unknown")
        recent_matches.append(match_dict)

    logger.info("dashboard loaded", user_id=user.id, alerts=len(active_alerts))

    return {"stats": stats, "digests": alert_configs, "recent_matches": recent_matches}


@router.get("/stats")
async def get_dashboard_stats(
    user: User = Depends(get_current_user), db: UserlandDB = Depends(get_userland_db)
):
    """
    Get dashboard statistics for authenticated user.

    Returns:
        - active_alerts: Number of active alert configurations
        - total_matches: Number of matches this week
        - cities_tracked: Number of unique cities being monitored
        - keywords_active: Total number of keywords across all alerts
    """
    alerts = db.get_alerts(user_id=user.id)
    active_alerts = [a for a in alerts if a.active]

    all_cities = set()
    total_keywords = 0
    for alert in active_alerts:
        all_cities.update(alert.cities)
        criteria = alert.criteria
        if "keywords" in criteria:
            total_keywords += len(criteria["keywords"])

    matches_today = db.get_match_count(user_id=user.id, since_days=1)

    return {
        "active_alerts": len(active_alerts),
        "matched_today": matches_today,
        "cities_tracked": len(all_cities),
        "keywords_active": total_keywords,
    }


@router.get("/activity")
async def get_recent_activity(
    limit: int = 10,
    user: User = Depends(get_current_user),
    db: UserlandDB = Depends(get_userland_db),
):
    """
    Get recent match activity for authenticated user.

    Returns list of recent matches with details.
    """
    matches = db.get_matches(user_id=user.id, limit=limit)

    alerts = db.get_alerts(user_id=user.id)
    alert_map = {a.id: a.name for a in alerts}

    activity = []
    for match in matches:
        match_dict = match.to_dict()
        match_dict["alert_name"] = alert_map.get(match.alert_id, "Unknown")
        activity.append(match_dict)

    return {"matches": activity, "total": len(activity)}


@router.get("/config")
async def get_alert_config(
    user: User = Depends(get_current_user), db: UserlandDB = Depends(get_userland_db)
):
    """
    Get alert configuration summary for authenticated user.

    Returns summary of all alerts with their cities and keywords.
    """
    alerts = db.get_alerts(user_id=user.id)
    active_alerts = [a for a in alerts if a.active]

    logger.info("config loaded", user_email=user.email, alerts=len(active_alerts))

    config_summary = []
    for alert in active_alerts:
        criteria = alert.criteria
        keywords = criteria.get("keywords", [])

        config_summary.append(
            {
                "alert_id": alert.id,
                "alert_name": alert.name,
                "cities": alert.cities,
                "keywords": keywords,
                "frequency": alert.frequency,
                "active": alert.active,
            }
        )

    return {"alerts": config_summary, "total_alerts": len(config_summary)}


@router.put("/alert/{alert_id}")
async def update_alert(
    alert_id: str,
    update_request: AlertUpdateRequest,
    user: User = Depends(get_current_user),
    db: UserlandDB = Depends(get_userland_db),
):
    """
    Update an alert configuration.

    Only the alert owner can update it.
    Simplified UX: 1 city, 1-3 keywords.
    """
    # Verify alert belongs to this user
    alert = db.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.user_id != user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to modify this alert"
        )

    # Validate simplified UX constraints
    if update_request.cities and len(update_request.cities) > 1:
        raise HTTPException(
            status_code=400,
            detail="Simplified UX: Please track only 1 city at a time",
        )

    if update_request.keywords and len(update_request.keywords) > 3:
        raise HTTPException(
            status_code=400, detail="Simplified UX: Maximum 3 keywords allowed"
        )

    # Update alert
    updated = db.update_alert(
        alert_id=alert_id,
        cities=update_request.cities,
        keywords=update_request.keywords,
        frequency=update_request.frequency,
    )

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update alert")

    logger.info("alert updated", alert_id=alert_id, user_email=user.email)

    return {"status": "updated", "alert": updated.to_dict()}


@router.delete("/alert/{alert_id}")
async def delete_alert(
    alert_id: str,
    user: User = Depends(get_current_user),
    db: UserlandDB = Depends(get_userland_db),
):
    """
    Delete an alert.

    Only the alert owner can delete it.
    """
    # Verify alert belongs to this user
    alert = db.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.user_id != user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this alert"
        )

    # Delete alert
    success = db.delete_alert(alert_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete alert")

    logger.info("alert deleted", alert_id=alert_id, user_email=user.email)

    return {"status": "deleted"}


@router.patch("/alerts/{alert_id}")
async def patch_alert(
    alert_id: str,
    updates: Dict[str, Any],
    user: User = Depends(get_current_user),
    db: UserlandDB = Depends(get_userland_db),
):
    """
    Partially update an alert (PATCH).

    Allows updating individual fields without sending all data.
    """
    alert = db.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.user_id != user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to modify this alert"
        )

    # Validate simplified UX constraints if cities or keywords are being updated
    if "cities" in updates and len(updates["cities"]) > 1:
        raise HTTPException(
            status_code=400, detail="Simplified UX: Please track only 1 city at a time"
        )

    if "keywords" in updates and len(updates["keywords"]) > 3:
        raise HTTPException(
            status_code=400, detail="Simplified UX: Maximum 3 keywords allowed"
        )

    # Apply partial updates
    cities = updates.get("cities", alert.cities)
    keywords = updates.get("keywords", alert.criteria.get("keywords", []))
    frequency = updates.get("frequency", alert.frequency)

    updated = db.update_alert(
        alert_id=alert_id, cities=cities, keywords=keywords, frequency=frequency
    )

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update alert")

    logger.info("alert patched", alert_id=alert_id, user_email=user.email)

    return {"status": "updated", "alert": updated.to_dict()}


@router.post("/alerts/{alert_id}/keywords")
async def add_keyword_to_alert(
    alert_id: str,
    keyword_data: Dict[str, str],
    user: User = Depends(get_current_user),
    db: UserlandDB = Depends(get_userland_db),
):
    """
    Add a keyword to an alert.

    Simplified UX: Maximum 3 keywords allowed.
    """
    alert = db.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.user_id != user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to modify this alert"
        )

    keyword = keyword_data.get("keyword")
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword is required")

    current_keywords = alert.criteria.get("keywords", [])

    if len(current_keywords) >= 3:
        raise HTTPException(
            status_code=400, detail="Simplified UX: Maximum 3 keywords allowed"
        )

    if keyword in current_keywords:
        raise HTTPException(status_code=400, detail="Keyword already exists")

    current_keywords.append(keyword)

    updated = db.update_alert(
        alert_id=alert_id,
        cities=alert.cities,
        keywords=current_keywords,
        frequency=alert.frequency,
    )

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to add keyword")

    logger.info(
        "keyword added", alert_id=alert_id, keyword=keyword, user_email=user.email
    )

    return {"status": "added", "alert": updated.to_dict()}


@router.delete("/alerts/{alert_id}/keywords")
async def remove_keyword_from_alert(
    alert_id: str,
    keyword_data: Dict[str, str],
    user: User = Depends(get_current_user),
    db: UserlandDB = Depends(get_userland_db),
):
    """
    Remove a keyword from an alert.
    """
    alert = db.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.user_id != user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to modify this alert"
        )

    keyword = keyword_data.get("keyword")
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword is required")

    current_keywords = alert.criteria.get("keywords", [])

    if keyword not in current_keywords:
        raise HTTPException(status_code=404, detail="Keyword not found")

    current_keywords.remove(keyword)

    updated = db.update_alert(
        alert_id=alert_id,
        cities=alert.cities,
        keywords=current_keywords,
        frequency=alert.frequency,
    )

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to remove keyword")

    logger.info(
        "keyword removed", alert_id=alert_id, keyword=keyword, user_email=user.email
    )

    return {"status": "removed", "alert": updated.to_dict()}


@router.post("/alerts/{alert_id}/cities")
async def add_city_to_alert(
    alert_id: str,
    city_data: Dict[str, str],
    user: User = Depends(get_current_user),
    db: UserlandDB = Depends(get_userland_db),
):
    """
    Add a city to an alert.

    Simplified UX: Only 1 city allowed (replace existing).
    """
    alert = db.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.user_id != user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to modify this alert"
        )

    city_banana = city_data.get("city_banana")
    if not city_banana:
        raise HTTPException(status_code=400, detail="City banana is required")

    # Simplified UX: Replace existing city (only 1 allowed)
    updated = db.update_alert(
        alert_id=alert_id,
        cities=[city_banana],
        keywords=alert.criteria.get("keywords", []),
        frequency=alert.frequency,
    )

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update city")

    logger.info(
        "city updated",
        alert_id=alert_id,
        city_banana=city_banana,
        user_email=user.email,
    )

    return {"status": "updated", "alert": updated.to_dict()}


@router.delete("/alerts/{alert_id}/cities")
async def remove_city_from_alert(
    alert_id: str,
    city_data: Dict[str, str],
    user: User = Depends(get_current_user),
    db: UserlandDB = Depends(get_userland_db),
):
    """
    Remove a city from an alert.

    Simplified UX: Removes the tracked city (sets to empty).
    """
    alert = db.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.user_id != user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to modify this alert"
        )

    # Remove all cities (simplified UX)
    updated = db.update_alert(
        alert_id=alert_id,
        cities=[],
        keywords=alert.criteria.get("keywords", []),
        frequency=alert.frequency,
    )

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to remove city")

    logger.info("city removed", alert_id=alert_id, user_email=user.email)

    return {"status": "removed", "alert": updated.to_dict()}
