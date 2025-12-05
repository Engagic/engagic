"""
Async Session Manager for Vendor Adapters

Centralized HTTP session pooling using aiohttp for all vendor adapters.

Benefits:
- Connection reuse across all adapters (2-5x faster syncs)
- One session per vendor (not per city)
- Async I/O for concurrent city fetching
- Automatic cleanup on shutdown

Replaces: vendors/session_manager.py (sync version with requests)
"""

import aiohttp
from typing import Any, Dict

from config import get_logger

logger = get_logger(__name__).bind(component="vendor")


class AsyncSessionManager:
    """
    Manages aiohttp client sessions for vendor adapters.

    Creates one shared session per vendor with connection pooling.
    Sessions are created lazily and reused for process lifetime.
    """

    _sessions: Dict[str, aiohttp.ClientSession] = {}
    _closed = False

    @classmethod
    async def get_session(cls, vendor: str, timeout_total: int = 30) -> aiohttp.ClientSession:
        """
        Get or create aiohttp session for vendor.

        Args:
            vendor: Vendor name (e.g., "legistar", "primegov", "granicus")
            timeout_total: Total timeout in seconds (default: 30s)

        Returns:
            Shared aiohttp.ClientSession for vendor
        """
        if cls._closed:
            raise RuntimeError("AsyncSessionManager has been closed")

        if vendor not in cls._sessions or cls._sessions[vendor].closed:
            # Create new session with connection pooling
            timeout = aiohttp.ClientTimeout(
                total=timeout_total,
                connect=10,  # 10s to establish connection
                sock_read=timeout_total  # Total time to read response
            )

            # Connection pooling configuration
            connector = aiohttp.TCPConnector(
                limit=20,  # Max 20 total connections per vendor
                limit_per_host=5,  # Max 5 connections per host
                ttl_dns_cache=300,  # Cache DNS for 5 minutes
                enable_cleanup_closed=True  # Clean up closed connections
            )

            # Browser-like headers to avoid bot detection
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive"
            }

            cls._sessions[vendor] = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers=headers,
                raise_for_status=False  # Don't raise on 4xx/5xx (handle in adapters)
            )

            logger.debug(
                "created async session",
                vendor=vendor,
                max_connections=20,
                timeout_seconds=timeout_total
            )

        return cls._sessions[vendor]

    @classmethod
    async def close_all(cls):
        """
        Close all active sessions (cleanup on shutdown).

        Call this when application is shutting down to properly
        close all HTTP connections.
        """
        if cls._closed:
            return

        logger.info("closing async sessions", session_count=len(cls._sessions))

        for vendor, session in cls._sessions.items():
            if not session.closed:
                await session.close()
                logger.debug("closed async session", vendor=vendor)

        cls._sessions.clear()
        cls._closed = True

    @classmethod
    async def close_session(cls, vendor: str):
        """
        Close session for specific vendor.

        Args:
            vendor: Vendor name to close session for
        """
        if vendor in cls._sessions:
            session = cls._sessions[vendor]
            if not session.closed:
                await session.close()
                logger.debug("closed async session", vendor=vendor)
            del cls._sessions[vendor]

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Get statistics about active sessions"""
        stats: Dict[str, Any] = {
            "total_sessions": len(cls._sessions),
            "closed": cls._closed,
            "vendors": {}
        }

        for vendor, session in cls._sessions.items():
            connector = session.connector
            if connector and hasattr(connector, "_conns"):
                stats["vendors"][vendor] = {
                    "closed": session.closed,
                    "active_connections": len(connector._conns) if hasattr(connector, "_conns") else 0
                }

        return stats
