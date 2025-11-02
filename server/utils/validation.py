"""
Input validation and sanitization utilities
"""

import re
from config import config


def sanitize_string(value: str) -> str:
    """Sanitize string input to prevent injection attacks"""
    if not value:
        return ""

    # Basic SQL injection prevention - reject obvious patterns
    sql_patterns = [
        r"';\s*DROP",
        r"';\s*DELETE",
        r"';\s*UPDATE",
        r"';\s*INSERT",
        r"--",
        r"/\*.*\*/",
        r"UNION\s+SELECT",
        r"OR\s+1\s*=\s*1",
    ]
    for pattern in sql_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            raise ValueError("Invalid characters in input")

    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>"\';()&+]', "", value.strip())
    return sanitized[: config.MAX_QUERY_LENGTH]
