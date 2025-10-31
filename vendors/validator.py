"""
Meeting validation layer to prevent data corruption.

Validates that packet URLs match configured vendor/slug before storing meetings.
"""

import logging
from urllib.parse import urlparse
from typing import Optional, Dict, Any

logger = logging.getLogger("engagic")

# Confidence: 9/10 - Simple domain validation logic


class MeetingValidator:
    """Validates meeting data before storage to prevent corruption."""

    # Expected domain patterns for each vendor
    VENDOR_DOMAINS = {
        "primegov": lambda slug: [f"{slug}.primegov.com"],
        "granicus": lambda slug: [
            f"{slug}.granicus.com",
            "s3.amazonaws.com",  # Granicus uses S3
            "cloudfront.net",  # Granicus CloudFront CDN
            "legistar.granicus.com",
            "legistar1.granicus.com",
            "legistar2.granicus.com",
            "docs.google.com",  # Some cities use Google Docs viewer
        ],
        "legistar": lambda slug: [
            "legistar.granicus.com",
            "legistar1.granicus.com",
            "legistar2.granicus.com",
            "legistar3.granicus.com",  # Columbus uses legistar3
            f"{slug}.legistar1.com",
            f"{slug}.legistar.com",
            "docs.google.com",  # Some cities use Google Docs viewer
        ],
        "civicclerk": lambda slug: [f"{slug}.api.civicclerk.com"],
        "novusagenda": lambda slug: [f"{slug}.novusagenda.com"],
        "civicplus": lambda slug: [
            f"{slug}.civicplus.com",
            "granicus.com",  # CivicPlus often redirects to Granicus
            "municodemeetings.com",  # Or Municode
        ],
        "civicweb": lambda slug: [f"{slug}.civicweb.net"],
        "iqm2": lambda slug: [f"{slug}.iqm2.com", "granicus.com"],
        "municode": lambda slug: [
            "municodemeetings.com",
            f"{slug}.municodemeetings.com",
        ],
        "escribe": lambda slug: [
            f"{slug}.escribemeetings.com",
            "escribemeetings.com",
        ],
    }

    @classmethod
    def validate_packet_url(
        cls,
        packet_url: Optional[str],
        city_banana: str,
        city_name: str,
        vendor: str,
        slug: str,
    ) -> Dict[str, Any]:
        """
        Validate that packet_url domain matches vendor/slug configuration.

        Args:
            packet_url: URL to meeting packet PDF
            city_banana: City banana identifier
            city_name: Human-readable city name
            vendor: Configured vendor name
            slug: Configured vendor slug

        Returns:
            {
                'valid': bool,
                'warning': str (if valid but suspicious),
                'error': str (if invalid),
                'action': 'store' | 'warn' | 'reject'
            }
        """
        # No packet URL is OK (meeting without packet)
        if not packet_url:
            return {"valid": True, "action": "store"}

        # Extract domain from packet URL
        if packet_url.startswith("http"):
            domain = urlparse(packet_url).netloc.lower()
        elif packet_url.startswith("//"):
            # Protocol-relative URL like //s3.amazonaws.com/...
            parts = packet_url.split("/")
            domain = parts[2].lower() if len(parts) > 2 else ""
        else:
            # Relative URL or malformed - can't validate
            logger.warning(
                f"[{city_banana}] Cannot validate relative/malformed URL: {packet_url}"
            )
            return {
                "valid": True,
                "warning": f"Relative/malformed URL: {packet_url}",
                "action": "warn",
            }

        # Get expected domains for this vendor
        if vendor not in cls.VENDOR_DOMAINS:
            # Unknown vendor - can't validate, but don't block
            logger.warning(
                f"[{city_banana}] Unknown vendor '{vendor}' - cannot validate"
            )
            return {
                "valid": True,
                "warning": f"Unknown vendor: {vendor}",
                "action": "warn",
            }

        expected_domains = cls.VENDOR_DOMAINS[vendor](slug)

        # Check if domain matches any expected pattern
        domain_matches = any(
            expected.lower() in domain for expected in expected_domains
        )

        if domain_matches:
            return {"valid": True, "action": "store"}

        # Domain mismatch - this is data corruption!
        error_msg = (
            f"Domain mismatch for {city_name}: "
            f"packet_url domain '{domain}' does not match vendor '{vendor}' slug '{slug}' "
            f"(expected: {expected_domains})"
        )

        logger.error(f"[{city_banana}] CORRUPTION DETECTED: {error_msg}")
        logger.error(f"[{city_banana}] Packet URL: {packet_url}")

        return {
            "valid": False,
            "error": error_msg,
            "action": "reject",
            "details": {
                "packet_url": packet_url,
                "domain": domain,
                "expected_domains": expected_domains,
                "city_banana": city_banana,
                "city_name": city_name,
                "vendor": vendor,
                "slug": slug,
            },
        }

    @classmethod
    def validate_and_store(
        cls,
        meeting_data: Dict[str, Any],
        city_banana: str,
        city_name: str,
        vendor: str,
        slug: str,
    ) -> bool:
        """
        Validate meeting and return whether it should be stored.

        Args:
            meeting_data: Meeting dict with 'packet_url' field
            city_banana: City banana identifier
            city_name: Human-readable city name
            vendor: Configured vendor name
            slug: Configured vendor slug

        Returns:
            True if meeting should be stored, False if rejected
        """
        packet_url = meeting_data.get("packet_url")

        validation = cls.validate_packet_url(
            packet_url, city_banana, city_name, vendor, slug
        )

        if validation["action"] == "reject":
            logger.error(
                f"[{city_banana}] REJECTING meeting due to corruption: "
                f"{meeting_data.get('title', 'Unknown')}"
            )
            logger.error(f"[{city_banana}] Reason: {validation['error']}")
            return False

        if validation["action"] == "warn":
            logger.warning(
                f"[{city_banana}] Storing meeting with warning: "
                f"{meeting_data.get('title', 'Unknown')}"
            )
            logger.warning(f"[{city_banana}] Warning: {validation.get('warning')}")

        return True
