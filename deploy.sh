#!/bin/bash
# Engagic deployment and management script
#
# Usage: ./deploy.sh <command>

set -e

# Configuration
PROJECT_DIR="/opt/engagic"
API_SERVICE="engagic-api"
PROMETHEUS_SERVICE="prometheus"

# Source environment variables (optional - systemd service loads these directly)
if [ -f "$PROJECT_DIR/.env" ] && [ -r "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[$(date +%T)]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[$(date +%T)]${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date +%T)]${NC} $1"
}

# Command functions
cmd_help() {
    cat <<EOF
Engagic Deployment Script

Commands:
  help              Show this help message

  API Management:
  start-api         Start API server
  stop-api          Stop API server
  restart-api       Restart API server
  logs-api          Stream API logs
  status-api        Check API status

  Prometheus Management:
  install-prometheus    Install Prometheus binary and service
  start-prometheus      Start Prometheus service
  stop-prometheus       Stop Prometheus service
  restart-prometheus    Restart Prometheus service
  logs-prometheus       Stream Prometheus logs
  status-prometheus     Check Prometheus status

  Testing:
  test-emails       Send test emails to ibansadowski12@gmail.com

  Moderation:
  moderate          List pending deliberation comments
  moderate review   Interactive review (prompts for deliberation ID)

  Map/Coverage:
  map-import        Import Census TIGER boundaries (download + import + match)
  map-tiles         Generate PMTiles from city geometries
  map-status        Show geometry coverage status
  map-all           Full map pipeline (import + tiles + deploy)

  System:
  status            Show status of all services
  logs              Show all logs
  security          Show security posture (UFW, fail2ban, SSH, backups)
EOF
}

# API Commands
cmd_start_api() {
    log_info "Starting API server..."
    sudo systemctl start $API_SERVICE
    log_info "API server started"
}

cmd_stop_api() {
    log_info "Stopping API server..."
    sudo systemctl stop $API_SERVICE
    log_info "API server stopped"
}

cmd_restart_api() {
    log_info "Restarting API server..."
    sudo systemctl restart $API_SERVICE
    log_info "API server restarted"
}

cmd_logs_api() {
    log_info "Streaming API logs (Ctrl+C to exit)..."
    sudo journalctl -u $API_SERVICE -n 50 -f
}

cmd_status_api() {
    sudo systemctl status $API_SERVICE
}

# Prometheus Commands
cmd_install_prometheus() {
    log_info "Installing Prometheus..."
    cd $PROJECT_DIR
    chmod +x install-prometheus.sh
    ./install-prometheus.sh
    log_info "Prometheus installation complete"
}

cmd_start_prometheus() {
    log_info "Starting Prometheus..."
    sudo systemctl start $PROMETHEUS_SERVICE
    log_info "Prometheus started"
}

cmd_stop_prometheus() {
    log_info "Stopping Prometheus..."
    sudo systemctl stop $PROMETHEUS_SERVICE
    log_info "Prometheus stopped"
}

cmd_restart_prometheus() {
    log_info "Restarting Prometheus..."
    sudo systemctl restart $PROMETHEUS_SERVICE
    log_info "Prometheus restarted"
}

cmd_logs_prometheus() {
    log_info "Streaming Prometheus logs (Ctrl+C to exit)..."
    sudo journalctl -u $PROMETHEUS_SERVICE -f
}

cmd_status_prometheus() {
    sudo systemctl status $PROMETHEUS_SERVICE
}

# Testing Commands
cmd_test_emails() {
    log_info "Sending test emails to ibansadowski12@gmail.com..."
    cd $PROJECT_DIR
    uv run userland/scripts/test_emails.py ibansadowski12@gmail.com
}

# System Commands
cmd_status() {
    log_info "Service Status:"
    echo ""
    echo "API Server:"
    sudo systemctl status $API_SERVICE --no-pager | head -3
    echo ""
    echo "Prometheus:"
    sudo systemctl status $PROMETHEUS_SERVICE --no-pager | head -3
}

cmd_logs() {
    log_info "Streaming all logs (Ctrl+C to exit)..."
    sudo journalctl -u $API_SERVICE -u $PROMETHEUS_SERVICE -f
}

cmd_security() {
    log_info "Security Status:"
    echo ""
    echo "Firewall (UFW):"
    ufw status | head -5
    echo ""
    echo "Fail2ban:"
    echo "  Status: $(systemctl is-active fail2ban)"
    fail2ban-client status 2>/dev/null | grep "Jail list" || echo "  (could not query jails)"
    echo ""
    echo "SSH:"
    echo "  Password auth: $(grep -E '^PasswordAuthentication' /etc/ssh/sshd_config.d/*.conf 2>/dev/null || echo 'default (check main config)')"
    echo ""
    echo "Backups:"
    local latest_backup=$(ls -t /opt/engagic/data/backups/engagic_*.sql.gz 2>/dev/null | head -1)
    if [ -n "$latest_backup" ]; then
        echo "  Latest: $latest_backup"
        echo "  Size: $(du -h "$latest_backup" | cut -f1)"
    else
        echo "  No backups found (will run at 3 AM daily)"
    fi
    echo "  Total backup space: $(du -sh /opt/engagic/data/backups 2>/dev/null | cut -f1)"
}

# Map Commands
cmd_map_import() {
    log_info "Importing Census TIGER boundaries..."
    cd $PROJECT_DIR
    uv run python scripts/import_census_boundaries.py --all
    log_info "Census import complete"
}

cmd_map_tiles() {
    log_info "Generating PMTiles..."
    cd $PROJECT_DIR
    uv run python scripts/generate_tiles.py --all
    log_info "Tiles generated"
}

cmd_map_status() {
    cd $PROJECT_DIR
    uv run python scripts/import_census_boundaries.py --status
}

cmd_map_all() {
    log_info "Running full map pipeline..."
    cmd_map_import
    cmd_map_tiles
    log_info "Map pipeline complete"
}

# Main command router
main() {
    local cmd="${1:-help}"

    case "$cmd" in
        help|--help|-h)
            cmd_help
            ;;

        # API
        start-api)
            cmd_start_api
            ;;
        stop-api)
            cmd_stop_api
            ;;
        restart-api)
            cmd_restart_api
            ;;
        logs-api)
            cmd_logs_api
            ;;
        status-api)
            cmd_status_api
            ;;

        # Prometheus
        install-prometheus)
            cmd_install_prometheus
            ;;
        start-prometheus)
            cmd_start_prometheus
            ;;
        stop-prometheus)
            cmd_stop_prometheus
            ;;
        restart-prometheus)
            cmd_restart_prometheus
            ;;
        logs-prometheus)
            cmd_logs_prometheus
            ;;
        status-prometheus)
            cmd_status_prometheus
            ;;

        # Testing
        test-emails)
            cmd_test_emails
            ;;

        # Moderation
        moderate)
            if [ "$2" = "review" ]; then
                if [ -z "$3" ]; then
                    echo "Enter deliberation ID to review:"
                    read -r delib_id
                    python3 "$PROJECT_DIR/scripts/moderate.py" review "$delib_id"
                else
                    python3 "$PROJECT_DIR/scripts/moderate.py" review "$3"
                fi
            else
                python3 "$PROJECT_DIR/scripts/moderate.py" list
            fi
            ;;

        # Map
        map-import)
            cmd_map_import
            ;;
        map-tiles)
            cmd_map_tiles
            ;;
        map-status)
            cmd_map_status
            ;;
        map-all)
            cmd_map_all
            ;;

        # System
        status)
            cmd_status
            ;;
        logs)
            cmd_logs
            ;;
        security)
            cmd_security
            ;;

        *)
            log_error "Unknown command: $cmd"
            echo ""
            cmd_help
            exit 1
            ;;
    esac
}

main "$@"
