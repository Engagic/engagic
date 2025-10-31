"""Vendor-aware rate limiter to be respectful to city websites"""

import time
import random
import logging
import threading
from collections import defaultdict

logger = logging.getLogger("engagic")


class RateLimiter:
    """Vendor-aware rate limiter to be respectful to city websites"""

    def __init__(self):
        self.last_request = defaultdict(float)
        self.lock = threading.Lock()

    def wait_if_needed(self, vendor: str):
        """Enforce minimum delay between requests to same vendor"""
        delays = {
            "primegov": 3.0,  # PrimeGov cities
            "granicus": 4.0,  # Granicus/Legistar cities
            "civicclerk": 3.0,  # CivicClerk cities
            "legistar": 3.0,  # Direct Legistar
            "civicplus": 8.0,  # CivicPlus cities - aggressive blocking, need longer delays
            "novusagenda": 4.0,  # NovusAgenda cities
            "unknown": 5.0,  # Unknown vendors get longest delay
        }

        min_delay = delays.get(vendor, 5.0)

        # CivicPlus gets extra random jitter to avoid pattern detection
        jitter = random.uniform(0, 2) if vendor == "civicplus" else random.uniform(0, 1)

        with self.lock:
            now = time.time()
            last = self.last_request[vendor]

            if last > 0:
                elapsed = now - last
                if elapsed < min_delay:
                    sleep_time = min_delay - elapsed + jitter
                    logger.info(f"Rate limiting {vendor}: sleeping {sleep_time:.1f}s")
                    time.sleep(sleep_time)

            self.last_request[vendor] = time.time()
