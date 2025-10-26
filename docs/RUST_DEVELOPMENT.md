# Rust Development Workflow

## Two Different Workflows

### 1. Local Development (Fast Iteration)
When actively coding Rust modules, use the fast rebuild script:

```bash
# Fast debug build (2-5 seconds)
./scripts/setup_rust.sh

# Auto-rebuild on save (recommended for active development)
./scripts/setup_rust.sh watch

# Release build for performance testing
./scripts/setup_rust.sh release
```

**Debug vs Release:**
- **Debug** (default): 2-5 second builds, adequate runtime performance
- **Release**: 30-60 second builds, 5x faster runtime (use for benchmarks)

### 2. VPS Deployment (Production)
When deploying to your VPS, use the deploy script:

```bash
# On VPS - handles everything including Rust build
./scripts/deploy.sh setup    # First time
./scripts/deploy.sh update   # After git pull
```

This uses `uv sync` which triggers maturin automatically.

## Active Development Loop

**Recommended workflow when editing Rust code:**

```bash
# Terminal 1: Watch mode (auto-rebuilds on save)
./scripts/setup_rust.sh watch

# Terminal 2: Run your tests
uv run python test_rust_integration.py

# Edit infra/src/*.rs files
# Save → auto rebuild → rerun tests
```

## Build Times

- **Initial build**: ~60s (downloads all Rust dependencies)
- **Debug rebuild**: 2-5s (only changed files)
- **Release rebuild**: 30-60s (full optimization)
- **uv sync rebuild**: Same as above + Python packaging overhead

## Common Tasks

### Test Python → Rust integration
```bash
python -c "from engagic_core import PdfExtractor; print(PdfExtractor())"
```

### Check Rust compilation errors (no Python binding)
```bash
cd infra
cargo check    # Fast syntax/type check
cargo build    # Full build
cargo test     # Run Rust tests
```

### Benchmark performance
```bash
./scripts/setup_rust.sh release  # Must use release mode
uv run python benchmark_pdf_extraction.py
```

## Don't Mix Workflows

**WRONG:**
```bash
# Don't use uv sync for active development
uv sync  # Too slow, rebuilds everything
```

**RIGHT:**
```bash
# Use setup_rust.sh for development
./scripts/setup_rust.sh        # Fast iteration
./scripts/setup_rust.sh watch  # Even faster
```

Only use `uv sync` when:
- Setting up project fresh
- Deploying to VPS
- Adding new Python dependencies
- Someone else updated dependencies

## Troubleshooting

**Error: "cannot find -lpoppler-glib"**
```bash
# macOS
brew install poppler pkg-config

# Linux
sudo apt-get install libpoppler-glib-dev pkg-config
```

**Error: "rustc not found"**
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
```

**Rebuild not picking up changes?**
```bash
# Nuclear option: clean build
cd infra
cargo clean
cd ..
./scripts/setup_rust.sh
```
