"""
Userland Configuration

Userland-specific environment variables.
Database configuration now centralized in main config.py.
"""

import os

# Email (Mailgun)
MAILGUN_API_KEY = os.getenv('MAILGUN_API_KEY')
MAILGUN_DOMAIN = os.getenv('MAILGUN_DOMAIN')
MAILGUN_FROM_EMAIL = os.getenv('MAILGUN_FROM_EMAIL', f"alerts@{MAILGUN_DOMAIN}" if MAILGUN_DOMAIN else None)

# Application
APP_URL = os.getenv('APP_URL', 'https://engagic.org')

# CORS
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173,https://engagic.org').split(',')

# Cookies
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'true').lower() == 'true'
COOKIE_SAMESITE = os.getenv('COOKIE_SAMESITE', 'lax')

# Alert Processing
SYNC_INTERVAL_HOURS = int(os.getenv('USERLAND_SYNC_INTERVAL_HOURS', '24'))  # How often to check for matches
