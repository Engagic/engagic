#!/bin/bash
# VPS dependency setup for Rust + system libraries
set -e

echo "Setting up VPS dependencies for Engagic Rust components..."

# Install Rust if not present
if ! command -v cargo &> /dev/null; then
    echo "Installing Rust toolchain..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
    echo "Rust installed successfully"
else
    echo "Rust already installed ($(rustc --version))"
fi

# Detect package manager and install poppler
if command -v apt-get &> /dev/null; then
    echo "Installing poppler-glib (Debian/Ubuntu)..."
    sudo apt-get update
    sudo apt-get install -y libpoppler-glib-dev pkg-config
elif command -v yum &> /dev/null; then
    echo "Installing poppler-glib (RHEL/CentOS)..."
    sudo yum install -y poppler-glib-devel pkgconfig
elif command -v dnf &> /dev/null; then
    echo "Installing poppler-glib (Fedora)..."
    sudo dnf install -y poppler-glib-devel pkgconfig
else
    echo "WARNING: Could not detect package manager. Please install poppler-glib manually."
    exit 1
fi

echo "VPS dependencies ready for Rust build"
