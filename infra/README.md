# engagic-core: Rust PDF Processing Extensions

PyO3-based Python bindings for high-performance PDF extraction and queue processing.

## Build Requirements

### System Dependencies
- **Rust toolchain** (cargo, rustc) - Install via rustup
- **poppler-glib** - PDF rendering library (C library)
- **pkg-config** - For finding system libraries

### Installation

**On VPS (automated):**
```bash
# The deploy script handles this automatically
./scripts/deploy.sh setup
```

**Manual setup:**
```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install poppler (Debian/Ubuntu)
sudo apt-get install libpoppler-glib-dev pkg-config

# Or on macOS
brew install poppler pkg-config
```

### Building

**With uv (recommended):**
```bash
# From project root - builds Rust extension automatically
uv sync
```

**Manual build (development):**
```bash
cd infra
maturin develop --release
```

## How uv sync Works

1. Root `pyproject.toml` declares `engagic-core` as editable path dependency
2. uv reads `infra/pyproject.toml` and sees `build-backend = "maturin"`
3. maturin compiles Rust code to Python extension module
4. Extension installed as `engagic_core` in venv

## Exported Components

```python
from engagic_core import PdfExtractor

# PDF text extraction
extractor = PdfExtractor()
result = extractor.extract_from_url("https://example.com/agenda.pdf")
# Returns: {"success": bool, "text": str, "page_count": int, ...}
```

## Architecture

- **lib.rs** - PyO3 module definition
- **pdf/extractor.rs** - Poppler-based PDF extraction (alternative to PyPDF2)
- **conductor.rs** - Async queue processor (planned replacement for background_processor.py)
- **database.rs** - SQLite async operations
- **rate_limiter.rs** - Request throttling

## Performance Targets

- **5x faster** PDF extraction vs PyPDF2 (benchmark pending)
- **True concurrency** for queue processing (Python GIL bypass)
- **Lower memory** for large PDF batches
