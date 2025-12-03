"""Standardized API response helpers.

Ensures consistent response structure across all endpoints.
All successful responses include {"success": True, ...}
"""

from typing import Optional


def success_response(data: dict, **extras) -> dict:
    """Standard success response wrapper.

    Usage:
        return success_response({"meeting": meeting_dict, "city_name": city.name})

    Returns:
        {"success": True, **data, **extras}
    """
    return {"success": True, **data, **extras}


def list_response(
    items: list,
    key: str = "items",
    total: Optional[int] = None,
    **extras
) -> dict:
    """Standard list response with total count.

    Standardizes the count field naming (always "total").

    Usage:
        return list_response(matters, key="matters")
        return list_response(votes, key="votes", total=100)  # When paginated

    Returns:
        {"success": True, key: items, "total": N, **extras}
    """
    return {
        "success": True,
        key: items,
        "total": total if total is not None else len(items),
        **extras
    }


def error_response(message: str, **extras) -> dict:
    """Standard error response wrapper.

    For cases where you want to return an error dict instead of raising HTTPException.

    Usage:
        return error_response("Summary not yet available")

    Returns:
        {"success": False, "message": message, **extras}
    """
    return {"success": False, "message": message, **extras}
