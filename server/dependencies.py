"""FastAPI Dependencies

Centralized dependency injection for reuse across all route modules.
Provides type-safe, testable access to shared resources.
"""

from fastapi import Request
from database.db_postgres import Database


def get_db(request: Request) -> Database:
    """Dependency to get shared database instance from app state

    Usage in routes:
        @router.get("/endpoint")
        async def endpoint(db: Database = Depends(get_db)):
            meetings = await db.meetings.get_recent_meetings()
            return meetings

    Benefits:
    - Type-safe database access (IDE autocomplete works)
    - Testable (can mock database in tests)
    - Cleaner than manual request.app.state.db access
    """
    return request.app.state.db
