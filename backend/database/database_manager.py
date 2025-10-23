"""
Database Manager - Direct wrapper around UnifiedDatabase

Simple pass-through to UnifiedDatabase. Exists only to avoid changing
all the import statements immediately.

Will be removed once imports are updated to use UnifiedDatabase directly.
"""

from .unified_db import UnifiedDatabase

# Direct alias - DatabaseManager IS UnifiedDatabase
DatabaseManager = UnifiedDatabase
