use pyo3::prelude::*;

mod pdf;
mod conductor;
mod database;
mod rate_limiter;

// Re-export main types
pub use pdf::{PdfExtractor, PdfExtractionResult};
pub use conductor::Conductor;

// PyO3 module definition - exposes Rust functions to Python
#[pymodule]
fn engagic_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // PDF extraction
    m.add_class::<PdfExtractor>()?;

    // Conductor (queue processor, sync loop)
    m.add_class::<Conductor>()?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_imports() {
        // Ensure modules compile
    }
}
