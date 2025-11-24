"""
Meeting validation layer to prevent data corruption.

Validates that packet URLs match configured vendor/slug before storing meetings.
"""

from urllib.parse import urlparse
from typing import Optional, Dict, Any

from config import get_logger

logger = get_logger(__name__).bind(component="vendor")


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
        # Custom city adapters
        "menlopark": lambda slug: ["menlopark.gov"],
        "berkeley": lambda slug: ["berkeleyca.gov"],
        "chicago": lambda slug: ["occprodstoragev1.blob.core.usgovcloudapi.net"],
    }

    @classmethod
    def validate_url(
        cls,
        url: Optional[str],
        url_type: str,
        city_banana: str,
        city_name: str,
        vendor: str,
        slug: str,
    ) -> Dict[str, Any]:
        """
        Validate that URL domain matches vendor/slug configuration.

        Args:
            url: URL to validate (packet_url, agenda_url, or attachment)
            url_type: Type of URL for logging ('packet_url', 'agenda_url', 'attachment')
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
        # No URL is OK (meeting without this URL type)
        if not url:
            return {"valid": True, "action": "store"}

        # Note: eScribe adapter may return List[str] for packet_url (multiple PDFs).
        # Not implemented here since validator not used in production (only in tests).
        # If integrating validator into production, normalize List[str] to single URL.

        # Extract domain from URL
        if url.startswith("http"):
            domain = urlparse(url).netloc.lower()
        elif url.startswith("//"):
            # Protocol-relative URL like //s3.amazonaws.com/...
            parts = url.split("/")
            domain = parts[2].lower() if len(parts) > 2 else ""
        else:
            # Relative URL or malformed - can't validate
            logger.warning(
                f"[{city_banana}] Cannot validate relative/malformed {url_type}: {url}"
            )
            return {
                "valid": True,
                "warning": f"Relative/malformed {url_type}: {url}",
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
        error_msg = f"Domain mismatch: {domain} not in {expected_domains}"

        logger.error(
            f"[{city_banana}] {url_type} validation failed: {error_msg}",
            extra={
                "city_banana": city_banana,
                "domain": domain,
                "expected": expected_domains,
                "vendor": vendor,
                "url_type": url_type,
                "url": url,
            }
        )

        return {
            "valid": False,
            "error": error_msg,
            "action": "reject",
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

        Backwards-compatible wrapper around validate_url().

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
        return cls.validate_url(
            packet_url, "packet_url", city_banana, city_name, vendor, slug
        )

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

        Validates both packet_url and agenda_url against expected vendor domains.
        Rejects meeting if either URL fails validation.

        Args:
            meeting_data: Meeting dict with 'packet_url' and 'agenda_url' fields
            city_banana: City banana identifier
            city_name: Human-readable city name
            vendor: Configured vendor name
            slug: Configured vendor slug

        Returns:
            True if meeting should be stored, False if rejected
        """
        packet_url = meeting_data.get("packet_url")
        agenda_url = meeting_data.get("agenda_url")

        # Validate packet_url
        packet_validation = cls.validate_packet_url(
            packet_url, city_banana, city_name, vendor, slug
        )

        # Validate agenda_url
        agenda_validation = cls.validate_url(
            agenda_url, "agenda_url", city_banana, city_name, vendor, slug
        )

        # Reject if either URL fails validation
        if packet_validation["action"] == "reject":
            logger.error(
                "rejecting meeting due to packet_url corruption",
                city_banana=city_banana,
                meeting_title=meeting_data.get('title', 'Unknown'),
                reason=packet_validation['error']
            )
            return False

        if agenda_validation["action"] == "reject":
            logger.error(
                "rejecting meeting due to agenda_url corruption",
                city_banana=city_banana,
                meeting_title=meeting_data.get('title', 'Unknown'),
                reason=agenda_validation['error']
            )
            return False

        # Warn if either URL is suspicious
        if packet_validation["action"] == "warn":
            logger.warning(
                "storing meeting with packet_url warning",
                city_banana=city_banana,
                meeting_title=meeting_data.get('title', 'Unknown'),
                warning=packet_validation.get('warning')
            )

        if agenda_validation["action"] == "warn":
            logger.warning(
                "storing meeting with agenda_url warning",
                city_banana=city_banana,
                meeting_title=meeting_data.get('title', 'Unknown'),
                warning=agenda_validation.get('warning')
            )

        return True
