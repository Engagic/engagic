#!/bin/bash
# Deployment script for Engagic Background Processor

set -e

echo "=== Engagic Background Processor Deployment ==="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root"
    exit 1
fi

# Set up paths
SERVICE_FILE="/etc/systemd/system/engagic-daemon.service"
LOG_FILE="/root/engagic/app/daemon.log"

# Create log file if it doesn't exist
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

# Reload systemd
echo "Reloading systemd..."
systemctl daemon-reload

# Enable service to start on boot
echo "Enabling service..."
systemctl enable engagic-daemon

# Check if service is already running
if systemctl is-active --quiet engagic-daemon; then
    echo "Service is already running. Restarting..."
    systemctl restart engagic-daemon
else
    echo "Starting service..."
    systemctl start engagic-daemon
fi

# Check service status
echo "Service status:"
systemctl status engagic-daemon --no-pager

# Show recent logs
echo ""
echo "Recent logs:"
journalctl -u engagic-daemon -n 20 --no-pager

echo ""
echo "=== Deployment Complete ==="
echo "Service: engagic-daemon"
echo "Status: systemctl status engagic-daemon"
echo "Logs: journalctl -u engagic-daemon -f"
echo "Manual control: python3 daemon.py --status"
