#!/bin/bash
# engagic deployment script - handles both API and daemon
set -e

APP_DIR="/root/engagic/app"
VENV_DIR="/root/engagic/.venv"
API_PID_FILE="/tmp/engagic-api.pid"
DAEMON_SERVICE="engagic-daemon"
SERVICE_FILE="/etc/systemd/system/${DAEMON_SERVICE}.service"

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

check_api_process() {
    if [ -f "$API_PID_FILE" ]; then
        local pid=$(cat "$API_PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "$pid"
        else
            rm -f "$API_PID_FILE"
            echo ""
        fi
    else
        echo ""
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
    uv pip install -r requirements.txt
}

create_daemon_service() {
    log "Creating systemd service file for daemon..."
    
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Engagic Background Processing Daemon
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV_DIR/bin/python daemon.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    log "Systemd service file created"
}

# API Management
start_api() {
    local existing_pid=$(check_api_process)
    if [ -n "$existing_pid" ]; then
        warn "API already running (PID: $existing_pid)"
        return
    fi
    
    log "Starting engagic API..."
    source "$VENV_DIR/bin/activate"
    cd "$APP_DIR"
    
    # Check if using uvicorn in requirements
    if grep -q "uvicorn" requirements.txt; then
        nohup uvicorn app:app --host 0.0.0.0 --port 8000 > /tmp/engagic-api.log 2>&1 &
    else
        nohup python app.py > /tmp/engagic-api.log 2>&1 &
    fi
    
    local pid=$!
    echo "$pid" > "$API_PID_FILE"
    
    sleep 2
    if ps -p "$pid" > /dev/null 2>&1; then
        log "API started successfully (PID: $pid)"
        log "API logs: tail -f /tmp/engagic-api.log"
    else
        error "Failed to start API"
    fi
}

stop_api() {
    local existing_pid=$(check_api_process)
    if [ -n "$existing_pid" ]; then
        log "Stopping API (PID: $existing_pid)..."
        kill "$existing_pid"
        rm -f "$API_PID_FILE"
        log "API stopped"
    else
        warn "API not running"
    fi
}

restart_api() {
    log "Restarting API..."
    stop_api
    sleep 1
    start_api
}

# Daemon Management
start_daemon() {
    if [ ! -f "$SERVICE_FILE" ]; then
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
    if systemctl is-active --quiet "$DAEMON_SERVICE"; then
        log "Stopping daemon..."
        systemctl stop "$DAEMON_SERVICE"
        log "Daemon stopped"
    else
        warn "Daemon not running"
    fi
}

restart_daemon() {
    log "Restarting daemon..."
    stop_daemon
    sleep 1
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
    local api_pid=$(check_api_process)
    if [ -n "$api_pid" ]; then
        echo -e "${GREEN}  Running (PID: $api_pid)${NC}"
        echo "  Logs: tail -f /tmp/engagic-api.log"
        echo "  Test: curl http://localhost:8000/"
        
        if command -v ps &> /dev/null; then
            local mem=$(ps -p "$api_pid" -o %mem | tail -1)
            echo "  Memory usage: ${mem}%"
        fi
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
    
    # Database stats
    if [ -n "$api_pid" ]; then
        echo -e "${BLUE}Database Stats:${NC}"
        curl -s "http://localhost:8000/api/stats" | python3 -m json.tool 2>/dev/null | head -10 | sed 's/^/  /' || echo "  Unable to fetch stats"
    fi
}

test_services() {
    log "Testing API endpoints..."
    
    if ! command -v curl &> /dev/null; then
        error "curl is required for testing"
    fi
    
    local api_pid=$(check_api_process)
    if [ -z "$api_pid" ]; then
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
    uv pip install -r requirements.txt
    restart_all
    log "Update complete!"
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
    python daemon.py --status
}

sync_city() {
    if [ -z "$1" ]; then
        error "City banana required (e.g., paloaltoCA)"
    fi
    
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    python daemon.py --sync-city "$1"
}

process_unprocessed() {
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    python background_processor.py --process-all-unprocessed
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
    echo ""
    echo "API Commands:"
    echo "  logs-api                  - Show API logs"
    echo ""
    echo "Background Processor Commands:"
    echo "  logs-daemon               - Show daemon logs"
    echo "  daemon-status             - Show processing status"
    echo "  sync-city CITY_BANANA     - Force sync specific city"
    echo "  process-unprocessed       - Process all unprocessed meetings"
    echo ""
    echo "Examples:"
    echo "  $0 deploy                 # First time setup"
    echo "  $0 update                 # Quick update from git"
    echo "  $0 sync-city paloaltoCA   # Sync Palo Alto"
    echo "  $0 status                 # Check everything"
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
    logs-api)       tail -f /tmp/engagic-api.log ;;
    logs-daemon)    journalctl -u "$DAEMON_SERVICE" -f ;;
    
    # Testing
    test)           test_services ;;
    
    # Deployment
    update)         quick_update ;;
    deploy)         deploy_full ;;
    
    # Daemon specific
    daemon-status)  daemon_status ;;
    sync-city)      sync_city "$2" ;;
    process-unprocessed) process_unprocessed ;;
    
    # Help
    help|*)         show_help ;;
esac