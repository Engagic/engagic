"""
Utility to construct vendor source URLs for attribution
"""

import json
import os
from typing import Optional

from config import config
from config import get_logger

log = get_logger("engagic.vendor_urls")


def _get_granicus_url(slug: str) -> Optional[str]:
    """
    Get Granicus URL with city-specific view_id from cache.

    Returns a single URL for the primary view.  When multiple view_ids
    exist (e.g. Board of Supervisors + Planning Commission), uses the
    first entry.  For multi-body display, use _get_granicus_urls().
    """
    urls = _get_granicus_urls(slug)
    return urls[0]["url"] if urls else f"https://{slug}.granicus.com/ViewPublisher.php"


def _get_granicus_urls(slug: str) -> list:
    """
    Get all Granicus calendar URLs for a city.

    Returns list of {"url": ..., "body": ...} dicts.
    Most cities have a single entry; some (e.g. Marin County) have
    multiple view_ids for different governing bodies.
    """
    view_ids_file = os.path.join(config.DB_DIR, "granicus_view_ids.json")
    base_url = f"https://{slug}.granicus.com"

    if os.path.exists(view_ids_file):
        try:
            with open(view_ids_file, "r") as f:
                mappings = json.load(f)
                entry = mappings.get(base_url)

                if isinstance(entry, list):
                    # Multi-body: [{"view_id": 33, "body": "Board of Supervisors"}, ...]
                    return [
                        {
                            "url": f"{base_url}/ViewPublisher.php?view_id={e['view_id']}",
                            "body": e.get("body", ""),
                        }
                        for e in entry
                    ]
                elif entry:
                    # Single view_id (int)
                    return [{"url": f"{base_url}/ViewPublisher.php?view_id={entry}", "body": ""}]
        except Exception:
            log.warning("failed to read granicus view_ids", file=view_ids_file, slug=slug)

    return [{"url": f"{base_url}/ViewPublisher.php", "body": ""}]


def _get_municode_url(slug: str) -> str:
    """
    Get Municode URL based on slug format.

    - Hyphenated slugs (columbus-ga) -> subdomain API
    - Short codes (CPTX) -> PublishPage
    """
    if "-" in slug:
        # Subdomain pattern: columbus-ga.municodemeetings.com
        return f"https://{slug}.municodemeetings.com"
    else:
        # PublishPage pattern: meetings.municode.com/PublishPage?cid=CPTX
        return f"https://meetings.municode.com/PublishPage/index?cid={slug.upper()}"


def _get_onbase_url(slug: str) -> Optional[str]:
    """
    Get OnBase URL from config file.

    OnBase deployments vary (Hyland Cloud, self-hosted), so URLs are stored
    in data/onbase_sites.json keyed by city slug.
    """
    config_file = os.path.join(config.DB_DIR, "onbase_sites.json")

    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                sites = json.load(f)
                urls = sites.get(slug, [])
                if urls:
                    return f"https://{urls[0]}"
        except Exception:
            log.warning("failed to read onbase config", file=config_file, slug=slug)
            return None

    log.warning("onbase config not found", file=config_file)
    return None


def get_vendor_source_url(vendor: str, slug: str) -> Optional[str]:
    """
    Construct the source URL for a city's meeting calendar based on vendor and slug.

    Args:
        vendor: Vendor name (legistar, primegov, granicus, etc.)
        slug: City-specific slug used by the vendor

    Returns:
        Full URL to the city's calendar page, or None if vendor unknown

    Example:
        get_vendor_source_url("legistar", "sfgov")
        -> "https://sfgov.legistar.com/Calendar.aspx"
    """
    vendor = vendor.lower().strip()

    # Special handling for Granicus - requires city-specific view_id
    if vendor == "granicus":
        return _get_granicus_url(slug)

    # Special handling for Municode - two URL patterns based on slug format
    if vendor == "municode":
        return _get_municode_url(slug)

    # Special handling for OnBase - URLs vary by deployment, load from config
    if vendor == "onbase":
        return _get_onbase_url(slug)

    vendor_patterns = {
        "legistar": f"https://{slug}.legistar.com/Calendar.aspx",
        "primegov": f"https://{slug}.primegov.com/public/portal",
        "iqm2": f"https://{slug}.iqm2.com/Citizens/Calendar.aspx",
        "novusagenda": f"https://{slug}.novusagenda.com/agendapublic",
        "escribe": f"https://{slug}.escribemeetings.com",
        "civicclerk": f"https://{slug}.portal.civicclerk.com",
        "civicplus": f"https://{slug}.civicplus.com/AgendaCenter",
        "civicengage": f"https://{slug}.gov/Archive.aspx",
        "civicweb": f"https://{slug}.civicweb.net/Portal",
        "visioninternet": None,  # Varies per site, loaded from config
        "proudcity": f"https://{slug}.gov/meetings",
        "wp_events": None,  # WordPress-based, varies per site
        # Custom adapters
        "berkeley": "https://berkeleyca.gov/your-government/city-council/city-council-agendas",
        "chicago": "https://chicityclerkelms.chicago.gov/Meetings/",
        "menlopark": "https://menlopark.gov/Agendas-and-minutes",
        "destiny": f"https://public.destinyhosted.com/agenda_publish.cfm?id={slug}",
    }

    return vendor_patterns.get(vendor)


def get_vendor_source_urls(vendor: str, slug: str) -> list:
    """
    Get all source URLs for a vendor, with optional body labels.

    Returns list of {"url": ..., "body": ...} dicts.  Most vendors return
    a single entry.  Granicus cities with multiple view_ids return one
    entry per governing body.  Only populated when there are multiple
    sources worth displaying.
    """
    if vendor.lower().strip() == "granicus":
        urls = _get_granicus_urls(slug)
        if len(urls) > 1:
            return urls
    return []


def get_vendor_display_name(vendor: str) -> str:
    """
    Get human-readable display name for vendor.

    Args:
        vendor: Vendor identifier

    Returns:
        Display name for the vendor
    """
    vendor = vendor.lower().strip()

    display_names = {
        "legistar": "Legistar",
        "primegov": "PrimeGov",
        "granicus": "Granicus",
        "iqm2": "iQM2",
        "novusagenda": "NovusAgenda",
        "escribe": "eScribe",
        "civicclerk": "CivicClerk",
        "civicplus": "CivicPlus",
        "civicengage": "CivicEngage",
        "civicweb": "CivicWeb",
        "visioninternet": "Vision Internet",
        "proudcity": "ProudCity",
        "wp_events": "City Website",
        "onbase": "OnBase Agenda Online",
        "municode": "Municode",
        # Custom adapters
        "berkeley": "City of Berkeley",
        "chicago": "City of Chicago",
        "menlopark": "City of Menlo Park",
        "ross": "Town of Ross",
        "destiny": "Destiny AgendaQuick",
    }

    return display_names.get(vendor, vendor.title())
