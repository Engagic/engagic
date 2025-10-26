use pyo3::prelude::*;
use tracing_subscriber;

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
    // Initialize tracing subscriber for logging (only once)
    use std::sync::Once;
    static INIT: Once = Once::new();
    INIT.call_once(|| {
        tracing_subscriber::fmt()
            .with_max_level(tracing::Level::DEBUG)
            .with_target(false)
            .with_thread_ids(false)
            .with_file(false)
            .with_line_number(false)
            .init();
    });

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
