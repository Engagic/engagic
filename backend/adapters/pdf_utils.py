#!/usr/bin/env python3
"""
Shared utilities for deep-scraping PDF links from meeting detail pages
Used by multiple adapters (Legistar, CivicPlus, etc.)
"""

import requests
import logging
import re
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import List

logger = logging.getLogger("engagic")

DEFAULT_HEADERS = {
    "User-Agent": "Engagic/1.0 (Civic Engagement Bot; Engagic Is For The People)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def deep_scrape_pdfs(
    detail_url: str, base_url: str = None, max_depth: int = 2
) -> List[str]:
    """
    Generic deep scraper for finding PDF links on detail pages.

    Args:
        detail_url: The URL to scrape for PDFs
        base_url: Base URL for relative links (if not provided, extracted from detail_url)
        max_depth: Maximum recursion depth for following links

    Returns:
        List of PDF URLs found
    """
    scrape_start = time.time()

    if not base_url:
        parsed = urlparse(detail_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

    found_pdfs = set()
    visited_urls = set()
    depth_stats = {i: 0 for i in range(max_depth + 1)}
    pages_scraped_by_depth = {i: 0 for i in range(max_depth + 1)}

    logger.debug(f"[DeepScrape] Starting at {detail_url} (max_depth={max_depth})")

    # Normalize the original URL to compare against
    original_url_normalized = detail_url.rstrip("/").lower()
    original_path = urlparse(detail_url).path.rstrip("/").lower()

    def _scrape_page(url: str, depth: int = 0, parent_url: str = None):
        """Recursively scrape a page for PDFs"""
        if depth > max_depth or url in visited_urls:
            return

        visited_urls.add(url)
        pages_scraped_by_depth[depth] += 1
        logger.debug(f"[DeepScrape] Depth {depth}: Scraping {url}")

        try:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")

            # Find all links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                link_text = link.get_text().strip().lower()

                # Make absolute URL
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    full_url = urljoin(base_url, href)
                else:
                    full_url = urljoin(url, href)

                # Skip self-referential links (anchors to same page)
                if href.startswith("#"):
                    continue

                # Skip if this links back to the original URL we're scraping
                full_url_normalized = full_url.rstrip("/").lower()
                full_url_path = urlparse(full_url).path.rstrip("/").lower()

                # Check if it's linking back to the original page (or parent)
                if (
                    full_url_normalized == original_url_normalized
                    or full_url_path == original_path
                    or (
                        parent_url
                        and full_url_normalized == parent_url.rstrip("/").lower()
                    )
                ):
                    logger.debug(f"Skipping self-referential link: {full_url}")
                    continue

                # Check if it's a PDF
                if is_pdf_url(full_url, link_text):
                    found_pdfs.add(full_url)
                    depth_stats[depth] += 1
                    logger.debug(f"[DeepScrape] Depth {depth}: Found PDF {full_url}")

                # Check if we should follow this link deeper
                elif depth < max_depth and should_follow_link(full_url, link_text):
                    # Recursively scrape this page
                    time.sleep(0.3)  # Be polite
                    _scrape_page(full_url, depth + 1, parent_url=url)

        except Exception as e:
            logger.warning(f"Failed to scrape {url}: {e}")

    # Start scraping
    _scrape_page(detail_url, parent_url=detail_url)

    elapsed = time.time() - scrape_start

    # Log scraping statistics
    logger.info(f"[DeepScrape] Completed in {elapsed:.2f}s: Found {len(found_pdfs)} PDFs across {len(visited_urls)} pages")
    logger.debug(f"[DeepScrape] Pages scraped by depth: {dict(pages_scraped_by_depth)}")
    logger.debug(f"[DeepScrape] PDFs found by depth: {dict(depth_stats)}")

    if len(found_pdfs) > 0:
        depth_breakdown = [f"depth {d}: {count}" for d, count in sorted(depth_stats.items()) if count > 0]
        logger.info(f"[DeepScrape] PDF breakdown: {', '.join(depth_breakdown)}")

    return list(found_pdfs)


def is_pdf_url(url: str, link_text: str = "") -> bool:
    """
    Determine if a URL is likely a PDF
    """
    url_lower = url.lower()
    text_lower = link_text.lower()

    # EXCLUDE minutes - they often link to previous meetings creating loops
    if "minutes" in url_lower or "minutes" in text_lower:
        return False

    # Direct PDF extensions
    if url_lower.endswith(".pdf"):
        # Double-check it's not minutes
        if "minutes" not in url_lower:
            return True

    # Common PDF serving endpoints
    pdf_patterns = [
        r"/view\.ashx",  # Legistar
        r"/download/",
        r"/file/",
        r"/document/",
        r"/attachment/",
        r"/agenda.*packet",
        r"/meeting.*packet",
    ]

    for pattern in pdf_patterns:
        if re.search(pattern, url_lower):
            # Exclude if it contains 'minutes'
            if "minutes" not in url_lower:
                return True

    # Check link text for PDF indicators (but not minutes)
    if link_text:
        pdf_text_indicators = ["pdf", "packet", "agenda", "attachment", "document"]
        has_pdf_indicator = any(
            indicator in text_lower for indicator in pdf_text_indicators
        )
        has_minutes = "minutes" in text_lower
        return has_pdf_indicator and not has_minutes

    return False


def should_follow_link(url: str, link_text: str = "") -> bool:
    """
    Determine if we should follow a link deeper (might contain PDFs)
    """
    url_lower = url.lower()
    text_lower = link_text.lower()

    # EXCLUDE patterns that create loops or are not useful
    exclude_patterns = [
        "minutes",
        "previous",
        "past-meeting",
        "prior-meeting",
        "old-meeting",
        "back to",
        "all agendas",
        "agendacenter",  # Don't follow back to the main agenda center
    ]

    for pattern in exclude_patterns:
        if pattern in url_lower or pattern in text_lower:
            return False

    # Skip external domains
    external_domains = ["facebook.com", "twitter.com", "youtube.com", "linkedin.com"]
    if any(domain in url_lower for domain in external_domains):
        return False

    # Follow patterns that might have PDFs
    follow_patterns = [
        r"/meeting",
        r"/agenda",
        r"/legislation",
        r"/detail",
        r"/item",
        r"/attachment",
        r"/document",
    ]

    for pattern in follow_patterns:
        if re.search(pattern, url_lower):
            # Double-check it's not excluded
            if not any(excl in url_lower for excl in exclude_patterns):
                return True

    # Check link text
    if link_text:
        follow_keywords = ["detail", "view", "more", "agenda", "meeting", "item"]
        has_follow_keyword = any(keyword in text_lower for keyword in follow_keywords)
        has_exclude_keyword = any(excl in text_lower for excl in exclude_patterns)
        return has_follow_keyword and not has_exclude_keyword

    return False


def extract_pdf_urls_from_html(html: str, base_url: str) -> List[str]:
    """
    Simple extraction of PDF URLs from HTML without recursion
    """
    soup = BeautifulSoup(html, "html.parser")
    pdf_urls = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        link_text = link.get_text().strip().lower()

        # Make absolute URL
        if href.startswith("http"):
            full_url = href
        elif href.startswith("/"):
            full_url = urljoin(base_url, href)
        else:
            full_url = urljoin(base_url, href)

        if is_pdf_url(full_url, link_text):
            pdf_urls.append(full_url)

    return pdf_urls
