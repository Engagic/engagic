#!/bin/bash
# Fast iteration script for Rust development
# Usage:
#   ./scripts/setup_rust.sh         # Fast debug build (use during development)
#   ./scripts/setup_rust.sh release # Optimized release build (for testing perf)
#   ./scripts/setup_rust.sh watch   # Auto-rebuild on file changes

set -e

MODE="${1:-debug}"

case "$MODE" in
    release)
        echo "Building Rust extension (RELEASE mode - slow build, fast runtime)..."
        cd infra
        # Simple: maturin develop handles everything
        maturin develop --release --uv
        ;;
    watch)
        echo "Watching Rust files for changes..."
        echo "Press Ctrl+C to stop"
        cd infra
        cargo watch -x "run --bin maturin -- develop" || {
            echo ""
            echo "cargo-watch not installed. Installing..."
            cargo install cargo-watch
            cargo watch -x "run --bin maturin -- develop"
        }
        ;;
    debug|*)
        echo "Building Rust extension (DEBUG mode - fast build, slower runtime)..."
        cd infra
        # Simple: maturin develop handles everything
        maturin develop --uv
        ;;
esac

cd ..
echo ""
echo "Rust extension installed in active venv"
echo ""
echo "Test with:"
echo "  python -c 'from engagic_core import PdfExtractor; print(PdfExtractor())'"
echo "  uv run python test_rust_integration.py"
