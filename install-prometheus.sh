#!/bin/bash
# Install Prometheus as a native binary (NO DOCKER)
#
# Usage:
#   chmod +x install-prometheus.sh
#   ./install-prometheus.sh

set -e

echo "Installing Prometheus (native binary, no Docker)..."

# Configuration
PROMETHEUS_VERSION="2.48.0"
PROMETHEUS_URL="https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz"
INSTALL_DIR="/root/engagic"
DATA_DIR="/root/engagic/data/prometheus"

# Download Prometheus
cd "$INSTALL_DIR"

if [ ! -d "prometheus" ]; then
    echo "Downloading Prometheus ${PROMETHEUS_VERSION}..."
    wget "$PROMETHEUS_URL" -O prometheus.tar.gz

    echo "Extracting..."
    tar xzf prometheus.tar.gz
    mv "prometheus-${PROMETHEUS_VERSION}.linux-amd64" prometheus
    rm prometheus.tar.gz

    echo "Prometheus binary installed at: ${INSTALL_DIR}/prometheus"
else
    echo "Prometheus already installed, skipping download"
fi

# Create data directory
mkdir -p "$DATA_DIR"
echo "Data directory created at: $DATA_DIR"

# Install systemd service
echo "Installing systemd service..."
cp prometheus.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable prometheus

echo ""
echo "Prometheus installation complete!"
echo ""
echo "To start Prometheus:"
echo "  sudo systemctl start prometheus"
echo ""
echo "To check status:"
echo "  sudo systemctl status prometheus"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u prometheus -f"
echo ""
echo "Access Prometheus UI:"
echo "  http://localhost:9090"
echo ""
echo "Verify metrics scraping:"
echo "  curl http://localhost:9090/api/v1/targets"
echo ""
