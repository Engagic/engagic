"""Userland email module"""

from userland.email.emailer import EmailService, send_daily_digests
from userland.email.transactional import send_magic_link

__all__ = ["EmailService", "send_daily_digests", "send_magic_link"]
