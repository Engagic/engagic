"""
Engagic API Server

Clean, modular FastAPI application with separation of concerns.
Routes, services, and utilities are organized into focused modules.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import config, get_logger
from database.db import UnifiedDatabase
from server.rate_limiter import SQLiteRateLimiter
from server.middleware.logging import log_requests
from server.middleware.metrics import metrics_middleware
from server.middleware.request_id import RequestIDMiddleware
from server.routes import search, meetings, topics, admin, monitoring, flyer, matters, donate, auth, dashboard
from userland.auth import init_jwt
from userland.database.db import UserlandDB

logger = get_logger(__name__)

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(config.LOG_PATH, mode="a")],
)

# Initialize FastAPI app
app = FastAPI(title="engagic API", description="EGMI")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Request ID middleware (must be early in stack for tracing)
app.add_middleware(RequestIDMiddleware)

# Initialize global instances
rate_limiter = SQLiteRateLimiter(
    db_path=str(config.UNIFIED_DB_PATH).replace("engagic.db", "rate_limits.db"),
    requests_limit=config.RATE_LIMIT_REQUESTS,
    window_seconds=config.RATE_LIMIT_WINDOW,
)

# Initialize shared database instance (reused across all requests)
db = UnifiedDatabase(config.UNIFIED_DB_PATH)
logger.info("initialized shared database", db_path=config.UNIFIED_DB_PATH)

# Initialize userland database for auth and user features
userland_db_path = os.getenv('USERLAND_DB', str(config.DB_DIR) + '/userland.db')
userland_db = UserlandDB(userland_db_path, silent=False)
logger.info("initialized userland database", db_path=userland_db_path)

# Initialize JWT for authentication
jwt_secret = os.getenv('USERLAND_JWT_SECRET')
if not jwt_secret:
    logger.warning("WARNING: USERLAND_JWT_SECRET not set. Auth features will not work.")
    logger.warning("Generate with: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'")
else:
    init_jwt(jwt_secret)
    logger.info("JWT authentication initialized")

# Store in app state for dependency injection
app.state.db = db
app.state.userland_db = userland_db


# Register middleware (execution order: metrics -> rate limiting -> logging)
# FastAPI middleware stack: last registered runs first, so register in reverse order
@app.middleware("http")
async def log_requests_middleware(request, call_next):
    return await log_requests(request, call_next)


@app.middleware("http")
async def rate_limit_middleware_wrapper(request, call_next):
    from server.middleware.rate_limiting import rate_limit_middleware
    return await rate_limit_middleware(request, call_next, rate_limiter)


@app.middleware("http")
async def metrics_middleware_wrapper(request, call_next):
    return await metrics_middleware(request, call_next)


# Mount routers
app.include_router(monitoring.router)  # Root and monitoring endpoints
app.include_router(search.router)      # Search endpoints
app.include_router(meetings.router)    # Meeting endpoints
app.include_router(topics.router)      # Topic endpoints
app.include_router(admin.router)       # Admin endpoints
app.include_router(flyer.router)       # Flyer generation endpoints
app.include_router(matters.router)     # Matter timeline and tracking endpoints
app.include_router(donate.router)      # Donation and payment endpoints
app.include_router(auth.router)        # Authentication endpoints (userland)
app.include_router(dashboard.router)   # User dashboard and alerts (userland)


if __name__ == "__main__":
    import uvicorn
    import sys

    # Validate critical environment variables on startup
    if not config.get_api_key():
        logger.warning(
            "WARNING: No LLM API key configured. AI features will be disabled."
        )
        logger.warning("Set ANTHROPIC_API_KEY or LLM_API_KEY to enable AI summaries.")

    if not config.ADMIN_TOKEN:
        logger.warning(
            "WARNING: No admin token configured. Admin endpoints will not work."
        )
        logger.warning("Set ENGAGIC_ADMIN_TOKEN to enable admin functionality.")

    logger.info("Starting engagic API server...")
    logger.info("configuration", config_summary=config.summary())

    # Handle command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--init-db":
        logger.info("Initializing databases...")
        from database.db import UnifiedDatabase
        db = UnifiedDatabase(config.UNIFIED_DB_PATH)
        _ = db.get_stats()
        logger.info("Databases initialized successfully")
        sys.exit(0)

    uvicorn.run(
        app,
        host=config.API_HOST,
        port=config.API_PORT,
        access_log=False,  # Disable default uvicorn logs (we have custom middleware logging)
    )
