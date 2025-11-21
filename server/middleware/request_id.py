"""
Request ID middleware for distributed tracing

Adds correlation IDs to all requests for debugging across logs.
Uses structlog contextvars for request-scoped logging context.
"""

import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add request ID to all requests for tracing"""

    async def dispatch(self, request: Request, call_next):
        # Get request ID from header or generate new one
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in request state for access in routes
        request.state.request_id = request_id

        # Bind request_id to structlog context for ALL logs in this request
        # This makes request_id available to all logger calls within this request context
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            # Process request
            response = await call_next(request)

            # Add request ID to response headers for client tracking
            response.headers["X-Request-ID"] = request_id

            return response
        finally:
            # Clear context after request completes (prevents context leakage)
            structlog.contextvars.clear_contextvars()


def get_request_id(request: Request) -> str:
    """Get request ID from request state"""
    return getattr(request.state, "request_id", "unknown")
