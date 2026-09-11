"""Durable identifier extraction: instrument numbers and title codes.

Every case here came from a real title that misfired during the 2026-09-11
parity pass; the labelled-handle cases live in test_escribe_adapter.py.
"""

import pytest

from parsing.identifiers import extract_identifier, extract_leading_file_token


class TestInstrumentNumbers:
    def test_resolution_and_ordinance_are_namespaced(self):
        assert extract_identifier("Resolution No. 2026-080 authorizing a HOME application") == (
            "Resolution 2026-080", "Resolution",
        )
        assert extract_identifier("Ordinance No. 2026-76 - Introduced by Council") == (
            "Ordinance 2026-76", "Ordinance",
        )

    def test_council_bill_forms(self):
        assert extract_identifier("Council Bill 2026-137 (Horton)")[0] == "Bill 2026-137"
        assert extract_identifier("First reading of Council Bill No. 10-26, an ordinance")[0] == "Bill 10-26"
        assert extract_identifier("Board Bill 107 Redevelopment plan")[0] == "Bill 107"

    def test_state_legislation_citation_is_not_a_city_bill(self):
        assert extract_identifier(
            "Annual Military Equipment Use Report 2025, per CA Assembly Bill No. 481"
        ) is None

    def test_amended_instrument_is_a_citation_not_the_item(self):
        assert extract_identifier(
            "Resolution No. _____ amending Resolution No. 1804 to authorize a lease"
        ) is None

    def test_body_citation_beyond_head_is_ignored(self):
        body = "x" * 400 + " as required by Ordinance No. 1187."
        assert extract_identifier("Discussion of pocket park concepts", body) is None

    def test_comma_thousands_ordinance(self):
        assert extract_identifier("Lease Agreement: ICRI", "adopt Ordinance No. 7,891-N.S. authorizing")[0] == (
            "Ordinance 7,891-N.S"
        )

    def test_bare_year_is_rejected(self):
        assert extract_identifier("Ordinance No. 2026") is None

    def test_labelled_handle_outranks_instrument(self):
        assert extract_identifier("Resolution No. 2026-14 approving Contract No. 12345 with Acme") == (
            "Contract 12345", "Contract",
        )


class TestFileNumberShapes:
    def test_case_file_with_dashed_suffix_is_whole(self):
        assert extract_identifier("CASE FILE NO. 2026-07-V") == ("File 2026-07-V", "File")
        assert extract_identifier("CASE FILE NO. 2025-90-P(ETJ)")[0] == "File 2025-90-P"

    def test_plain_file_number_still_keys(self):
        assert extract_identifier("File No. 15120 workers comp")[0] == "File 15120"


class TestTitleCodes:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("2026-469 Advisory Boards and Committee Reports", "2026-469"),
            ("22-1200-S49CD 13Motion relative to the reappointment", "22-1200-S49"),
            ("2026-05-19 Architectural Review Board Meeting Minutes", None),
            ("2027-28 Urban Forestry Work Plan", None),
            ("2026-2027 Operating Budget", None),
            ("2026-0615 Review", None),
            ("Approval of minutes 03-25", None),
        ],
    )
    def test_leading_file_token(self, title, expected):
        assert extract_leading_file_token(title) == expected

    def test_parenthesised_department_code(self):
        assert extract_identifier("(PC-11015) Application by Trinity Presbyterian Church to rezone") == (
            "PC-11015", None,
        )

    def test_dash_codes_keep_trailing_groups(self):
        assert extract_identifier("ZON-26-05-0014 - Zoning Change/Concept Plan")[0] == "ZON-26-05-0014"
        assert extract_identifier("CU-26-012 Conditional use permit for 12 Main St")[0] == "CU-26-012"

    def test_year_last_dash_code(self):
        assert extract_identifier("O-079-26 AN ORDINANCE AMENDING ORDINANCE NO. 102, SERIES 2016")[0] == "O-079-26"

    def test_date_like_committee_code_does_not_key(self):
        assert extract_identifier("CC-06-15 Committee report on parks") is None
