#!/bin/bash
# engagic API deployment script (uv version)
set -e

APP_DIR="/root/engagic/app"
VENV_DIR="/root/engagic/.venv"
PID_FILE="/tmp/engagic.pid"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

check_uv() {
    if ! command -v uv &> /dev/null; then
        log "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
        source ~/.bashrc
    fi
}

check_process() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "$pid"
        else
            rm -f "$PID_FILE"
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
        uv venv "$VENV_DIR"  # Specify the full path
        log "Created virtual environment with uv"
    fi
    
    # Install dependencies with uv (much faster than pip)
    source "$VENV_DIR/bin/activate"  # Use the variable
    uv pip install -r requirements.txt
    log "Dependencies installed (lightning fast with uv)"
}


start_api() {
    local existing_pid=$(check_process)
    if [ -n "$existing_pid" ]; then
        warn "API already running (PID: $existing_pid)"
        return
    fi
    
    log "Starting engagic API..."
    source "$VENV_DIR/bin/activate"
    cd "$APP_DIR"
    
    # Check if using uvicorn in requirements
    if grep -q "uvicorn" requirements.txt; then
        nohup uvicorn app:app --host 0.0.0.0 --port 8000 > /tmp/engagic.log 2>&1 &
    else
        nohup python app.py > /tmp/engagic.log 2>&1 &
    fi
    
    local pid=$!
    echo "$pid" > "$PID_FILE"
    
    # Reduced sleep since uv is faster
    sleep 1
    if ps -p "$pid" > /dev/null 2>&1; then
        log "API started successfully (PID: $pid)"
        log "Logs: tail -f /tmp/engagic.log"
    else
        error "Failed to start API"
    fi
}

stop_api() {
    local existing_pid=$(check_process)
    if [ -n "$existing_pid" ]; then
        log "Stopping API (PID: $existing_pid)..."
        kill "$existing_pid"
        rm -f "$PID_FILE"
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

status_api() {
    local existing_pid=$(check_process)
    if [ -n "$existing_pid" ]; then
        echo -e "${GREEN}API is running (PID: $existing_pid)${NC}"
        echo "Logs: tail -f /tmp/engagic.log"
        echo "Test: curl http://localhost:8000/"
        
        # Check memory usage
        if command -v ps &> /dev/null; then
            local mem=$(ps -p "$existing_pid" -o %mem | tail -1)
            echo "Memory usage: ${mem}%"
        fi
    else
        echo -e "${YELLOW}API is not running${NC}"
    fi
}

logs_api() {
    if [ -f "/tmp/engagic.log" ]; then
        tail -f /tmp/engagic.log
    else
        error "No log file found"
    fi
}

test_api() {
    log "Testing API endpoints..."
    
    if ! command -v curl &> /dev/null; then
        error "curl is required for testing"
    fi
    
    # Test root endpoint

    
    # Test meetings endpoint
    if curl -s "http://localhost:8000/api/meetings" | grep -q "packet_url\|error"; then
        log "✓ Meetings endpoint responding"
    else
        warn "⚠ Meetings endpoint may have issues"
    fi
    
    # Test cache stats
    if curl -s "http://localhost:8000/api/cache/stats" | grep -q "total_meetings"; then
        log "✓ Cache stats working"
    else
        warn "⚠ Cache stats endpoint may have issues"
    fi
    
    log "API test complete"
}

quick_update() {
    log "Quick update with uv..."
    cd "$APP_DIR"
    git pull
    source "$VENV_DIR/bin/activate"
    uv pip install -r requirements.txt
    restart_api
    log "Update complete!"
}

deploy_full() {
    log "Full deployment starting..."
    check_uv
    setup_env
    restart_api
    sleep 2
    test_api
    log "Deployment complete!"
}

show_help() {
    echo "engagic API Management Script (uv-powered)"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  setup     - Install dependencies with uv"
    echo "  start     - Start the API server"
    echo "  stop      - Stop the API server"
    echo "  restart   - Restart the API server"
    echo "  status    - Show API status"
    echo "  logs      - Show API logs (follow mode)"
    echo "  test      - Test API endpoints"
    echo "  update    - Quick update (git pull + deps + restart)"
    echo "  deploy    - Full deployment (setup + restart + test)"
    echo "  help      - Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 deploy   # First time setup"
    echo "  $0 update   # Quick update from git"
    echo "  $0 logs     # Monitor logs"
}

# Main command handling
case "${1:-help}" in
    setup)     setup_env ;;
    start)     start_api ;;
    stop)      stop_api ;;
    restart)   restart_api ;;
    status)    status_api ;;
    logs)      logs_api ;;
    test)      test_api ;;
    update)    quick_update ;;
    deploy)    deploy_full ;;
    help|*)    show_help ;;
esac