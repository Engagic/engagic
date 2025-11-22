"""
Userland Configuration

Environment variables for userland services.
"""

import os

# Database
USERLAND_DB = os.getenv('USERLAND_DB', '/root/engagic/data/userland.db')
ENGAGIC_DB = os.getenv('ENGAGIC_UNIFIED_DB', '/root/engagic/data/engagic.db')

# Authentication
JWT_SECRET = os.getenv('USERLAND_JWT_SECRET')

# Email (Mailgun)
MAILGUN_API_KEY = os.getenv('MAILGUN_API_KEY')
MAILGUN_DOMAIN = os.getenv('MAILGUN_DOMAIN')
MAILGUN_FROM_EMAIL = os.getenv('MAILGUN_FROM_EMAIL', f"alerts@{MAILGUN_DOMAIN}" if MAILGUN_DOMAIN else None)

# Application
APP_URL = os.getenv('APP_URL', 'https://engagic.org')

# Server
SERVER_HOST = os.getenv('SERVER_HOST', '0.0.0.0')
SERVER_PORT = int(os.getenv('SERVER_PORT', '8001'))
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# CORS
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173,https://engagic.org').split(',')

# Cookies
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'true').lower() == 'true'
COOKIE_SAMESITE = os.getenv('COOKIE_SAMESITE', 'lax')

# Alert Processing
SYNC_INTERVAL_HOURS = int(os.getenv('USERLAND_SYNC_INTERVAL_HOURS', '24'))  # How often to check for matches
