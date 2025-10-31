#!/bin/bash
# engagic deployment script - handles both API and daemon
set -e

APP_DIR="/root/engagic"
VENV_DIR="/root/engagic/.venv"
API_SERVICE="engagic-api"
DAEMON_SERVICE="engagic-daemon"
API_SERVICE_FILE="/etc/systemd/system/${API_SERVICE}.service"
DAEMON_SERVICE_FILE="/etc/systemd/system/${DAEMON_SERVICE}.service"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

info() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')] $1${NC}"
}

check_uv() {
    if ! command -v uv &> /dev/null; then
        log "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
        source ~/.bashrc
    fi
}

setup_env() {
    log "Setting up Python environment with uv..."
    check_uv

    cd "$APP_DIR"

    # Create venv with uv if doesn't exist
    if [ ! -d "$VENV_DIR" ]; then
        uv venv "$VENV_DIR"
        log "Created virtual environment with uv"
    fi

    # Install dependencies with uv
    source "$VENV_DIR/bin/activate"
    uv sync
    log "Dependencies installed"
}

create_api_service() {
    log "Creating systemd service file for API..."

    cat > "$API_SERVICE_FILE" << EOF
[Unit]
Description=Engagic API Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP_DIR
ExecStart=$VENV_DIR/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Environment
Environment=PYTHONPATH=$APP_DIR
EnvironmentFile=-$APP_DIR/.env
EnvironmentFile=-/root/.llm_secrets

# Resource limits
LimitNOFILE=65536

# Security
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    log "API systemd service file created"
}

create_daemon_service() {
    log "Creating systemd service file for daemon..."

    cat > "$DAEMON_SERVICE_FILE" << EOF
[Unit]
Description=Engagic Background Processing Daemon
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=-/root/.llm_secrets
ExecStart=$VENV_DIR/bin/uv run engagic-daemon --daemon
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    log "Daemon systemd service file created"
}

# API Management
start_api() {
    if [ ! -f "$API_SERVICE_FILE" ]; then
        create_api_service
    fi

    log "Starting API service..."
    systemctl enable "$API_SERVICE"

    if systemctl is-active --quiet "$API_SERVICE"; then
        warn "API already running, restarting..."
        systemctl restart "$API_SERVICE"
    else
        systemctl start "$API_SERVICE"
    fi

    sleep 2
    if systemctl is-active --quiet "$API_SERVICE"; then
        log "API started successfully"
        log "API logs: journalctl -u $API_SERVICE -f"
    else
        error "Failed to start API"
    fi
}

stop_api() {
    if systemctl is-active --quiet "$API_SERVICE"; then
        log "Stopping API..."
        systemctl stop "$API_SERVICE"
        log "API stopped"
    else
        warn "API not running"
    fi
}

restart_api() {
    log "Restarting API..."
    systemctl restart "$API_SERVICE"
    sleep 2
    if systemctl is-active --quiet "$API_SERVICE"; then
        log "API restarted successfully"
    else
        error "Failed to restart API"
    fi
}

# Daemon Management
start_daemon() {
    if [ ! -f "$DAEMON_SERVICE_FILE" ]; then
        create_daemon_service
    fi

    log "Starting background processor daemon..."
    systemctl enable "$DAEMON_SERVICE"

    if systemctl is-active --quiet "$DAEMON_SERVICE"; then
        warn "Daemon already running, restarting..."
        systemctl restart "$DAEMON_SERVICE"
    else
        systemctl start "$DAEMON_SERVICE"
    fi

    sleep 2
    if systemctl is-active --quiet "$DAEMON_SERVICE"; then
        log "Daemon started successfully"
        log "Daemon logs: journalctl -u $DAEMON_SERVICE -f"
    else
        error "Failed to start daemon"
    fi
}

stop_daemon() {
    log "Stopping daemon..."

    # Disable first to prevent auto-restart
    systemctl disable "$DAEMON_SERVICE" 2>/dev/null || true

    if systemctl is-active --quiet "$DAEMON_SERVICE"; then
        # Use timeout to prevent hanging on graceful shutdown
        # Try stop first (proper way), but with 5 second timeout
        log "Stopping daemon (5s timeout)..."
        timeout 5 systemctl stop "$DAEMON_SERVICE" 2>/dev/null || {
            # If timeout or stop fails, force kill
            warn "Stop timed out, sending SIGKILL..."
            systemctl kill --signal=SIGKILL "$DAEMON_SERVICE"
            sleep 2
        }
    fi

    # Kill any orphaned processes
    if pgrep -f "engagic-daemon" > /dev/null; then
        warn "Found orphaned daemon processes, killing..."
        pkill -9 -f "engagic-daemon"
        sleep 1
    fi

    # Final verification
    if systemctl is-active --quiet "$DAEMON_SERVICE" || pgrep -f "engagic-daemon" > /dev/null; then
        error "Failed to stop daemon"
    else
        log "Daemon stopped and disabled"
    fi
}

restart_daemon() {
    log "Restarting daemon..."

    # Clean stop first
    stop_daemon

    # Then start
    start_daemon
}

# Combined operations
start_all() {
    info "Starting all services..."
    start_api
    start_daemon
    info "All services started"
}

stop_all() {
    info "Stopping all services..."
    stop_api
    stop_daemon
    info "All services stopped"
}

restart_all() {
    info "Restarting all services..."
    restart_api
    restart_daemon
    info "All services restarted"
}

status_all() {
    echo -e "${BLUE}=== Engagic Status ===${NC}"
    echo ""

    # API status
    echo -e "${BLUE}API Status:${NC}"
    if systemctl is-active --quiet "$API_SERVICE"; then
        echo -e "${GREEN}  Running${NC}"
        echo "  Logs: journalctl -u $API_SERVICE -f"
        echo "  Test: curl http://localhost:8000/"
        systemctl status "$API_SERVICE" --no-pager | grep -E "Active:|Main PID:" | sed 's/^/  /'
    else
        echo -e "${YELLOW}  Not running${NC}"
    fi

    echo ""

    # Daemon status
    echo -e "${BLUE}Background Processor Status:${NC}"
    if systemctl is-active --quiet "$DAEMON_SERVICE"; then
        echo -e "${GREEN}  Running${NC}"
        echo "  Logs: journalctl -u $DAEMON_SERVICE -f"
        systemctl status "$DAEMON_SERVICE" --no-pager | grep -E "Active:|Main PID:" | sed 's/^/  /'
    else
        echo -e "${YELLOW}  Not running${NC}"
    fi

    echo ""

    # Database stats - only if API is running
    if systemctl is-active --quiet "$API_SERVICE"; then
        echo -e "${BLUE}Database Stats:${NC}"
        curl -s "http://localhost:8000/api/stats" | python3 -m json.tool 2>/dev/null | head -10 | sed 's/^/  /' || echo "  Unable to fetch stats"
    fi
}

test_services() {
    log "Testing API endpoints..."

    if ! command -v curl &> /dev/null; then
        error "curl is required for testing"
    fi

    # Check systemd status
    if ! systemctl is-active --quiet "$API_SERVICE"; then
        warn "API not running, skipping tests"
        return
    fi
    
    # Test root endpoint
    if curl -s "http://localhost:8000/" | grep -q "engagic API"; then
        log "✓ Root endpoint"
    else
        warn "✗ Root endpoint"
    fi
    
    # Test health endpoint
    if curl -s "http://localhost:8000/api/health" | grep -q "healthy\|status"; then
        log "✓ Health endpoint"
    else
        warn "✗ Health endpoint"
    fi
    
    # Test stats endpoint
    if curl -s "http://localhost:8000/api/stats" | grep -q "cities\|meetings"; then
        log "✓ Stats endpoint"
    else
        warn "✗ Stats endpoint"
    fi
    
    # Test search endpoint
    if curl -s -X POST "http://localhost:8000/api/search" \
        -H "Content-Type: application/json" \
        -d '{"query":"94301"}' | grep -q "success\|message"; then
        log "✓ Search endpoint"
    else
        warn "✗ Search endpoint"
    fi
    
    # Check daemon
    if systemctl is-active --quiet "$DAEMON_SERVICE"; then
        log "✓ Background processor"
    else
        warn "✗ Background processor"
    fi
    
    log "Service tests complete"
}

quick_update() {
    log "Quick update..."
    cd "$APP_DIR"
    git pull
    source "$VENV_DIR/bin/activate"
    uv sync
    restart_all
    log "Update complete!"
}

sync_deps() {
    log "Syncing dependencies..."
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    uv sync
    log "Dependencies synced!"
}

deploy_full() {
    info "Full deployment starting..."
    check_uv
    setup_env
    restart_all
    sleep 2
    test_services
    status_all
    info "Deployment complete!"
}

# Daemon-specific commands
daemon_status() {
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    uv run engagic-daemon --status
}

sync_city() {
    if [ -z "$1" ]; then
        error "City banana required (e.g., paloaltoCA)"
    fi

    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    # Source API keys if available
    [ -f ~/.llm_secrets ] && source ~/.llm_secrets
    uv run engagic-conductor --sync-city "$1"
}

sync_and_process_city() {
    if [ -z "$1" ]; then
        error "City banana required (e.g., paloaltoCA)"
    fi

    log "Syncing and processing $1..."
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    # Source API keys if available
    [ -f ~/.llm_secrets ] && source ~/.llm_secrets
    uv run engagic-conductor --sync-and-process-city "$1"
}

process_unprocessed() {
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    # Source API keys if available
    [ -f ~/.llm_secrets ] && source ~/.llm_secrets
    uv run engagic-conductor --full-sync
}

show_help() {
    echo "Engagic Deployment Script"
    echo ""
    echo "Usage: $0 [command] [args]"
    echo ""
    echo "Service Management:"
    echo "  start [api|daemon|all]    - Start services (default: all)"
    echo "  stop [api|daemon|all]     - Stop services (default: all)"
    echo "  restart [api|daemon|all]  - Restart services (default: all)"
    echo "  status                    - Show status of all services"
    echo ""
    echo "Deployment:"
    echo "  setup                     - Install dependencies"
    echo "  update                    - Quick update (git pull + restart)"
    echo "  deploy                    - Full deployment"
    echo "  test                      - Test all services"
    echo "  sync                      - Sync dependencies"
    echo ""
    echo "API Commands:"
    echo "  logs-api                  - Show API logs"
    echo ""
    echo "Background Processor Commands:"
    echo "  logs-daemon               - Show daemon logs"
    echo "  daemon-status             - Show processing status"
    echo "  sync-city CITY_BANANA     - Force sync specific city (enqueues only)"
    echo "  sync-and-process CITY     - Sync city and immediately process all meetings"
    echo "  process-unprocessed       - Process all unprocessed meetings"
    echo ""
    echo "Examples:"
    echo "  $0 deploy                      # First time setup"
    echo "  $0 update                      # Quick update from git"
    echo "  $0 sync-city paloaltoCA        # Sync Palo Alto (just fetch + enqueue)"
    echo "  $0 sync-and-process paloaltoCA # Sync + process immediately (test item detection)"
    echo "  $0 status                      # Check everything"
}

# Main command handling
case "${1:-help}" in
    # Setup
    setup)     setup_env ;;
    
    # Start commands
    start)
        case "${2:-all}" in
            api)    start_api ;;
            daemon) start_daemon ;;
            all|*)  start_all ;;
        esac
        ;;
    
    # Stop commands
    stop)
        case "${2:-all}" in
            api)    stop_api ;;
            daemon) stop_daemon ;;
            all|*)  stop_all ;;
        esac
        ;;
    
    # Restart commands
    restart)
        case "${2:-all}" in
            api)    restart_api ;;
            daemon) restart_daemon ;;
            all|*)  restart_all ;;
        esac
        ;;
    
    # Status and logs
    status)         status_all ;;
    logs-api)       journalctl -u engagic-api -f ;;
    logs-daemon)    journalctl -u "$DAEMON_SERVICE" -f ;;
    
    # Testing
    test)           test_services ;;
    
    # Deployment
    update)         quick_update ;;
    deploy)         deploy_full ;;
    sync)           sync_deps ;;

    # Daemon specific
    daemon-status)  daemon_status ;;
    sync-city)      sync_city "$2" ;;
    sync-and-process) sync_and_process_city "$2" ;;
    process-unprocessed) process_unprocessed ;;

    # Help
    help|*)         show_help ;;
esac