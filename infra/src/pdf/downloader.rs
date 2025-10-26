use reqwest::blocking::Client;
use std::time::Duration;
use thiserror::Error;

const MAX_PDF_SIZE: usize = 200 * 1024 * 1024; // 200MB
const DOWNLOAD_TIMEOUT_SECS: u64 = 30;
const MAX_RETRIES: usize = 3;

#[derive(Error, Debug)]
pub enum DownloadError {
    #[error("Network error: {0}")]
    Network(#[from] reqwest::Error),

    #[error("PDF too large: {0} bytes")]
    TooLarge(usize),

    #[error("Invalid URL: {0}")]
    InvalidUrl(String),

    #[error("All retries exhausted")]
    RetriesExhausted,
}

pub struct PdfDownloader {
    client: Client,
    max_size: usize,
    timeout: Duration,
    max_retries: usize,
}

impl PdfDownloader {
    pub fn new() -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(DOWNLOAD_TIMEOUT_SECS))
            .user_agent("Engagic-Rust-Processor/1.0")
            .build()
            .expect("Failed to create HTTP client");

        Self {
            client,
            max_size: MAX_PDF_SIZE,
            timeout: Duration::from_secs(DOWNLOAD_TIMEOUT_SECS),
            max_retries: MAX_RETRIES,
        }
    }

    /// Download PDF with retry logic
    /// Confidence: 9/10 - Retry logic is well-tested pattern
    pub fn download(&self, url: &str) -> Result<Vec<u8>, DownloadError> {
        // Validate URL
        if url.is_empty() || url.len() > 2000 {
            return Err(DownloadError::InvalidUrl(url.to_string()));
        }

        // Handle Google Docs viewer URLs
        let actual_url = self.extract_google_docs_url(url);

        let mut last_error = None;

        // Retry loop
        for attempt in 1..=self.max_retries {
            match self.download_once(&actual_url) {
                Ok(bytes) => {
                    tracing::info!(
                        "Downloaded PDF: {} bytes (attempt {})",
                        bytes.len(),
                        attempt
                    );
                    return Ok(bytes);
                }
                Err(e) => {
                    tracing::warn!(
                        "Download attempt {}/{} failed: {}",
                        attempt,
                        self.max_retries,
                        e
                    );
                    last_error = Some(e);

                    if attempt < self.max_retries {
                        // Exponential backoff: 1s, 2s, 4s
                        let delay = Duration::from_secs(2u64.pow(attempt as u32 - 1));
                        std::thread::sleep(delay);
                    }
                }
            }
        }

        // All retries failed
        match last_error {
            Some(e) => Err(e),
            None => Err(DownloadError::RetriesExhausted),
        }
    }

    fn download_once(&self, url: &str) -> Result<Vec<u8>, DownloadError> {
        let response = self.client.get(url).send()?;

        // Check status
        response.error_for_status_ref()?;

        // Check content length
        if let Some(content_length) = response.content_length() {
            if content_length as usize > self.max_size {
                return Err(DownloadError::TooLarge(content_length as usize));
            }
        }

        // Download with size checking
        let bytes = response.bytes()?;

        if bytes.len() > self.max_size {
            return Err(DownloadError::TooLarge(bytes.len()));
        }

        Ok(bytes.to_vec())
    }

    fn extract_google_docs_url(&self, url: &str) -> String {
        // Handle Google Docs viewer URLs
        // Example: https://docs.google.com/gview?url=...
        if url.contains("docs.google.com/gview") {
            if let Some(start) = url.find("url=") {
                let query_part = &url[start + 4..];
                if let Some(end) = query_part.find('&') {
                    return urlencoding::decode(&query_part[..end])
                        .unwrap_or_default()
                        .to_string();
                } else {
                    return urlencoding::decode(query_part)
                        .unwrap_or_default()
                        .to_string();
                }
            }
        }

        url.to_string()
    }
}

impl Default for PdfDownloader {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_google_docs_url_extraction() {
        let downloader = PdfDownloader::new();

        let google_url = "https://docs.google.com/gview?url=https%3A%2F%2Fexample.com%2Fdoc.pdf";
        let extracted = downloader.extract_google_docs_url(google_url);
        assert!(extracted.contains("example.com"));

        let normal_url = "https://example.com/doc.pdf";
        let unchanged = downloader.extract_google_docs_url(normal_url);
        assert_eq!(unchanged, normal_url);
    }

    #[test]
    fn test_invalid_url() {
        let downloader = PdfDownloader::new();
        let result = downloader.download("");
        assert!(result.is_err());
    }
}
