"""Userland email module - Weekly digests only"""

from userland.email.emailer import EmailService
from userland.email.transactional import send_magic_link

__all__ = ["EmailService", "send_magic_link"]
