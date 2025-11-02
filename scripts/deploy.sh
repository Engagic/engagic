#!/bin/bash
# engagic deployment script - API management and explicit data operations
# NO DAEMON - explicit control only via sync-cities, process-cities commands
set -e

APP_DIR="/root/engagic"
VENV_DIR="/root/engagic/.venv"
API_SERVICE="engagic-api"
API_SERVICE_FILE="/etc/systemd/system/${API_SERVICE}.service"

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

# Background Process Management (Manual Commands Only)
kill_background_processes() {
    log "Stopping all background conductor/daemon processes..."

    local was_running=false

    # Check for ANY running processes
    if pgrep -f "engagic-daemon|pipeline.conductor|engagic-conductor" > /dev/null; then
        was_running=true
        warn "Found running background processes:"
        pgrep -fa "engagic-daemon|pipeline.conductor|engagic-conductor" | sed 's/^/  /'
    fi

    # Kill all background processes
    if pgrep -f "engagic-daemon|pipeline.conductor|engagic-conductor" > /dev/null; then
        warn "Killing background processes..."

        # Send SIGTERM first (graceful)
        pkill -TERM -f "engagic-daemon|pipeline.conductor|engagic-conductor" 2>/dev/null || true
        sleep 3

        # Check if still running
        if pgrep -f "engagic-daemon|pipeline.conductor|engagic-conductor" > /dev/null; then
            warn "Processes still running, sending SIGKILL..."
            pkill -KILL -f "engagic-daemon|pipeline.conductor|engagic-conductor" 2>/dev/null || true
            sleep 1
        fi
    fi

    # Final verification
    if pgrep -f "engagic-daemon|pipeline.conductor|engagic-conductor" > /dev/null; then
        error "Failed to stop background processes:"
        pgrep -fa "engagic-daemon|pipeline.conductor|engagic-conductor" | sed 's/^/  /'
        echo ""
        warn "Try: pkill -9 -f 'engagic-daemon|pipeline.conductor|engagic-conductor'"
    else
        if [ "$was_running" = true ]; then
            log "Stopped all background processes"
        else
            info "No background processes running"
        fi
    fi
}

# Combined operations
start_all() {
    start_api
}

stop_all() {
    stop_api
    kill_background_processes
}

restart_all() {
    restart_api
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

    # Background processes (manual)
    echo -e "${BLUE}Background Processes:${NC}"
    if pgrep -f "engagic-daemon|pipeline.conductor|engagic-conductor" > /dev/null; then
        echo -e "${YELLOW}  Running (manual):${NC}"
        pgrep -fa "engagic-daemon|pipeline.conductor|engagic-conductor" | sed 's/^/    /'
    else
        echo -e "${GREEN}  None${NC}"
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
    # Source and export API keys if available
    if [ -f ~/.llm_secrets ]; then
        set -a  # Auto-export all variables
        source ~/.llm_secrets
        set +a
    fi
    uv run engagic-conductor --sync-city "$1"
}

sync_and_process_city() {
    if [ -z "$1" ]; then
        error "City banana required (e.g., paloaltoCA)"
    fi

    log "Syncing and processing $1..."
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    # Source and export API keys if available
    if [ -f ~/.llm_secrets ]; then
        set -a  # Auto-export all variables
        source ~/.llm_secrets
        set +a
    fi
    uv run engagic-conductor --sync-and-process-city "$1"
}

sync_cities() {
    if [ -z "$1" ]; then
        error "Cities required (comma-separated bananas or @file path)"
    fi

    log "Syncing cities: $1"
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    # Source and export API keys if available
    if [ -f ~/.llm_secrets ]; then
        set -a  # Auto-export all variables
        source ~/.llm_secrets
        set +a
    fi
    uv run engagic-conductor --sync-cities "$1"
}

process_cities() {
    if [ -z "$1" ]; then
        error "Cities required (comma-separated bananas or @file path)"
    fi

    log "Processing queued jobs for cities: $1"
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    # Source and export API keys if available
    if [ -f ~/.llm_secrets ]; then
        set -a  # Auto-export all variables
        source ~/.llm_secrets
        set +a
    fi
    uv run engagic-conductor --process-cities "$1"
}

sync_and_process_cities() {
    if [ -z "$1" ]; then
        error "Cities required (comma-separated bananas or @file path)"
    fi

    log "Syncing and processing cities: $1"
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    # Source and export API keys if available
    if [ -f ~/.llm_secrets ]; then
        set -a  # Auto-export all variables
        source ~/.llm_secrets
        set +a
    fi
    uv run engagic-conductor --sync-and-process-cities "$1"
}

process_unprocessed() {
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    # Source and export API keys if available
    if [ -f ~/.llm_secrets ]; then
        set -a  # Auto-export all variables
        source ~/.llm_secrets
        set +a
    fi
    uv run engagic-conductor --full-sync
}

preview_queue() {
    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"
    uv run engagic-conductor --preview-queue "${1:-all}"
}

extract_text() {
    if [ -z "$1" ]; then
        error "Meeting ID required"
    fi

    cd "$APP_DIR"
    source "$VENV_DIR/bin/activate"

    # Build command
    CMD="uv run engagic-conductor --extract-text $1"

    # Add output file if provided
    if [ -n "$2" ]; then
        CMD="$CMD --output-file $2"
        log "Extracting text from meeting $1 to $2..."
    else
        log "Extracting text preview from meeting $1..."
    fi

    eval $CMD
}

show_help() {
    echo "Engagic Deployment Script"
    echo ""
    echo "Usage: $0 [command] [args]"
    echo ""
    echo "Service Management:"
    echo "  start                     - Start API service"
    echo "  stop                      - Stop API and kill background processes"
    echo "  restart                   - Restart API service"
    echo "  status                    - Show system status"
    echo "  logs-api                  - Show API logs"
    echo ""
    echo "Deployment:"
    echo "  setup                     - Install dependencies"
    echo "  update                    - Quick update (git pull + restart)"
    echo "  deploy                    - Full deployment"
    echo "  test                      - Test API endpoints"
    echo "  sync                      - Sync dependencies"
    echo ""
    echo "Data Operations (Explicit Control Only):"
    echo ""
    echo "  Single City:"
    echo "    sync-city CITY_BANANA          - Fetch meetings (enqueue for processing)"
    echo "    sync-and-process CITY          - Fetch + process immediately"
    echo ""
    echo "  Multiple Cities:"
    echo "    sync-cities CITIES             - Fetch multiple (comma-separated or @file)"
    echo "    process-cities CITIES          - Process queued jobs for multiple cities"
    echo "    sync-and-process-cities CITIES - Fetch + process multiple cities"
    echo ""
    echo "  Batch Operations:"
    echo "    process-unprocessed            - Process all unprocessed meetings in queue"
    echo ""
    echo "  Preview & Inspection:"
    echo "    preview-queue [CITY]           - Show queued jobs (no processing)"
    echo "    extract-text MEETING_ID [FILE] - Extract PDF text (no LLM, manual review)"
    echo "    kill-background                - Kill any running background processes"
    echo ""
    echo "Examples:"
    echo ""
    echo "  # System management"
    echo "  $0 deploy                                  # First time setup"
    echo "  $0 status                                  # Check what's running"
    echo "  $0 kill-background                         # Stop any background jobs"
    echo ""
    echo "  # Single city workflow"
    echo "  $0 sync-city paloaltoCA                    # 1. Fetch meetings"
    echo "  $0 preview-queue paloaltoCA                # 2. Preview queue"
    echo "  $0 extract-text MEETING_ID /tmp/check.txt  # 3. Review extraction quality"
    echo "  $0 sync-and-process paloaltoCA             # 4. Process (costs API credits)"
    echo ""
    echo "  # Regional workflow (RECOMMENDED)"
    echo "  $0 sync-cities @regions/bay-area.txt       # 1. Fetch region (free)"
    echo "  $0 preview-queue                           # 2. Check queue"
    echo "  $0 process-cities @regions/bay-area.txt    # 3. Process (costs ~\$0.50)"
    echo ""
    echo "  # Quick test"
    echo "  $0 sync-and-process-cities @regions/test-small.txt  # 2 cities (~\$0.02)"
}

# Main command handling
case "${1:-help}" in
    # Setup
    setup)     setup_env ;;
    
    # Service commands
    start)          start_api ;;
    stop)           stop_all ;;
    restart)        restart_api ;;
    kill-background) kill_background_processes ;;
    
    # Status and logs
    status)         status_all ;;
    logs-api)
        if systemctl is-active --quiet "$API_SERVICE"; then
            journalctl -u engagic-api -f
        else
            warn "API not running via systemd"
            if [ -f "$APP_DIR/logs/api.log" ]; then
                tail -f "$APP_DIR/logs/api.log"
            else
                error "No API logs found"
            fi
        fi
        ;;
    
    # Testing
    test)           test_services ;;
    
    # Deployment
    update)         quick_update ;;
    deploy)         deploy_full ;;
    sync)           sync_deps ;;

    # Data operations - single city
    sync-city)           sync_city "$2" ;;
    sync-and-process)    sync_and_process_city "$2" ;;

    # Data operations - multiple cities
    sync-cities)         sync_cities "$2" ;;
    process-cities)      process_cities "$2" ;;
    sync-and-process-cities) sync_and_process_cities "$2" ;;

    # Batch operations
    process-unprocessed) process_unprocessed ;;

    # Preview and inspection
    preview-queue)       preview_queue "$2" ;;
    extract-text)        extract_text "$2" "$3" ;;

    # Help
    help|*)              show_help ;;
esac