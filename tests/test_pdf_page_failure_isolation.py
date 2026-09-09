"""A MuPDF allocation failure on one page must not discard the document."""

import fitz
import pytest

from parsing.pdf import PdfExtractor


def _two_page_pdf() -> bytes:
    document = fitz.open()
    for index in range(2):
        page = document.new_page()
        body = f"Page {index + 1} council staff report text. " * 20
        page.insert_text((72, 100), body[:400], fontsize=11)
    data = document.tobytes()
    document.close()
    return data


def _extractor() -> PdfExtractor:
    return PdfExtractor(ocr_enabled=False)


def test_realloc_failure_on_one_page_marks_it_partial(monkeypatch):
    original = fitz.Page.get_text
    calls = {"n": 0}

    def flaky_get_text(self, *args, **kwargs):
        calls["n"] += 1
        if self.number == 1:
            raise RuntimeError("code=2: realloc (48837532 bytes) failed")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(fitz.Page, "get_text", flaky_get_text)
    result = _extractor().extract_from_bytes(_two_page_pdf())

    assert result["success"] is True
    assert "Page 1 council staff report" in result["text"]
    assert result["page_count"] == 2
    assert result["ocr_pending"] == 1
    # The failing page was retried once on the plain text layer before giving up.
    assert calls["n"] >= 3


def test_clean_document_is_unaffected():
    result = _extractor().extract_from_bytes(_two_page_pdf())
    assert result["success"] is True
    assert result["ocr_pending"] == 0
    assert "Page 2 council staff report" in result["text"]


def test_document_level_failure_still_raises():
    from exceptions import ExtractionError

    with pytest.raises(ExtractionError):
        _extractor().extract_from_bytes(b"%PDF-not-really")


def test_extraction_timeout_scales_with_pages(tmp_path, monkeypatch):
    from analysis.analyzer_async import (
        DOCUMENT_EXTRACTION_MAX_SECONDS,
        DOCUMENT_EXTRACTION_TIMEOUT_SECONDS,
        extraction_timeout_for,
    )

    small = tmp_path / "small.pdf"
    small.write_bytes(_two_page_pdf())
    assert extraction_timeout_for(str(small)) == DOCUMENT_EXTRACTION_TIMEOUT_SECONDS

    document = fitz.open()
    for _ in range(900):
        document.new_page()
    big = tmp_path / "big.pdf"
    big.write_bytes(document.tobytes())
    document.close()

    # The forkserver child imports a fresh parsing module. Native inspection
    # in this process is forbidden, including the timeout's metadata probe.
    def forbidden_parent_open(*args, **kwargs):
        raise AssertionError("PDF opened outside guarded child")

    monkeypatch.setattr(fitz, "open", forbidden_parent_open)
    scaled = extraction_timeout_for(str(big))
    assert DOCUMENT_EXTRACTION_TIMEOUT_SECONDS < scaled <= DOCUMENT_EXTRACTION_MAX_SECONDS
    assert scaled == 300 + 1.5 * 900

    garbage = tmp_path / "garbage.pdf"
    garbage.write_bytes(b"not a pdf")
    assert extraction_timeout_for(str(garbage)) == DOCUMENT_EXTRACTION_TIMEOUT_SECONDS
    assert extraction_timeout_for("/tmp/x.docx") == DOCUMENT_EXTRACTION_TIMEOUT_SECONDS


def test_geometry_scan_failure_preserves_text_but_cannot_certify_formatting(monkeypatch):
    import parsing.pdf as pdf_module

    original = pdf_module._detect_horizontal_lines

    def failing_geometry(page):
        if page.number == 1:
            raise RuntimeError("code=2: geometry allocation failed")
        return original(page)

    monkeypatch.setattr(pdf_module, "_detect_horizontal_lines", failing_geometry)
    result = _extractor().extract_from_bytes(_two_page_pdf())
    assert result["success"] is True
    assert "Page 1 council staff report" in result["text"]
    assert "Page 2 council staff report" in result["text"]
    assert result["ocr_pending_pages"] == [2]
    assert result["method"].endswith("-partial")
