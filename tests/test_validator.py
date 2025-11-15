"""
Test suite for MeetingValidator

Tests domain validation for packet_url, agenda_url, and attachment URLs
to prevent data corruption and security issues.

Run with: python -m unittest tests.test_validator
"""

import unittest

from vendors.validator import MeetingValidator


class TestMeetingValidator(unittest.TestCase):
    """Test suite for URL validation"""

    def setUp(self):
        """Set up test fixtures"""
        self.city_banana = "testcityCA"
        self.city_name = "Test City"
        self.vendor = "legistar"
        self.slug = "testcity"

    def test_validate_url_legistar_valid_packet_url(self):
        """Test that valid Legistar packet URLs pass validation"""
        valid_urls = [
            "https://legistar.granicus.com/testcity/meetings/2025/1/agenda.pdf",
            "https://legistar1.granicus.com/testcity/AgendaPacket.pdf",
            "https://testcity.legistar.com/View.ashx?M=A&ID=123",
        ]

        for url in valid_urls:
            with self.subTest(url=url):
                result = MeetingValidator.validate_url(
                    url, "packet_url", self.city_banana, self.city_name, self.vendor, self.slug
                )
                self.assertTrue(result["valid"], f"Should accept valid Legistar URL: {url}")
                self.assertEqual(result["action"], "store")

    def test_validate_url_legistar_valid_agenda_url(self):
        """Test that valid Legistar agenda URLs pass validation"""
        valid_urls = [
            "https://legistar.granicus.com/testcity/meetings/2025/1/agenda.html",
            "https://legistar2.granicus.com/testcity/Calendar.aspx",
            "https://testcity.legistar1.com/MeetingDetail.aspx?ID=456",
        ]

        for url in valid_urls:
            with self.subTest(url=url):
                result = MeetingValidator.validate_url(
                    url, "agenda_url", self.city_banana, self.city_name, self.vendor, self.slug
                )
                self.assertTrue(result["valid"], f"Should accept valid Legistar URL: {url}")
                self.assertEqual(result["action"], "store")

    def test_validate_url_reject_wrong_vendor_domain(self):
        """Test that URLs from wrong vendor domains are rejected"""
        # Configured for Legistar, but URL is from PrimeGov
        wrong_url = "https://testcity.primegov.com/meetings/agenda.pdf"

        result = MeetingValidator.validate_url(
            wrong_url, "packet_url", self.city_banana, self.city_name, self.vendor, self.slug
        )

        self.assertFalse(result["valid"], "Should reject URL from wrong vendor")
        self.assertEqual(result["action"], "reject")
        self.assertIn("Domain mismatch", result["error"])

    def test_validate_url_reject_malicious_domain(self):
        """Test that URLs from completely unknown domains are rejected"""
        malicious_urls = [
            "https://attacker.com/malware.pdf",
            "https://evil.ru/payload.pdf",
            "https://random-domain.xyz/agenda.pdf",
        ]

        for url in malicious_urls:
            with self.subTest(url=url):
                result = MeetingValidator.validate_url(
                    url, "packet_url", self.city_banana, self.city_name, self.vendor, self.slug
                )
                self.assertFalse(result["valid"], f"Should reject malicious URL: {url}")
                self.assertEqual(result["action"], "reject")

    def test_validate_url_null_url_is_valid(self):
        """Test that None/null URLs are considered valid (meetings without that URL type)"""
        result = MeetingValidator.validate_url(
            None, "packet_url", self.city_banana, self.city_name, self.vendor, self.slug
        )

        self.assertTrue(result["valid"], "None URL should be valid (meeting without packet)")
        self.assertEqual(result["action"], "store")

    def test_validate_url_relative_url_warns(self):
        """Test that relative URLs generate warnings but don't reject"""
        relative_urls = [
            "/meetings/agenda.pdf",
            "../documents/packet.pdf",
            "agenda.pdf",
        ]

        for url in relative_urls:
            with self.subTest(url=url):
                result = MeetingValidator.validate_url(
                    url, "packet_url", self.city_banana, self.city_name, self.vendor, self.slug
                )
                self.assertTrue(result["valid"], "Relative URL should be valid with warning")
                self.assertEqual(result["action"], "warn")
                self.assertIn("Relative/malformed", result["warning"])

    def test_validate_and_store_both_urls_valid(self):
        """Test that meetings with both valid URLs are accepted"""
        meeting_data = {
            "packet_url": "https://legistar.granicus.com/testcity/packet.pdf",
            "agenda_url": "https://legistar.granicus.com/testcity/agenda.html",
            "title": "City Council Meeting",
        }

        result = MeetingValidator.validate_and_store(
            meeting_data, self.city_banana, self.city_name, self.vendor, self.slug
        )

        self.assertTrue(result, "Meeting with both valid URLs should be stored")

    def test_validate_and_store_reject_bad_packet_url(self):
        """Test that meetings with invalid packet_url are rejected"""
        meeting_data = {
            "packet_url": "https://attacker.com/malware.pdf",
            "agenda_url": "https://legistar.granicus.com/testcity/agenda.html",
            "title": "City Council Meeting",
        }

        result = MeetingValidator.validate_and_store(
            meeting_data, self.city_banana, self.city_name, self.vendor, self.slug
        )

        self.assertFalse(result, "Meeting with bad packet_url should be rejected")

    def test_validate_and_store_reject_bad_agenda_url(self):
        """
        Test that meetings with invalid agenda_url are rejected.

        This is the critical test for the security gap fix: agenda_url validation
        prevents malicious/misconfigured URLs from being processed.
        """
        meeting_data = {
            "packet_url": "https://legistar.granicus.com/testcity/packet.pdf",
            "agenda_url": "https://attacker.com/malicious-agenda.html",
            "title": "City Council Meeting",
        }

        result = MeetingValidator.validate_and_store(
            meeting_data, self.city_banana, self.city_name, self.vendor, self.slug
        )

        self.assertFalse(result, "Meeting with bad agenda_url should be rejected")

    def test_validate_and_store_only_packet_url(self):
        """Test that monolithic meetings (packet_url only) are validated correctly"""
        meeting_data = {
            "packet_url": "https://legistar.granicus.com/testcity/packet.pdf",
            "agenda_url": None,
            "title": "City Council Meeting",
        }

        result = MeetingValidator.validate_and_store(
            meeting_data, self.city_banana, self.city_name, self.vendor, self.slug
        )

        self.assertTrue(result, "Monolithic meeting with valid packet_url should be stored")

    def test_validate_and_store_only_agenda_url(self):
        """Test that item-based meetings (agenda_url only) are validated correctly"""
        meeting_data = {
            "packet_url": None,
            "agenda_url": "https://legistar.granicus.com/testcity/agenda.html",
            "title": "City Council Meeting",
        }

        result = MeetingValidator.validate_and_store(
            meeting_data, self.city_banana, self.city_name, self.vendor, self.slug
        )

        self.assertTrue(result, "Item-based meeting with valid agenda_url should be stored")

    def test_validate_url_primegov_domains(self):
        """Test PrimeGov domain validation"""
        result = MeetingValidator.validate_url(
            "https://testcity.primegov.com/Portal/Meeting?id=123",
            "agenda_url",
            "testcityCA",
            "Test City",
            "primegov",
            "testcity"
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["action"], "store")

    def test_validate_url_granicus_s3_domains(self):
        """Test that Granicus S3/CloudFront CDN URLs are accepted"""
        cdn_urls = [
            "https://s3.amazonaws.com/granicus-testcity/packet.pdf",
            "https://d12345.cloudfront.net/meetings/agenda.pdf",
        ]

        for url in cdn_urls:
            with self.subTest(url=url):
                result = MeetingValidator.validate_url(
                    url, "packet_url", self.city_banana, self.city_name, "granicus", self.slug
                )
                self.assertTrue(result["valid"], f"Should accept Granicus CDN URL: {url}")
                self.assertEqual(result["action"], "store")

    def test_validate_url_protocol_relative(self):
        """Test protocol-relative URLs (//domain/path)"""
        url = "//s3.amazonaws.com/granicus-testcity/packet.pdf"

        result = MeetingValidator.validate_url(
            url, "packet_url", self.city_banana, self.city_name, "granicus", self.slug
        )

        self.assertTrue(result["valid"], "Protocol-relative URL should be valid")
        self.assertEqual(result["action"], "store")

    def test_validate_url_unknown_vendor_warns(self):
        """Test that unknown vendors generate warnings but don't reject"""
        result = MeetingValidator.validate_url(
            "https://unknown-vendor.com/agenda.pdf",
            "packet_url",
            self.city_banana,
            self.city_name,
            "unknown_vendor",
            self.slug
        )

        self.assertTrue(result["valid"], "Unknown vendor should warn but not reject")
        self.assertEqual(result["action"], "warn")
        self.assertIn("Unknown vendor", result["warning"])


if __name__ == "__main__":
    unittest.main()
