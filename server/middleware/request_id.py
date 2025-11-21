"""
Request ID middleware for distributed tracing

Adds correlation IDs to all requests for debugging across logs.
"""

import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("engagic")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add request ID to all requests for tracing"""

    async def dispatch(self, request: Request, call_next):
        # Get request ID from header or generate new one
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in request state for access in routes
        request.state.request_id = request_id

        # Add to logging context
        logger_adapter = logging.LoggerAdapter(
            logger,
            {"request_id": request_id}
        )

        # Process request
        response = await call_next(request)

        # Add request ID to response headers for client tracking
        response.headers["X-Request-ID"] = request_id

        return response


def get_request_id(request: Request) -> str:
    """Get request ID from request state"""
    return getattr(request.state, "request_id", "unknown")
