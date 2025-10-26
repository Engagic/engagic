use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use poppler::Document;
use unicode_normalization::UnicodeNormalization;
use regex::Regex;

use super::downloader::PdfDownloader;
use super::validator::TextValidator;

const MAX_PAGES: usize = 1000;

#[pyclass]
pub struct PdfExtractor {
    downloader: PdfDownloader,
    validator: TextValidator,
    max_pages: usize,
}

#[pymethods]
impl PdfExtractor {
    #[new]
    pub fn new() -> Self {
        Self {
            downloader: PdfDownloader::new(),
            validator: TextValidator::new(),
            max_pages: MAX_PAGES,
        }
    }

    /// Download and extract text from PDF URL
    /// Returns (text, page_count) or None if extraction fails
    pub fn extract_from_url(&self, url: &str) -> PyResult<Option<PdfExtractionResult>> {
        // Download PDF
        let pdf_bytes = self.downloader
            .download(url)
            .map_err(|e| PyValueError::new_err(format!("Download failed: {}", e)))?;

        // Extract text
        self.extract_from_bytes(&pdf_bytes)
    }

    /// Extract text from PDF bytes
    /// Confidence: 9/10 - poppler handles Identity-H and other complex encodings
    pub fn extract_from_bytes(&self, pdf_bytes: &[u8]) -> PyResult<Option<PdfExtractionResult>> {
        // Load PDF document using poppler
        let document = Document::from_data(pdf_bytes, None)
            .map_err(|e| PyValueError::new_err(format!("PDF parsing failed: {}", e)))?;

        let page_count = document.n_pages() as usize;

        // Limit pages
        let pages_to_process = page_count.min(self.max_pages);

        // Extract text from each page
        let mut all_text = Vec::new();

        for page_num in 0..pages_to_process {
            match document.page(page_num as i32) {
                Some(page) => {
                    if let Some(text) = page.text() {
                        if !text.is_empty() {
                            all_text.push(format!("--- PAGE {} ---\n{}", page_num + 1, text));
                        }
                    }
                }
                None => {
                    tracing::debug!("Failed to get page {}", page_num + 1);
                }
            }
        }

        if all_text.is_empty() {
            tracing::warn!("No text extracted from PDF");
            return Ok(None);
        }

        let combined_text = all_text.join("\n");

        // Normalize and validate
        let normalized = normalize_text(&combined_text);

        // Debug: show text preview before validation
        let preview = if normalized.len() > 500 {
            &normalized[..500]
        } else {
            &normalized
        };
        tracing::debug!(
            "Extracted text preview (first 500 chars): {}...",
            preview.replace('\n', " ")
        );

        // Validate quality
        if !self.validator.is_good_quality(&normalized) {
            return Ok(None);
        }

        Ok(Some(PdfExtractionResult {
            text: normalized,
            page_count,
            pages_processed: pages_to_process,
        }))
    }

    /// Validate text quality without extraction
    pub fn validate_text(&self, text: &str) -> bool {
        self.validator.is_good_quality(text)
    }
}

#[pyclass]
#[derive(Clone)]
pub struct PdfExtractionResult {
    #[pyo3(get)]
    pub text: String,
    #[pyo3(get)]
    pub page_count: usize,
    #[pyo3(get)]
    pub pages_processed: usize,
}

// Normalize extracted text
fn normalize_text(text: &str) -> String {
    // Unicode normalization
    let normalized: String = text.nfc().collect();

    // Remove excessive whitespace
    let re_newlines = Regex::new(r"\n{3,}").unwrap();
    let re_spaces = Regex::new(r" {2,}").unwrap();

    let cleaned = re_newlines.replace_all(&normalized, "\n\n");
    let cleaned = re_spaces.replace_all(&cleaned, " ");

    // Fix common extraction issues
    let cleaned = cleaned.replace('|', "I");  // Common OCR mistake
    let cleaned = cleaned.replace('‚', ",");  // Unicode comma issue

    cleaned.trim().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_text() {
        let input = "Hello   world\n\n\n\nTest";
        let output = normalize_text(input);
        assert_eq!(output, "Hello world\n\nTest");
    }

    #[test]
    fn test_extractor_creation() {
        let extractor = PdfExtractor::new();
        assert_eq!(extractor.max_pages, MAX_PAGES);
    }
}
