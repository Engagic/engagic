#!/bin/bash
# Happening This Week Analysis Runner
#
# Runs Claude Code autonomously to analyze upcoming agenda items
# and populate the happening_items table.
#
# Usage:
#   ./scripts/run_happening.sh
#
# Cron example (run twice daily at 6am and 6pm):
#   0 6,18 * * * /opt/engagic/scripts/run_happening.sh >> /var/log/engagic/happening.log 2>&1

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Load secrets (same as systemd service)
if [ -f "$PROJECT_ROOT/.llm_secrets" ]; then
    set -a
    source "$PROJECT_ROOT/.llm_secrets"
    set +a
fi

# Build DATABASE_URL from config vars (mirrors config.py)
if [ -z "$DATABASE_URL" ]; then
    PGUSER="${ENGAGIC_POSTGRES_USER:-engagic}"
    PGPASS="${ENGAGIC_POSTGRES_PASSWORD:-}"
    PGHOST="${ENGAGIC_POSTGRES_HOST:-localhost}"
    PGPORT="${ENGAGIC_POSTGRES_PORT:-5432}"
    PGDB="${ENGAGIC_POSTGRES_DB:-engagic}"

    if [ -z "$PGPASS" ]; then
        echo "ERROR: ENGAGIC_POSTGRES_PASSWORD not set in .llm_secrets"
        exit 1
    fi

    export DATABASE_URL="postgresql://${PGUSER}:${PGPASS}@${PGHOST}:${PGPORT}/${PGDB}"
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') Starting Happening This Week analysis..."

# Run Claude Code with the happening prompt
# --allowedTools restricts to Bash for database queries only
claude -p "$(cat prompts/happening.md)" --allowedTools "Bash(psql:*)"

echo "$(date '+%Y-%m-%d %H:%M:%S') Happening analysis complete"
